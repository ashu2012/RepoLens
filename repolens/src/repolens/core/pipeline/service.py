"""Durable, multi-threaded repository indexing service."""

from __future__ import annotations

import asyncio
import os
import socket
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

import structlog

from repolens.core.graph.store import GraphStore
from repolens.core.paths import (
    repolens_current_index_path,
    repolens_package_root,
    repolens_publish_active_index,
    repolens_staging_index_path,
)

logger = structlog.get_logger(__name__)


def _registry():
    # Resolve dynamically so tests and embedded hosts can replace the registry.
    from repolens.core.persistence import registry

    return registry


def resolve_index_target(path: str | Path | None = None) -> Path:
    """Resolve an indexing target without falling back to the caller's cwd."""
    if path is not None:
        return Path(path).expanduser().resolve()
    return repolens_package_root()


class IndexingService:
    """Runs durable index jobs outside protocol and Web event loops."""

    def __init__(
        self,
        index_workers: int | None = None,
        poll_interval: float | None = None,
        lease_seconds: float | None = None,
    ) -> None:
        cpu_count = os.cpu_count() or 2
        self.index_workers = index_workers or int(
            os.environ.get("REPOLENS_INDEX_WORKERS", min(4, max(2, cpu_count // 2)))
        )
        self.poll_interval = poll_interval or float(
            os.environ.get("REPOLENS_INDEX_POLL_SECONDS", "2")
        )
        self.lease_seconds = lease_seconds or float(
            os.environ.get("REPOLENS_INDEX_LEASE_SECONDS", "900")
        )
        self.owner = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self._executor: ThreadPoolExecutor | None = None
        self._futures: dict[str, Future] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._dispatcher: threading.Thread | None = None

    def _ensure_executor(self) -> ThreadPoolExecutor:
        with self._lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=max(1, self.index_workers),
                    thread_name_prefix="repolens-index",
                )
            return self._executor

    @staticmethod
    def _active_index_path(repo_path: str | Path) -> Path | None:
        return repolens_current_index_path(repo_path)

    @staticmethod
    def _staging_index_path(repo_path: str | Path, job_id: str) -> Path:
        return repolens_staging_index_path(repo_path, job_id)

    @staticmethod
    def _publish_index(repo_path: str | Path, staged_index: str | Path) -> Path:
        return repolens_publish_active_index(repo_path, staged_index)

    def start_runtime(self) -> None:
        """Start recovery and delayed-session dispatch in a daemon thread."""
        self._ensure_executor()
        with self._lock:
            if self._dispatcher and self._dispatcher.is_alive():
                return
            self._stop_event.clear()
            self._dispatcher = threading.Thread(
                target=self._dispatch_loop,
                name="repolens-index-dispatcher",
                daemon=True,
            )
            self._dispatcher.start()

    def stop_runtime(self) -> None:
        """Stop dispatching; submitted jobs remain durable and finish when possible."""
        self._stop_event.set()
        dispatcher = self._dispatcher
        if dispatcher and dispatcher.is_alive():
            dispatcher.join(timeout=min(2.0, self.poll_interval + 0.5))
        with self._lock:
            self._dispatcher = None
            executor = self._executor
            self._executor = None
        if executor:
            executor.shutdown(wait=False, cancel_futures=False)

    def _dispatch_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.dispatch_recoverable_jobs()
                self.process_due_sessions()
            except Exception:
                logger.exception("index_dispatch_failed")
            self._stop_event.wait(max(0.05, self.poll_interval))

    def dispatch_recoverable_jobs(self) -> None:
        """Resume queued jobs and jobs whose prior worker lease expired."""
        for job in _registry().list_recoverable_jobs():
            self._submit(job["id"])

    def _submit(self, job_id: str, *, claimed: bool = False) -> Future:
        with self._lock:
            existing = self._futures.get(job_id)
            if existing and not existing.done():
                return existing
            cancel_event = self._cancel_events.setdefault(job_id, threading.Event())
            future = self._ensure_executor().submit(
                self._run_job, job_id, cancel_event, claimed
            )
            self._futures[job_id] = future
            future.add_done_callback(lambda completed, current=job_id: self._finished(current))
            return future

    def _finished(self, job_id: str) -> None:
        with self._lock:
            self._futures.pop(job_id, None)
            self._cancel_events.pop(job_id, None)

    def start_index(
        self,
        repo_id: str,
        mode: str = "incremental",
        *,
        trigger: str = "manual",
        session_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Atomically enqueue an index and return ``(job, created)``."""
        store = _registry()
        repo = store.get_repo(repo_id)
        if not repo:
            raise ValueError(f"Unknown repository: {repo_id}")
        if mode not in {"full", "incremental", "auto"}:
            raise ValueError("mode must be full, incremental, or auto")
        index_exists = self._active_index_path(repo["local_path"]) is not None
        resolved_mode = ("incremental" if index_exists else "full") if mode == "auto" else mode
        if resolved_mode == "incremental" and not index_exists:
            resolved_mode = "full"

        job_id = uuid.uuid4().hex[:12]
        job = store.create_job_if_idle(
            {
                "id": job_id,
                "repo_id": repo_id,
                "mode": resolved_mode,
                "status": "queued",
                "phase": "queued",
                "progress": 0,
                "started_at": time.time(),
                "details": {
                    "trigger": trigger,
                    "session_id": session_id,
                    "worker_owner": self.owner,
                },
            }
        )
        if job is None:
            active = store.latest_job(repo_id)
            if not active:
                raise RuntimeError("Index job could not be enqueued")
            return active, False
        claimed_job = store.claim_job(job_id, self.owner, self.lease_seconds)
        if not claimed_job:
            raise RuntimeError(f"Index job could not be claimed: {job_id}")
        store.update_repo(repo_id, status="indexing")
        self._submit(job_id, claimed=True)
        return store.get_job(job_id) or claimed_job, True

    def ensure_repository(self, path: str | Path | None = None) -> tuple[dict[str, Any], bool]:
        """Register a directory if it is not already in the durable registry."""
        root = Path(path or ".").expanduser().resolve()
        if not root.exists():
            raise ValueError(f"Path does not exist: {root}")
        if not root.is_dir():
            raise ValueError(f"Path is not a directory: {root}")
        store = _registry()
        existing = store.find_repo_by_path(str(root))
        if existing:
            return existing, False

        ignored = {".git", ".repolens", "__pycache__", "node_modules", ".venv", "venv"}
        files_count = sum(
            1
            for candidate in root.rglob("*")
            if candidate.is_file() and not ignored.intersection(candidate.parts)
        )
        index_exists = self._active_index_path(root) is not None
        repo = store.add_repo(
            {
                "id": uuid.uuid4().hex[:12],
                "name": root.name,
                "local_path": str(root),
                "status": "indexed" if index_exists else "registered",
                "files_count": files_count,
                "is_git": (root / ".git").exists(),
                "created_at": time.time(),
            }
        )
        return repo, True

    def index_directory(
        self,
        path: str | Path | None = None,
        mode: str = "auto",
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        repo, registered = self.ensure_repository(resolve_index_target(path))
        job, created = self.start_index(
            repo["id"],
            mode,
            trigger="mcp",
            session_id=session_id,
        )
        return {
            "status": "indexing_started" if created else "indexing_already_active",
            "registered": registered,
            "repo_id": repo["id"],
            "repository": repo["name"],
            "local_path": repo["local_path"],
            "job_id": job["id"],
            "mode": job["mode"],
            "job_status": job["status"],
            "durable_registry": str(_registry().db_path),
            "durable_index": str(self._active_index_path(repo["local_path"]) or (
                Path(repo["local_path"]) / ".repolens" / "index.db"
            )),
        }

    def cancel(self, job_id: str) -> bool:
        store = _registry()
        job = store.get_job(job_id)
        if not job or job["status"] not in {"queued", "running"}:
            return False
        with self._lock:
            event = self._cancel_events.setdefault(job_id, threading.Event())
            event.set()
            future = self._futures.get(job_id)
            if future:
                future.cancel()
        store.update_job(
            job_id,
            status="cancelled",
            phase="cancelled",
            completed_at=time.time(),
            lease_owner=None,
            lease_expires_at=None,
        )
        store.update_repo(job["repo_id"], status="cancelled")
        return True

    def wait(self, job_id: str, timeout: float = 60) -> dict[str, Any] | None:
        with self._lock:
            future = self._futures.get(job_id)
        if future:
            future.result(timeout=timeout)
        return _registry().get_job(job_id)

    def _run_job(
        self,
        job_id: str,
        cancel_event: threading.Event,
        claimed: bool = False,
    ) -> None:
        store = _registry()
        job = store.get_job(job_id) if claimed else store.claim_job(
            job_id, self.owner, self.lease_seconds
        )
        if job and claimed and job.get("lease_owner") != self.owner:
            job = None
        if not job:
            return
        repo = store.get_repo(job["repo_id"])
        if not repo:
            store.update_job(
                job_id,
                status="failed",
                phase="error",
                error=f"Repository was removed: {job['repo_id']}",
                completed_at=time.time(),
                lease_owner=None,
                lease_expires_at=None,
            )
            return
        started_at = time.time()

        def progress(phase: str, percentage: int) -> None:
            persisted = store.get_job(job_id)
            if persisted and persisted["status"] == "cancelled":
                cancel_event.set()
            if cancel_event.is_set():
                return
            store.update_job(
                job_id,
                phase=phase,
                progress=percentage,
                lease_owner=self.owner,
                lease_expires_at=time.time() + self.lease_seconds,
            )

        try:
            from repolens.core.pipeline.orchestrator import PipelineOrchestrator

            orchestrator = PipelineOrchestrator()
            staged_index = self._staging_index_path(repo["local_path"], job_id)
            staged_index.parent.mkdir(parents=True, exist_ok=True)
            if job["mode"] == "full":
                result = asyncio.run(
                    orchestrator.run_full(
                        repo["local_path"],
                        progress,
                        index_path=staged_index,
                    )
                )
            else:
                live_index = self._active_index_path(repo["local_path"])
                if live_index is not None and live_index.exists():
                    GraphStore(live_index, read_only=True).copy_to(staged_index)
                result = asyncio.run(
                    orchestrator.run_incremental(
                        repo["local_path"],
                        None,
                        progress,
                        index_path=staged_index,
                    )
                )
            persisted = store.get_job(job_id)
            if persisted and persisted["status"] == "cancelled":
                cancel_event.set()
            if cancel_event.is_set():
                store.update_job(
                    job_id,
                    status="cancelled",
                    phase="cancelled",
                    completed_at=time.time(),
                    lease_owner=None,
                    lease_expires_at=None,
                )
                store.update_repo(repo["id"], status="cancelled")
                return

            published_index = self._publish_index(repo["local_path"], staged_index)

            completed_at = time.time()
            stats = result.stats
            store.update_job(
                job_id,
                status="completed",
                phase="complete",
                progress=100,
                completed_at=completed_at,
                duration_s=result.duration_s,
                files_processed=result.files_processed,
                symbols_extracted=result.symbols_extracted,
                edges_resolved=result.edges_resolved,
                chunks_indexed=stats.get("total_chunks", 0),
                index_path=str(published_index),
                lease_owner=None,
                lease_expires_at=None,
            )
            store.update_repo(
                repo["id"],
                status="indexed",
                last_indexed=completed_at,
                index_duration_s=result.duration_s,
                symbols_count=stats.get("total_nodes", result.symbols_extracted),
                edges_count=stats.get("total_edges", result.edges_resolved),
                chunks_count=stats.get("total_chunks", 0),
            )
        except Exception as exc:
            store.update_job(
                job_id,
                status="failed",
                phase="error",
                error=str(exc),
                completed_at=time.time(),
                duration_s=time.time() - started_at,
                lease_owner=None,
                lease_expires_at=None,
            )
            store.update_repo(repo["id"], status="error")
            logger.exception("index_job_failed", job_id=job_id, repo_path=repo["local_path"])

    def record_mcp_activity(
        self,
        session_id: str,
        repo_id: str | None,
        working_directory: str | Path,
        delay_seconds: float | None = None,
    ) -> dict[str, Any]:
        delay = (
            float(os.environ.get("REPOLENS_AUTO_INDEX_DELAY_SECONDS", "600"))
            if delay_seconds is None
            else delay_seconds
        )
        return _registry().touch_mcp_session(
            session_id,
            repo_id,
            str(Path(working_directory).resolve()),
            delay,
        )

    def process_due_sessions(self) -> int:
        """Queue due debounced reindexes. Safe to call from multiple processes."""
        store = _registry()
        claimed = store.claim_due_mcp_sessions(self.owner)
        queued = 0
        for session in claimed:
            repo_id = session.get("repo_id")
            if not repo_id and session.get("working_directory"):
                repo = store.find_repo_by_path(
                    str(Path(session["working_directory"]).expanduser().resolve())
                )
                repo_id = repo["id"] if repo else None
            if not repo_id or not store.get_repo(repo_id):
                store.complete_mcp_session_index(
                    session["session_id"], self.owner, session["last_call_at"]
                )
                continue
            try:
                _, created = self.start_index(
                    repo_id,
                    "auto",
                    trigger="mcp-auto",
                    session_id=session["session_id"],
                )
                if created:
                    queued += 1
                    store.complete_mcp_session_index(
                        session["session_id"], self.owner, session["last_call_at"]
                    )
                else:
                    store.release_mcp_session_index(session["session_id"], self.owner)
            except Exception:
                store.release_mcp_session_index(session["session_id"], self.owner)
                logger.exception(
                    "mcp_auto_index_failed",
                    session_id=session["session_id"],
                    repo_id=repo_id,
                )
        return queued


indexing_service = IndexingService()
