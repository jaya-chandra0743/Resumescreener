"""
Resume and Job Description Parser Module.
Extracts structured candidate data (skills, experience, education, contact info, projects)
from PDF and plain text documents.
"""

import re
from typing import Dict, Any, List
import pymupdf


# Expanded multi-disciplinary skill taxonomy
SKILLS_TAXONOMY = [
    # Programming Languages
    "python", "java", "javascript", "typescript", "c++", "c#", "c", "go", "golang",
    "rust", "ruby", "php", "kotlin", "swift", "scala", "r", "dart", "perl", "bash", "shell",

    # Web & Frontend Frameworks
    "react", "react.js", "angular", "vue", "vue.js", "next.js", "nuxt.js", "node.js",
    "node", "express", "express.js", "html", "html5", "css", "css3", "sass", "scss",
    "tailwind", "tailwind css", "bootstrap", "redux", "graphql", "rest api", "rest",
    "web development", "webpack", "vite", "material ui",

    # Backend & Microservices
    "fastapi", "django", "flask", "spring", "spring boot", "hibernate", "asp.net",
    "dotnet", ".net core", "microservices", "api development", "grpc", "celery",
    "message queue", "kafka", "rabbitmq", "event driven architecture",

    # Databases & Storage
    "sql", "mysql", "postgresql", "postgres", "mongodb", "redis", "sqlite",
    "oracle", "cassandra", "dynamodb", "elasticsearch", "neo4j", "mariadb",
    "database design", "nosql", "firebase", "supabase",

    # Cloud, DevOps & Infrastructure
    "aws", "amazon web services", "azure", "microsoft azure", "gcp", "google cloud",
    "docker", "kubernetes", "k8s", "terraform", "ansible", "jenkins", "ci/cd",
    "github actions", "gitlab ci", "linux", "unix", "nginx", "apache",
    "cloud computing", "serverless", "lambda", "helm", "prometheus", "grafana",

    # Data Science, Machine Learning & AI
    "machine learning", "deep learning", "artificial intelligence", "ai",
    "natural language processing", "nlp", "computer vision", "llm", "large language models",
    "generative ai", "genai", "prompt engineering", "langchain", "llamaindex",
    "pandas", "numpy", "scipy", "scikit-learn", "tensorflow", "pytorch", "keras",
    "opencv", "data analysis", "data science", "statistics", "power bi", "tableau",
    "spark", "hadoop", "etl", "data engineering",

    # Cybersecurity & Security Testing
    "cybersecurity", "cyber security", "network security", "application security",
    "cloud security", "penetration testing", "ethical hacking", "vulnerability assessment",
    "incident response", "threat analysis", "siem", "splunk", "wireshark", "nmap",
    "burp suite", "metasploit", "kali linux", "owasp", "owasp top 10", "cryptography",
    "encryption", "authentication", "authorization", "oauth", "jwt", "soc2",

    # Software Engineering Practices
    "git", "github", "gitlab", "bitbucket", "data structures", "algorithms",
    "object oriented programming", "oop", "system design", "design patterns",
    "unit testing", "test driven development", "tdd", "pytest", "junit", "selenium",
    "cypress", "agile", "scrum", "jira", "code review", "debugging",

    # Mobile & Cross Platform
    "android", "ios", "flutter", "react native", "mobile development",

    # UI/UX & Product Design
    "figma", "ui design", "ux design", "user experience", "wireframing", "prototyping"
]


def pdf_to_text(data: bytes) -> str:
    """Extract raw text from PDF bytes using PyMuPDF."""
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
        pages_text = []
        for page in doc:
            page_text = page.get_text("text")
            if page_text:
                pages_text.append(page_text)
        return "\n".join(pages_text).strip()
    except Exception as e:
        raise ValueError(f"Failed to extract text from PDF: {str(e)}")


def normalize_text(text: str) -> str:
    """Clean and normalize whitespace, null bytes, and common unicode characters."""
    if not text:
        return ""
    text = text.replace("\x00", " ")
    text = re.sub(r"[\r\n]+", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def extract_contact_info(text: str) -> Dict[str, str]:
    """Extract email, phone number, and social links from resume text."""
    # Email regex
    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
    email = email_match.group(0) if email_match else ""

    # Phone regex (Indian/US/International formats)
    phone_match = re.search(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text)
    phone = phone_match.group(0) if phone_match else ""

    # LinkedIn / GitHub links
    linkedin_match = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-]+", text, re.I)
    linkedin = linkedin_match.group(0) if linkedin_match else ""

    github_match = re.search(r"(?:https?://)?(?:www\.)?github\.com/[\w\-]+", text, re.I)
    github = github_match.group(0) if github_match else ""

    return {
        "email": email,
        "phone": phone,
        "linkedin": linkedin,
        "github": github
    }


def extract_name(text: str) -> str:
    """Extract the candidate name from top lines of the resume."""
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    for line in lines[:8]:
        # Filter out common header words, contact info, and URLs
        if (
            2 <= len(line.split()) <= 5
            and not re.search(r"@|http|www\.|resume|curriculum|phone|contact|profile|skills|github|linkedin|\d{5,}", line, re.I)
            and len(line) < 45
        ):
            # Clean non-alphabetical prefix chars
            cleaned = re.sub(r"^[^a-zA-Z]+", "", line).strip()
            if cleaned:
                return cleaned
    return "Candidate"


def skill_regex_pattern(skill: str) -> str:
    """Generate exact boundary regex pattern for a skill string."""
    escaped = re.escape(skill.lower())
    escaped = escaped.replace(r"\ ", r"\s+")
    # Handles skills with special symbols like c++, c#, .net, next.js
    return r"(?<![a-zA-Z0-9_])" + escaped + r"(?![a-zA-Z0-9_])"


def extract_skills(text: str) -> List[str]:
    """Extract recognized skills from text using boundary matching."""
    text_low = text.lower()
    found = []
    for skill in SKILLS_TAXONOMY:
        if re.search(skill_regex_pattern(skill), text_low):
            found.append(skill)
    return sorted(list(set(found)))


def extract_experience_years(text: str) -> float:
    """Extract total years of experience from resume text."""
    # Matches: "3 years of experience", "2.5+ yrs experience", "5+ years", "4 yrs of professional experience"
    patterns = [
        r"(?i)(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)\s*(?:of)?\s*(?:relevant|hands-on|industry|work|professional)?\s*experience",
        r"(?i)experience\s*:\s*(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)",
        r"(?i)(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)\s+in\s+software"
    ]
    years_found = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for m in matches:
            try:
                years_found.append(float(m))
            except ValueError:
                continue

    return max(years_found, default=0.0)


def extract_education(text: str) -> List[str]:
    """Extract recognized educational degrees and qualifications."""
    degrees_map = {
        "b.tech": "B.Tech",
        "b.e": "B.E",
        "b.sc": "B.Sc",
        "b.s": "B.S",
        "bca": "BCA",
        "bachelor": "Bachelor's Degree",
        "m.tech": "M.Tech",
        "m.e": "M.E",
        "m.sc": "M.Sc",
        "m.s": "M.S",
        "mca": "MCA",
        "master": "Master's Degree",
        "mba": "MBA",
        "ph.d": "Ph.D",
        "phd": "Ph.D",
        "diploma": "Diploma"
    }

    text_low = text.lower()
    detected = []
    for key, label in degrees_map.items():
        if re.search(r"(?<![a-zA-Z0-9])" + re.escape(key) + r"(?![a-zA-Z0-9])", text_low):
            if label not in detected:
                detected.append(label)
    return detected


def extract_section(text: str, headings: List[str]) -> str:
    """Extract text content under specified section heading."""
    pattern = (
        r"(?is)(?:^|\n)\s*(?:"
        + "|".join(map(re.escape, headings))
        + r")\s*:?\s*\n?(.*?)(?=\n\s*(?:[A-Z][A-Za-z /&-]{2,25}\s*:?\s*\n|$))"
    )
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip()
    return ""


def extract_profile(text: str) -> Dict[str, Any]:
    """Extract full structured candidate profile from resume text."""
    normalized = normalize_text(text)
    contacts = extract_contact_info(normalized)

    summary_text = extract_section(normalized, ["summary", "professional summary", "profile", "about me", "objective"])
    experience_text = extract_section(normalized, ["experience", "work experience", "professional experience", "employment history"])
    projects_text = extract_section(normalized, ["projects", "personal projects", "academic projects", "key projects"])
    education_text = extract_section(normalized, ["education", "academic background", "academics", "qualifications"])
    certifications_text = extract_section(normalized, ["certifications", "certificates", "licenses"])

    return {
        "name": extract_name(normalized),
        "email": contacts["email"],
        "phone": contacts["phone"],
        "linkedin": contacts["linkedin"],
        "github": contacts["github"],
        "skills": extract_skills(normalized),
        "experience_years": extract_experience_years(normalized),
        "education": extract_education(normalized),
        "summary": summary_text,
        "experience_text": experience_text,
        "projects": projects_text,
        "education_text": education_text,
        "certifications": certifications_text,
        "raw_text_length": len(normalized)
    }


def extract_job_requirements(description: str) -> Dict[str, Any]:
    """Extract structured requirements from a job description."""
    normalized = normalize_text(description)
    lines = [
        line.strip("•-* \t")
        for line in normalized.splitlines()
        if line.strip()
    ]

    return {
        "skills": extract_skills(normalized),
        "experience_years": extract_experience_years(normalized),
        "education": extract_education(normalized),
        "responsibilities": lines[:20],
        "raw_description": normalized
    }