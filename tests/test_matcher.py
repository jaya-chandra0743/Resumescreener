"""
Unit tests for Explainable Hybrid Matching Engine.
"""

from app.matcher import (
    extract_skill_evidence,
    determine_status,
    deterministic_match,
    hybrid_match
)


CANDIDATE_PROFILE = {
    "name": "Jane Doe",
    "skills": ["java", "spring boot", "sql", "docker", "git", "aws"],
    "experience_years": 4.0,
    "education": ["B.Tech"],
    "summary": "Experienced Java backend developer with 4 years building APIs.",
    "experience_text": "Built and deployed Spring Boot microservices with Docker and optimized SQL queries.",
    "projects": "Online Portal developed using Java, Spring Boot, MySQL, and Docker."
}

JOB_REQUIREMENTS = {
    "skills": ["java", "spring boot", "sql", "docker", "kubernetes"],
    "experience_years": 3.0,
    "education": ["b.tech"],
    "responsibilities": ["Design REST APIs", "Manage Docker containers"]
}


def test_extract_skill_evidence_strong():
    evidence = extract_skill_evidence("java", CANDIDATE_PROFILE)
    assert evidence["level"] == "STRONG"
    assert "java" in evidence["evidence"].lower()


def test_extract_skill_evidence_missing():
    evidence = extract_skill_evidence("kubernetes", CANDIDATE_PROFILE)
    assert evidence["level"] == "MISSING"


def test_determine_status():
    assert determine_status(85.0) == "Shortlisted"
    assert determine_status(65.0) == "Under Review"
    assert determine_status(40.0) == "Not Recommended"


def test_deterministic_match_high_fit():
    result = deterministic_match(CANDIDATE_PROFILE, JOB_REQUIREMENTS)
    assert result["score"] >= 70.0
    assert result["score_1_to_10"] >= 7.0
    assert result["status"] in ["Shortlisted", "Under Review"]
    assert "subscores" in result
    assert result["subscores"]["experience"] == 100.0
    assert "kubernetes" in result["skill_gaps"]
    assert len(result["evidence"]) == len(JOB_REQUIREMENTS["skills"])


def test_deterministic_match_low_fit():
    unrelated_profile = {
        "name": "Graphic Designer",
        "skills": ["figma", "ui design", "photoshop"],
        "experience_years": 1.0,
        "education": ["Diploma"],
        "summary": "UI designer with 1 year experience.",
        "experience_text": "Created mockups in Figma.",
        "projects": "Design portfolio in Figma."
    }
    result = deterministic_match(unrelated_profile, JOB_REQUIREMENTS)
    assert result["score"] < 50.0
    assert result["status"] == "Not Recommended"
    assert len(result["skill_gaps"]) >= 4


def test_hybrid_match_fallback():
    # LLM keys not configured in test environment -> should gracefully fallback
    result = hybrid_match(CANDIDATE_PROFILE, JOB_REQUIREMENTS)
    assert result["score"] > 0
    assert result["status"] in ["Shortlisted", "Under Review"]
