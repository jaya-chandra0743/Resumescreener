"""
FastAPI Application Entrypoint for Smart Resume Screener.
Exposes RESTful endpoints for Job management, Resume Parsing, Screening & Scoring,
Evidence inspection, and CSV/JSON reporting.
"""

import io
import csv
import json
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import MAX_UPLOAD_MB, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL
from .db import connect, init_db, delete_job, delete_candidate
from .parser import pdf_to_text, extract_profile, extract_job_requirements
from .matcher import hybrid_match


# Ensure database tables exist
init_db()

app = FastAPI(
    title="Smart Resume Screener API",
    description="Intelligent, Explainable AI Resume Screening and Shortlisting System",
    version="1.0.0"
)

# Mount static dashboard assets
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


class JobCreate(BaseModel):
    title: str = Field(..., min_length=2, description="Job title")
    description: str = Field(..., min_length=10, description="Full job description")


@app.get("/", response_class=HTMLResponse)
def home():
    """Serve the Recruiter Web Dashboard."""
    index_file = frontend_dir / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Dashboard index.html not found.")
    return index_file.read_text(encoding="utf-8")


@app.get("/api/health")
def health_check():
    """System health check and configuration status."""
    llm_active = bool(LLM_BASE_URL and LLM_API_KEY and LLM_MODEL)
    return {
        "status": "healthy",
        "service": "Smart Resume Screener",
        "version": "1.0.0",
        "llm_mode": "hybrid_llm" if llm_active else "deterministic_offline",
        "model": LLM_MODEL if llm_active else None
    }


# ==========================================
# Job Management Endpoints
# ==========================================

@app.post("/api/jobs")
def create_job(job: JobCreate):
    """Create a new job posting and parse structured requirements."""
    requirements = extract_job_requirements(job.description)
    con = connect()
    cur = con.execute(
        "INSERT INTO jobs (title, description, requirements_json) VALUES (?, ?, ?)",
        (job.title.strip(), job.description.strip(), json.dumps(requirements))
    )
    con.commit()
    job_id = cur.lastrowid
    con.close()

    return {
        "id": job_id,
        "title": job.title,
        "requirements": requirements,
        "message": f"Job #{job_id} created successfully."
    }


@app.get("/api/jobs")
def list_jobs():
    """Retrieve all job postings."""
    con = connect()
    rows = con.execute("""
        SELECT j.*, COUNT(r.id) as screened_count
        FROM jobs j
        LEFT JOIN results r ON r.job_id = j.id
        GROUP BY j.id
        ORDER BY j.id DESC
    """).fetchall()
    con.close()

    jobs_list = []
    for r in rows:
        item = dict(r)
        item["requirements"] = json.loads(item["requirements_json"])
        jobs_list.append(item)
    return jobs_list


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int):
    """Get details for a specific job."""
    con = connect()
    row = con.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    con.close()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found.")
    job_dict = dict(row)
    job_dict["requirements"] = json.loads(job_dict["requirements_json"])
    return job_dict


@app.delete("/api/jobs/{job_id}")
def remove_job(job_id: int):
    """Delete a job and all associated screening results."""
    success = delete_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {"message": f"Job #{job_id} and associated screening data deleted."}


# ==========================================
# Candidate Management Endpoints
# ==========================================

@app.post("/api/candidates")
async def upload_candidate(file: UploadFile = File(...)):
    """Upload and parse a single resume file (PDF, TXT, or MD)."""
    data = await file.read()
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File exceeds maximum upload size of {MAX_UPLOAD_MB}MB")

    filename = file.filename or "resume"
    ext = filename.lower().split(".")[-1]

    if ext == "pdf":
        try:
            text = pdf_to_text(data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse PDF: {str(e)}")
    elif ext in ["txt", "md"]:
        text = data.decode("utf-8", errors="ignore")
    else:
        raise HTTPException(status_code=400, detail="Unsupported file format. Please upload PDF, TXT, or MD resumes.")

    if not text.strip():
        raise HTTPException(status_code=400, detail="The uploaded file contains no extractable text.")

    profile = extract_profile(text)
    con = connect()
    cur = con.execute(
        "INSERT INTO candidates (name, filename, email, phone, resume_text, profile_json) VALUES (?, ?, ?, ?, ?, ?)",
        (profile["name"], filename, profile.get("email", ""), profile.get("phone", ""), text, json.dumps(profile))
    )
    con.commit()
    candidate_id = cur.lastrowid
    con.close()

    return {
        "id": candidate_id,
        "name": profile["name"],
        "filename": filename,
        "profile": profile,
        "message": f"Candidate '{profile['name']}' parsed and saved."
    }


@app.get("/api/candidates")
def list_candidates():
    """Retrieve all parsed candidates."""
    con = connect()
    rows = con.execute("""
        SELECT id, name, filename, email, phone, created_at, profile_json
        FROM candidates
        ORDER BY id DESC
    """).fetchall()
    con.close()

    out = []
    for r in rows:
        d = dict(r)
        d["profile"] = json.loads(d["profile_json"])
        out.append(d)
    return out


@app.delete("/api/candidates/{candidate_id}")
def remove_candidate(candidate_id: int):
    """Delete a candidate."""
    success = delete_candidate(candidate_id)
    if not success:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    return {"message": f"Candidate #{candidate_id} deleted."}


# ==========================================
# Screening & Scoring Endpoints
# ==========================================

@app.post("/api/screen")
def screen_candidates(job_id: int = Query(..., description="ID of the job to screen against")):
    """Screen and rank all uploaded candidates against the specified job."""
    con = connect()
    job_row = con.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job_row:
        con.close()
        raise HTTPException(status_code=404, detail=f"Job #{job_id} not found.")

    requirements = json.loads(job_row["requirements_json"])
    candidate_rows = con.execute("SELECT * FROM candidates").fetchall()

    if not candidate_rows:
        con.close()
        return []

    ranked_results = []
    for c in candidate_rows:
        profile = json.loads(c["profile_json"])
        match_result = hybrid_match(profile, requirements)

        # Upsert result in SQLite database
        con.execute("""
            INSERT INTO results (job_id, candidate_id, score, score_1_to_10, status, mode, result_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id, candidate_id) DO UPDATE SET
                score = excluded.score,
                score_1_to_10 = excluded.score_1_to_10,
                status = excluded.status,
                mode = excluded.mode,
                result_json = excluded.result_json,
                created_at = CURRENT_TIMESTAMP
        """, (
            job_id,
            c["id"],
            match_result["score"],
            match_result["score_1_to_10"],
            match_result["status"],
            match_result["mode"],
            json.dumps(match_result)
        ))

        ranked_results.append({
            "candidate_id": c["id"],
            "name": c["name"],
            "filename": c["filename"],
            "email": c["email"],
            "score": match_result["score"],
            "score_1_to_10": match_result["score_1_to_10"],
            "status": match_result["status"],
            "mode": match_result["mode"],
            "justification": match_result["justification"],
            "skill_gaps": match_result["skill_gaps"],
            "strengths": match_result.get("strengths", []),
            "subscores": match_result.get("subscores", {})
        })

    con.commit()
    con.close()

    # Sort descending by final score
    ranked_results.sort(key=lambda x: x["score"], reverse=True)
    return ranked_results


@app.get("/api/results/{job_id}")
def get_job_results(job_id: int, status: Optional[str] = None):
    """Fetch stored screening results for a job, with optional status filtering."""
    con = connect()
    query = """
        SELECT r.*, c.name, c.filename, c.email, c.phone
        FROM results r
        JOIN candidates c ON c.id = r.candidate_id
        WHERE r.job_id = ?
    """
    params = [job_id]

    if status:
        query += " AND r.status = ?"
        params.append(status)

    query += " ORDER BY r.score DESC"
    rows = con.execute(query, params).fetchall()
    con.close()

    out = []
    for r in rows:
        d = dict(r)
        d["result"] = json.loads(d["result_json"])
        out.append(d)
    return out


@app.get("/api/results/{job_id}/{candidate_id}")
def get_candidate_evidence(job_id: int, candidate_id: int):
    """Retrieve in-depth evidence map, subscores, and justification for a candidate."""
    con = connect()
    row = con.execute("""
        SELECT r.*, c.name, c.filename, c.email, c.phone, c.profile_json
        FROM results r
        JOIN candidates c ON c.id = r.candidate_id
        WHERE r.job_id = ? AND r.candidate_id = ?
    """, (job_id, candidate_id)).fetchone()
    con.close()

    if not row:
        raise HTTPException(status_code=404, detail="Screening result not found for this candidate and job.")

    data = dict(row)
    data["result"] = json.loads(data["result_json"])
    data["profile"] = json.loads(data["profile_json"])
    return data


# ==========================================
# Export Endpoints (CSV / JSON)
# ==========================================

@app.get("/api/export/{job_id}")
def export_results(job_id: int, format: str = Query("csv", pattern="^(csv|json)$")):
    """Export screening shortlist results in CSV or JSON format."""
    con = connect()
    job = con.execute("SELECT title FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        con.close()
        raise HTTPException(status_code=404, detail="Job not found.")

    rows = con.execute("""
        SELECT r.score, r.score_1_to_10, r.status, r.mode, r.result_json,
               c.name, c.filename, c.email, c.phone
        FROM results r
        JOIN candidates c ON c.id = r.candidate_id
        WHERE r.job_id = ?
        ORDER BY r.score DESC
    """, (job_id,)).fetchall()
    con.close()

    job_title = job["title"].replace(" ", "_").lower()

    if format == "json":
        items = []
        for r in rows:
            d = dict(r)
            d["result"] = json.loads(d["result_json"])
            items.append(d)
        return JSONResponse(content={"job_id": job_id, "job_title": job["title"], "results": items})

    # CSV Generation
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Rank", "Candidate Name", "Fit Score (%)", "Score (1-10)", "Status",
        "Evaluation Mode", "Email", "Phone", "Filename", "Justification", "Skill Gaps"
    ])

    for rank, r in enumerate(rows, start=1):
        res = json.loads(r["result_json"])
        writer.writerow([
            rank,
            r["name"],
            f"{r['score']}%",
            r["score_1_to_10"],
            r["status"],
            r["mode"],
            r["email"] or "N/A",
            r["phone"] or "N/A",
            r["filename"] or "N/A",
            res.get("justification", ""),
            ", ".join(res.get("skill_gaps", []))
        ])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=screening_report_{job_title}_job{job_id}.csv"}
    )
