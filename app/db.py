"""
Database Module for Smart Resume Screener.
Manages SQLite connection, table schema creation, schema migrations, and persistence helpers.
"""

import sqlite3
from pathlib import Path
from typing import Optional
from .config import DATABASE_PATH


def connect() -> sqlite3.Connection:
    """Create and return a configured SQLite connection."""
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DATABASE_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db() -> None:
    """Initialize database tables, apply backward-compatible column migrations, and create indexes."""
    con = connect()
    
    # 1. Base table creation
    con.executescript("""
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        requirements_json TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        filename TEXT,
        email TEXT,
        phone TEXT,
        resume_text TEXT NOT NULL,
        profile_json TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL,
        candidate_id INTEGER NOT NULL,
        score REAL NOT NULL,
        score_1_to_10 REAL DEFAULT 0.0,
        status TEXT DEFAULT 'Under Review',
        mode TEXT NOT NULL,
        result_json TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(job_id, candidate_id),
        FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
        FOREIGN KEY(candidate_id) REFERENCES candidates(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_results_job ON results(job_id);
    CREATE INDEX IF NOT EXISTS idx_results_score ON results(score DESC);
    CREATE INDEX IF NOT EXISTS idx_candidates_created ON candidates(created_at DESC);
    """)
    con.commit()

    # 2. Schema migrations for existing database files
    candidate_cols = [row[1] for row in con.execute("PRAGMA table_info(candidates)").fetchall()]
    if "email" not in candidate_cols:
        con.execute("ALTER TABLE candidates ADD COLUMN email TEXT")
    if "phone" not in candidate_cols:
        con.execute("ALTER TABLE candidates ADD COLUMN phone TEXT")

    result_cols = [row[1] for row in con.execute("PRAGMA table_info(results)").fetchall()]
    if "score_1_to_10" not in result_cols:
        con.execute("ALTER TABLE results ADD COLUMN score_1_to_10 REAL DEFAULT 0.0")
    if "status" not in result_cols:
        con.execute("ALTER TABLE results ADD COLUMN status TEXT DEFAULT 'Under Review'")

    con.commit()
    con.close()


def delete_job(job_id: int) -> bool:
    """Delete a job and its associated screening results."""
    con = connect()
    cur = con.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    con.execute("DELETE FROM results WHERE job_id = ?", (job_id,))
    con.commit()
    deleted = cur.rowcount > 0
    con.close()
    return deleted


def delete_candidate(candidate_id: int) -> bool:
    """Delete a candidate and their screening results."""
    con = connect()
    cur = con.execute("DELETE FROM candidates WHERE id = ?", (candidate_id,))
    con.execute("DELETE FROM results WHERE candidate_id = ?", (candidate_id,))
    con.commit()
    deleted = cur.rowcount > 0
    con.close()
    return deleted
