"""
Explainable Hybrid Matching Engine.
Evaluates candidate profiles against job requirements using deterministic rule-based
evidence extraction combined with LLM semantic evaluation.
"""

import json
import re
from typing import Dict, Any, List, Optional
import requests
from .config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL


STRONG_ACTION_KEYWORDS = [
    "built", "developed", "implemented", "created", "designed", "architected",
    "engineered", "deployed", "scaled", "maintained", "managed", "led", "optimized",
    "integrated", "authored", "delivered", "programmed", "configured", "administered",
    "tested", "debugged", "automated", "used", "using", "utilizing", "hands-on"
]


def normalize_string(text: str) -> str:
    """Normalize string for fuzzy evidence matching."""
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def extract_skill_evidence(skill: str, profile: Dict[str, Any]) -> Dict[str, str]:
    """
    Search candidate profile sections to evaluate evidence quality:
    - STRONG: Skill mentioned in projects/experience with action verbs
    - PARTIAL: Skill listed in skills list or brief mention without deep context
    - MISSING: Skill not detected anywhere in resume
    """
    skill_clean = skill.strip().lower()
    profile_skills = [s.strip().lower() for s in profile.get("skills", [])]

    if skill_clean not in profile_skills:
        return {
            "skill": skill,
            "level": "MISSING",
            "evidence": "No mention of this skill found in resume."
        }

    # Aggregate context-heavy sections
    context_sources = [
        profile.get("experience_text", ""),
        profile.get("projects", ""),
        profile.get("summary", "")
    ]
    combined_context = " ".join(filter(None, context_sources))
    combined_normalized = normalize_string(combined_context)

    if skill_clean not in combined_normalized:
        return {
            "skill": skill,
            "level": "PARTIAL",
            "evidence": f"'{skill}' is listed in the candidate's skills section, but without detailed work or project descriptions."
        }

    # Find position and surrounding sentence excerpt
    pos = combined_normalized.find(skill_clean)
    start_pos = max(0, pos - 80)
    end_pos = min(len(combined_context), pos + len(skill_clean) + 120)
    snippet = combined_context[start_pos:end_pos].strip()

    is_strong = any(action in snippet.lower() for action in STRONG_ACTION_KEYWORDS)

    return {
        "skill": skill,
        "level": "STRONG" if is_strong else "PARTIAL",
        "evidence": " ".join(snippet.split())[:260]
    }


def determine_status(score: float) -> str:
    """Assign recruiter shortlist status category based on final percentage score."""
    if score >= 75.0:
        return "Shortlisted"
    elif score >= 50.0:
        return "Under Review"
    else:
        return "Not Recommended"


def deterministic_match(profile: Dict[str, Any], job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute explainable rule-based match score between candidate profile and job requirements.
    Weights: Skills (55%), Experience (20%), Education (10%), Project context (15%).
    """
    required_skills = job.get("skills", [])
    evidence_cards = [extract_skill_evidence(skill, profile) for skill in required_skills]

    # 1. Skills Score calculation
    if not required_skills:
        skill_score = 100.0
    else:
        strong_count = sum(1 for card in evidence_cards if card["level"] == "STRONG")
        partial_count = sum(1 for card in evidence_cards if card["level"] == "PARTIAL")
        skill_score = ((strong_count * 1.0 + partial_count * 0.5) / len(required_skills)) * 100.0

    # 2. Experience Alignment Score
    required_exp = float(job.get("experience_years", 0.0) or 0.0)
    candidate_exp = float(profile.get("experience_years", 0.0) or 0.0)

    if required_exp <= 0.0:
        experience_score = 100.0
    else:
        experience_score = min(100.0, (candidate_exp / required_exp) * 100.0)

    # 3. Education Alignment Score
    required_edu = [e.lower() for e in job.get("education", [])]
    candidate_edu = [e.lower() for e in profile.get("education", [])]

    if not required_edu:
        education_score = 100.0
    elif any(req in candidate_edu for req in required_edu) or candidate_edu:
        education_score = 100.0
    else:
        education_score = 40.0

    # 4. Projects Alignment Score
    project_text = normalize_string(profile.get("projects", ""))
    if not project_text or not required_skills:
        project_score = 50.0 if not required_skills else 20.0
    else:
        matched_in_projects = sum(1 for skill in required_skills if skill.lower() in project_text)
        project_score = min(100.0, (matched_in_projects / len(required_skills)) * 100.0)

    # Composite weighted score
    overall_score = round(
        (skill_score * 0.55) +
        (experience_score * 0.20) +
        (education_score * 0.10) +
        (project_score * 0.15),
        1
    )

    missing_skills = [c["skill"] for c in evidence_cards if c["level"] == "MISSING"]
    strong_skills = [c["skill"] for c in evidence_cards if c["level"] == "STRONG"]
    partial_skills = [c["skill"] for c in evidence_cards if c["level"] == "PARTIAL"]

    # Natural language justification
    justification_parts = []
    if strong_skills:
        justification_parts.append(f"Demonstrates strong hands-on evidence in {len(strong_skills)} required skill(s) ({', '.join(strong_skills[:3])}).")
    if partial_skills:
        justification_parts.append(f"Lists {len(partial_skills)} skill(s) ({', '.join(partial_skills[:2])}) with moderate context.")
    if missing_skills:
        justification_parts.append(f"Missing key requirement(s): {', '.join(missing_skills[:3])}.")
    if candidate_exp > 0:
        justification_parts.append(f"Candidate brings {candidate_exp:g} year(s) of experience vs {required_exp:g} year(s) required.")

    justification = " ".join(justification_parts) if justification_parts else "Candidate matches general job profile requirements."
    status = determine_status(overall_score)

    return {
        "score": overall_score,
        "score_1_to_10": round(overall_score / 10.0, 1),
        "status": status,
        "mode": "deterministic",
        "justification": justification,
        "evidence": evidence_cards,
        "skill_gaps": missing_skills,
        "strengths": strong_skills,
        "subscores": {
            "skills": round(skill_score, 1),
            "experience": round(experience_score, 1),
            "education": round(education_score, 1),
            "projects": round(project_score, 1)
        }
    }


def llm_match(profile: Dict[str, Any], job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Perform semantic matching using an OpenAI-compatible LLM endpoint.
    Follows project guidelines: 'Compare the following resume with this job description and rate fit on 1–10 with justification.'
    """
    if not (LLM_BASE_URL and LLM_API_KEY and LLM_MODEL):
        return None

    system_prompt = (
        "You are an expert AI recruitment screener. Your job is to evaluate candidate fit "
        "against job descriptions with high objectivity, exact evidence citations, and no hallucinations. "
        "Do not assume unlisted qualifications. Always respond in valid JSON format only."
    )

    user_prompt = (
        "Compare the following resume with this job description and rate fit on 1–10 with justification.\n\n"
        f"--- CANDIDATE PROFILE ---\n{json.dumps(profile, indent=2)}\n\n"
        f"--- JOB DESCRIPTION & REQUIREMENTS ---\n{json.dumps(job, indent=2)}\n\n"
        "Return a single JSON object with exact keys:\n"
        "{\n"
        '  "score_1_to_10": <number between 1.0 and 10.0>,\n'
        '  "status": "Shortlisted" | "Under Review" | "Not Recommended",\n'
        '  "justification": "<2-3 sentence executive reasoning>",\n'
        '  "evidence": [{"skill": "<skill_name>", "level": "STRONG"|"PARTIAL"|"MISSING", "evidence": "<quote or reason>"}],\n'
        '  "skill_gaps": ["<missing skill 1>", "<missing skill 2>"],\n'
        '  "strengths": ["<strength 1>", "<strength 2>"]\n'
        "}"
    )

    payload = {
        "model": LLM_MODEL,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    }

    try:
        response = requests.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        raw_content = response.json()["choices"][0]["message"]["content"].strip()

        # Clean JSON markdown fences if present
        clean_json_str = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_content, flags=re.DOTALL | re.IGNORECASE).strip()
        parsed_data = json.loads(clean_json_str)

        # Validate score range
        score_1_to_10 = float(parsed_data.get("score_1_to_10", 5.0))
        score_1_to_10 = max(1.0, min(10.0, score_1_to_10))
        parsed_data["score_1_to_10"] = score_1_to_10
        parsed_data["score"] = round(score_1_to_10 * 10.0, 1)

        return parsed_data
    except Exception:
        # Graceful fallback to deterministic matcher on any network or parsing error
        return None


def hybrid_match(profile: Dict[str, Any], job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute hybrid matching: Runs deterministic evidence analysis and fuses with
    LLM semantic evaluation if LLM is enabled and reachable.
    """
    base_result = deterministic_match(profile, job)
    llm_result = llm_match(profile, job)

    if not llm_result:
        return base_result

    try:
        llm_score = float(llm_result.get("score", base_result["score"]))
        # Fuse 65% deterministic rules + 35% LLM semantic scoring
        fused_score = round((base_result["score"] * 0.65) + (llm_score * 0.35), 1)

        return {
            **base_result,
            "score": fused_score,
            "score_1_to_10": round(fused_score / 10.0, 1),
            "status": determine_status(fused_score),
            "mode": "hybrid_llm",
            "llm_score": llm_score,
            "justification": llm_result.get("justification", base_result["justification"]),
            "evidence": llm_result.get("evidence", base_result["evidence"]),
            "skill_gaps": llm_result.get("skill_gaps", base_result["skill_gaps"]),
            "strengths": llm_result.get("strengths", base_result["strengths"])
        }
    except Exception:
        return base_result