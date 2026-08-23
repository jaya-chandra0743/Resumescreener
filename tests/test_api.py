"""
Integration tests for FastAPI REST Endpoints.
"""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "service" in data


def test_home_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "Smart Resume Screener" in response.text


def test_job_lifecycle():
    # 1. Create Job
    job_payload = {
        "title": "Backend Python Specialist",
        "description": "Requires 2+ years experience in Python, FastAPI, Docker, and SQL."
    }
    create_res = client.post("/api/jobs", json=job_payload)
    assert create_res.status_code == 200
    job_data = create_res.json()
    assert "id" in job_data
    job_id = job_data["id"]

    # 2. List Jobs
    list_res = client.get("/api/jobs")
    assert list_res.status_code == 200
    jobs = list_res.json()
    assert any(j["id"] == job_id for j in jobs)

    # 3. Get Single Job
    get_res = client.get(f"/api/jobs/{job_id}")
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "Backend Python Specialist"


def test_candidate_upload_and_screening():
    # 1. Create Job
    job_res = client.post("/api/jobs", json={
        "title": "DevOps Engineer",
        "description": "Looking for DevOps Engineer with Docker, Kubernetes, AWS, and Git experience."
    })
    job_id = job_res.json()["id"]

    # 2. Upload Candidate Resume
    resume_content = """
    Vikram Patel
    Email: vikram@devops.example.com
    Summary: 3 years experience as DevOps Engineer.
    Skills: Docker, Kubernetes, AWS, Git, Linux
    Experience: Built CI/CD pipelines on AWS using Docker and Kubernetes.
    Education: B.Tech Computer Science
    """
    upload_res = client.post(
        "/api/candidates",
        files={"file": ("vikram_resume.txt", resume_content.encode("utf-8"), "text/plain")}
    )
    assert upload_res.status_code == 200
    candidate_data = upload_res.json()
    assert candidate_data["name"] == "Vikram Patel"
    candidate_id = candidate_data["id"]

    # 3. Run Screening
    screen_res = client.post(f"/api/screen?job_id={job_id}")
    assert screen_res.status_code == 200
    results = screen_res.json()
    assert len(results) >= 1
    vikram_result = next(r for r in results if r["candidate_id"] == candidate_id)
    assert vikram_result["score"] >= 60.0

    # 4. Get Candidate Evidence Details
    detail_res = client.get(f"/api/results/{job_id}/{candidate_id}")
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    assert "result" in detail_data
    assert "evidence" in detail_data["result"]

    # 5. Test Export Endpoints
    csv_res = client.get(f"/api/export/{job_id}?format=csv")
    assert csv_res.status_code == 200
    assert "Vikram Patel" in csv_res.text

    json_res = client.get(f"/api/export/{job_id}?format=json")
    assert json_res.status_code == 200
    assert json_res.json()["job_id"] == job_id
