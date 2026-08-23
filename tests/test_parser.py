"""
Unit tests for Resume Parser and Structured Data Extraction.
"""

from pathlib import Path
from app.parser import (
    normalize_text,
    extract_contact_info,
    extract_name,
    extract_skills,
    extract_experience_years,
    extract_education,
    extract_profile,
    extract_job_requirements,
    pdf_to_text
)


SAMPLE_RESUME_TEXT = """
Alex Morgan
Email: alex.morgan@test.com | Phone: +1 555-019-2834
LinkedIn: linkedin.com/in/alexmorgan | GitHub: github.com/alexmorgan

Summary
Senior Software Engineer with 5+ years of experience in backend systems.

Technical Skills
Java, Python, Spring Boot, FastAPI, PostgreSQL, Docker, AWS, Git

Professional Experience
Lead Backend Developer | FinTech Corp (2021 - Present)
- Architected REST APIs using Java and Spring Boot.
- Deployed microservices on AWS with Docker.
- Optimized PostgreSQL queries for low latency.

Education
B.Tech in Computer Science | State University
"""


def test_normalize_text():
    raw = "  Hello   world \r\n\r\n this is \x00 test  "
    clean = normalize_text(raw)
    assert "Hello world" in clean
    assert "this is test" in clean
    assert "\x00" not in clean


def test_extract_contact_info():
    info = extract_contact_info(SAMPLE_RESUME_TEXT)
    assert info["email"] == "alex.morgan@test.com"
    assert "555" in info["phone"]
    assert "linkedin.com/in/alexmorgan" in info["linkedin"]
    assert "github.com/alexmorgan" in info["github"]


def test_extract_name():
    name = extract_name(SAMPLE_RESUME_TEXT)
    assert name == "Alex Morgan"


def test_extract_skills():
    skills = extract_skills(SAMPLE_RESUME_TEXT)
    assert "java" in skills
    assert "spring boot" in skills
    assert "fastapi" in skills
    assert "postgresql" in skills
    assert "docker" in skills
    assert "aws" in skills


def test_extract_experience_years():
    years = extract_experience_years(SAMPLE_RESUME_TEXT)
    assert years == 5.0


def test_extract_education():
    edu = extract_education(SAMPLE_RESUME_TEXT)
    assert "B.Tech" in edu


def test_extract_profile():
    profile = extract_profile(SAMPLE_RESUME_TEXT)
    assert profile["name"] == "Alex Morgan"
    assert profile["experience_years"] == 5.0
    assert "B.Tech" in profile["education"]
    assert "java" in profile["skills"]
    assert len(profile["skills"]) >= 5


def test_extract_job_requirements():
    job_desc = """
    We need a Python FastAPI Backend Developer with 3 years of experience.
    Requirements:
    - Python
    - FastAPI
    - Docker
    - SQL
    - Git
    """
    reqs = extract_job_requirements(job_desc)
    assert "python" in reqs["skills"]
    assert "fastapi" in reqs["skills"]
    assert "docker" in reqs["skills"]
    assert reqs["experience_years"] == 3.0


def test_pdf_parsing():
    pdf_path = Path("sample_data/resume_1_backend_senior.pdf")
    if pdf_path.exists():
        data = pdf_path.read_bytes()
        text = pdf_to_text(data)
        assert len(text) > 50
        assert "Arun Kumar" in text
        profile = extract_profile(text)
        assert profile["name"] == "Arun Kumar"
        assert "java" in profile["skills"]
        assert "spring boot" in profile["skills"]
