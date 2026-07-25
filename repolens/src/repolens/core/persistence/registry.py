"""SQLite-backed repository registry and pipeline job history."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any


def default_data_dir() -> Path:
    configured = os.environ.get("REPOLENS_DATA_DIR")
    return Path(configured).expanduser().resolve() if configured else Path(".repolens").resolve()


class RegistryStore:
    """Durable server state shared by REST, scheduler, and MCP surfaces."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or default_data_dir() / "registry.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS repositories (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    local_path TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    files_count INTEGER NOT NULL DEFAULT 0,
                    symbols_count INTEGER NOT NULL DEFAULT 0,
                    edges_count INTEGER NOT NULL DEFAULT 0,
                    chunks_count INTEGER NOT NULL DEFAULT 0,
                    is_git INTEGER NOT NULL DEFAULT 0,
                    last_indexed REAL,
                    index_duration_s REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    repo_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    started_at REAL NOT NULL,
                    completed_at REAL,
                    duration_s REAL,
                    files_processed INTEGER NOT NULL DEFAULT 0,
                    symbols_extracted INTEGER NOT NULL DEFAULT 0,
                    edges_resolved INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    details TEXT NOT NULL DEFAULT '{}'
                )"""
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_repo ON jobs(repo_id, started_at DESC)")

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        data = dict(row)
        if "is_git" in data:
            data["is_git"] = bool(data["is_git"])
        if "details" in data:
            try:
                data.update(json.loads(data.pop("details") or "{}"))
            except json.JSONDecodeError:
                data.pop("details", None)
        return data

    def add_repo(self, repo: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO repositories
                   (id, name, local_path, status, files_count, is_git, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    repo["id"], repo["name"], repo["local_path"], repo["status"],
                    repo.get("files_count", 0), int(repo.get("is_git", False)),
                    repo.get("created_at", now), now,
                ),
            )
        return self.get_repo(repo["id"]) or repo

    def list_repos(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM repositories ORDER BY created_at").fetchall()
        return [self._row(row) for row in rows if row is not None]

    def get_repo(self, repo_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM repositories WHERE id = ?", (repo_id,)).fetchone()
        return self._row(row)

    def find_repo_by_path(self, local_path: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM repositories WHERE local_path = ?", (local_path,)
            ).fetchone()
        return self._row(row)

    def update_repo(self, repo_id: str, **fields: Any) -> dict[str, Any] | None:
        allowed = {
            "name", "status", "files_count", "symbols_count", "edges_count",
            "chunks_count", "last_indexed", "index_duration_s",
        }
        values = {key: value for key, value in fields.items() if key in allowed}
        if not values:
            return self.get_repo(repo_id)
        values["updated_at"] = time.time()
        assignments = ", ".join(f"{key} = ?" for key in values)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE repositories SET {assignments} WHERE id = ?",
                (*values.values(), repo_id),
            )
        return self.get_repo(repo_id)

    def remove_repo(self, repo_id: str) -> bool:
        with self._connect() as conn:
            deleted = conn.execute("DELETE FROM repositories WHERE id = ?", (repo_id,)).rowcount
        return bool(deleted)

    def create_job(self, job: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO jobs
                   (id, repo_id, mode, status, phase, progress, started_at, details)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job["id"], job["repo_id"], job["mode"], job.get("status", "running"),
                    job.get("phase", "starting"), job.get("progress", 0),
                    job.get("started_at", time.time()), json.dumps(job.get("details", {})),
                ),
            )
        return self.get_job(job["id"]) or job

    def update_job(self, job_id: str, **fields: Any) -> dict[str, Any] | None:
        allowed = {
            "mode", "status", "phase", "progress", "completed_at", "duration_s",
            "files_processed", "symbols_extracted", "edges_resolved", "error",
        }
        values = {key: value for key, value in fields.items() if key in allowed}
        details = {key: value for key, value in fields.items() if key not in allowed}
        if details:
            current = self.get_job(job_id) or {}
            preserved = {
                key: value for key, value in current.items()
                if key not in allowed | {"id", "repo_id", "started_at"}
            }
            preserved.update(details)
            values["details"] = json.dumps(preserved)
        if values:
            assignments = ", ".join(f"{key} = ?" for key in values)
            with self._connect() as conn:
                conn.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", (*values.values(), job_id))
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row(row)

    def list_jobs(self, repo_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if repo_id:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE repo_id = ? ORDER BY started_at DESC LIMIT ?",
                    (repo_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM jobs ORDER BY started_at DESC LIMIT ?", (limit,)
                ).fetchall()
        return [self._row(row) for row in rows if row is not None]

    def latest_job(self, repo_id: str) -> dict[str, Any] | None:
        jobs = self.list_jobs(repo_id=repo_id, limit=1)
        return jobs[0] if jobs else None


registry = RegistryStore()
