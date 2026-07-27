"""SQLite-backed repository registry and pipeline job history."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from repolens.core.paths import repolens_project_root
from repolens.runtime.bootstrap import RuntimeLocator


def default_data_dir() -> Path:
    configured = os.environ.get("REPOLENS_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve() / "repositories"
    source_root = repolens_project_root()
    if (source_root / "pyproject.toml").is_file():
        return source_root / ".repolens" / "repositories"
    return RuntimeLocator.default_runtime() / "repositories"


class RegistryStore:
    """Durable server state shared by REST, scheduler, and MCP surfaces."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or default_data_dir() / "registry.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=FULL")
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
                    details TEXT NOT NULL DEFAULT '{}',
                    updated_at REAL,
                    lease_owner TEXT,
                    lease_expires_at REAL
                )"""
            )
            existing_job_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
            }
            for column, definition in {
                "updated_at": "REAL",
                "lease_owner": "TEXT",
                "lease_expires_at": "REAL",
            }.items():
                if column not in existing_job_columns:
                    conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} {definition}")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_repo ON jobs(repo_id, started_at DESC)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, lease_expires_at)"
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS mcp_sessions (
                    session_id TEXT PRIMARY KEY,
                    repo_id TEXT,
                    working_directory TEXT,
                    last_call_at REAL NOT NULL,
                    next_index_at REAL,
                    last_auto_index_at REAL,
                    claim_owner TEXT,
                    claim_expires_at REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )"""
            )
            conn.execute(
                """CREATE INDEX IF NOT EXISTS idx_mcp_sessions_due
                   ON mcp_sessions(next_index_at, claim_expires_at)"""
            )

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
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO jobs
                   (id, repo_id, mode, status, phase, progress, started_at, details, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job["id"], job["repo_id"], job["mode"], job.get("status", "running"),
                    job.get("phase", "starting"), job.get("progress", 0),
                    job.get("started_at", now), json.dumps(job.get("details", {})),
                    job.get("updated_at", now),
                ),
            )
        return self.get_job(job["id"]) or job

    def create_job_if_idle(self, job: dict[str, Any]) -> dict[str, Any] | None:
        """Atomically enqueue a job unless that repository already has active work."""
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            active = conn.execute(
                """SELECT id FROM jobs
                   WHERE repo_id = ? AND status IN ('queued', 'running')
                   LIMIT 1""",
                (job["repo_id"],),
            ).fetchone()
            if active:
                return None
            conn.execute(
                """INSERT INTO jobs
                   (id, repo_id, mode, status, phase, progress, started_at, details, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job["id"],
                    job["repo_id"],
                    job["mode"],
                    job.get("status", "queued"),
                    job.get("phase", "queued"),
                    job.get("progress", 0),
                    job.get("started_at", now),
                    json.dumps(job.get("details", {})),
                    now,
                ),
            )
        return self.get_job(job["id"])

    def update_job(self, job_id: str, **fields: Any) -> dict[str, Any] | None:
        allowed = {
            "mode", "status", "phase", "progress", "completed_at", "duration_s",
            "files_processed", "symbols_extracted", "edges_resolved", "error",
            "updated_at", "lease_owner", "lease_expires_at",
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
            values["updated_at"] = time.time()
            assignments = ", ".join(f"{key} = ?" for key in values)
            with self._connect() as conn:
                conn.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", (*values.values(), job_id))
        return self.get_job(job_id)

    def claim_job(self, job_id: str, owner: str, lease_seconds: float) -> dict[str, Any] | None:
        """Claim queued or abandoned work for one process."""
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                return None
            job = self._row(row)
            recoverable = job["status"] == "queued" or (
                job["status"] == "running"
                and (job.get("lease_expires_at") or 0) <= now
            )
            if not recoverable:
                return None
            conn.execute(
                """UPDATE jobs
                   SET status = 'running', phase = 'starting', lease_owner = ?,
                       lease_expires_at = ?, updated_at = ?
                   WHERE id = ?""",
                (owner, now + lease_seconds, now, job_id),
            )
        return self.get_job(job_id)

    def list_recoverable_jobs(self, limit: int = 100) -> list[dict[str, Any]]:
        now = time.time()
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM jobs
                   WHERE status = 'queued'
                      OR (status = 'running' AND COALESCE(lease_expires_at, 0) <= ?)
                   ORDER BY started_at
                   LIMIT ?""",
                (now, limit),
            ).fetchall()
        return [self._row(row) for row in rows if row is not None]

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

    def touch_mcp_session(
        self,
        session_id: str,
        repo_id: str | None,
        working_directory: str,
        delay_seconds: float = 600,
    ) -> dict[str, Any]:
        """Persist activity and debounce the session's next incremental index."""
        now = time.time()
        next_index_at = now + max(0, delay_seconds)
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO mcp_sessions
                   (session_id, repo_id, working_directory, last_call_at, next_index_at,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(session_id) DO UPDATE SET
                       repo_id = COALESCE(excluded.repo_id, mcp_sessions.repo_id),
                       working_directory = excluded.working_directory,
                       last_call_at = excluded.last_call_at,
                       next_index_at = excluded.next_index_at,
                       claim_owner = NULL,
                       claim_expires_at = NULL,
                       updated_at = excluded.updated_at""",
                (
                    session_id,
                    repo_id,
                    working_directory,
                    now,
                    next_index_at,
                    now,
                    now,
                ),
            )
        return self.get_mcp_session(session_id) or {
            "session_id": session_id,
            "repo_id": repo_id,
            "last_call_at": now,
            "next_index_at": next_index_at,
        }

    def set_mcp_session_context(
        self,
        session_id: str,
        repo_id: str | None = None,
        working_directory: str | None = None,
    ) -> dict[str, Any]:
        """Persist the active working repository for a session without queueing reindexing."""
        now = time.time()
        current = self.get_mcp_session(session_id)
        with self._connect() as conn:
            if current is None:
                conn.execute(
                    """INSERT INTO mcp_sessions
                       (session_id, repo_id, working_directory, last_call_at, next_index_at,
                        created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        session_id,
                        repo_id,
                        working_directory,
                        now,
                        None,
                        now,
                        now,
                    ),
                )
            else:
                conn.execute(
                    """UPDATE mcp_sessions
                       SET repo_id = COALESCE(?, repo_id),
                           working_directory = COALESCE(?, working_directory),
                           last_call_at = ?,
                           next_index_at = NULL,
                           claim_owner = NULL,
                           claim_expires_at = NULL,
                           updated_at = ?
                       WHERE session_id = ?""",
                    (repo_id, working_directory, now, now, session_id),
                )
        return self.get_mcp_session(session_id) or {
            "session_id": session_id,
            "repo_id": repo_id,
            "working_directory": working_directory,
            "last_call_at": now,
            "next_index_at": None,
        }

    def get_mcp_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM mcp_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return self._row(row)

    def claim_due_mcp_sessions(
        self,
        owner: str,
        lease_seconds: float = 60,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Atomically lease due session reindexes to one runtime."""
        now = time.time()
        claimed: list[dict[str, Any]] = []
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """SELECT * FROM mcp_sessions
                   WHERE next_index_at IS NOT NULL
                     AND next_index_at <= ?
                     AND (claim_expires_at IS NULL OR claim_expires_at <= ?)
                   ORDER BY next_index_at
                   LIMIT ?""",
                (now, now, limit),
            ).fetchall()
            for row in rows:
                updated = conn.execute(
                    """UPDATE mcp_sessions
                       SET claim_owner = ?, claim_expires_at = ?, updated_at = ?
                       WHERE session_id = ?
                         AND (claim_expires_at IS NULL OR claim_expires_at <= ?)""",
                    (owner, now + lease_seconds, now, row["session_id"], now),
                ).rowcount
                if updated:
                    claimed.append(self._row(row))
        return claimed

    def complete_mcp_session_index(
        self,
        session_id: str,
        owner: str,
        claimed_last_call_at: float,
    ) -> None:
        """Complete a lease without erasing activity that arrived after it was claimed."""
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """UPDATE mcp_sessions
                   SET next_index_at = CASE
                           WHEN last_call_at <= ? THEN NULL
                           ELSE next_index_at
                       END,
                       last_auto_index_at = ?,
                       claim_owner = NULL,
                       claim_expires_at = NULL,
                       updated_at = ?
                   WHERE session_id = ? AND claim_owner = ?""",
                (claimed_last_call_at, now, now, session_id, owner),
            )

    def release_mcp_session_index(
        self,
        session_id: str,
        owner: str,
        retry_seconds: float = 60,
    ) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """UPDATE mcp_sessions
                   SET next_index_at = ?,
                       claim_owner = NULL,
                       claim_expires_at = NULL,
                       updated_at = ?
                   WHERE session_id = ? AND claim_owner = ?""",
                (now + max(1, retry_seconds), now, session_id, owner),
            )


registry = RegistryStore()
