"""Persistent repository management and indexing API."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from repolens.core.persistence import registry

logger = logging.getLogger(__name__)
router = APIRouter()

# Background tasks are process-local; their state and results are durable.
_tasks: dict[str, asyncio.Task] = {}


class RepoCreate(BaseModel):
    local_path: str
    name: Optional[str] = None


class RepoResponse(BaseModel):
    id: str
    name: str
    local_path: str
    status: str
    files_count: int
    last_indexed: Optional[float]
    index_duration_s: Optional[float]


def _count_files(root: Path) -> int:
    ignored = {".git", ".repolens", "__pycache__", "node_modules", ".venv", "venv"}
    return sum(
        1 for path in root.rglob("*")
        if path.is_file() and not ignored.intersection(path.parts)
    )


@router.post("", response_model=RepoResponse)
async def add_repo(repo: RepoCreate):
    repo_path = Path(repo.local_path).expanduser().resolve()
    if not repo_path.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {repo_path}")
    if not repo_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {repo_path}")
    if registry.find_repo_by_path(str(repo_path)):
        raise HTTPException(status_code=409, detail=f"Repository already registered: {repo_path}")

    entry = registry.add_repo(
        {
            "id": uuid.uuid4().hex[:12],
            "name": repo.name or repo_path.name,
            "local_path": str(repo_path),
            "status": "registered",
            "files_count": _count_files(repo_path),
            "is_git": (repo_path / ".git").exists(),
            "created_at": time.time(),
        }
    )
    logger.info("Repository added: %s (%s)", entry["name"], repo_path)
    return RepoResponse(**entry)


@router.get("")
async def list_repos():
    result = []
    for repo in registry.list_repos():
        latest = registry.latest_job(repo["id"])
        if latest and latest["status"] == "running":
            repo = {**repo, "status": f"indexing ({latest['phase']})"}
        result.append(repo)
    return result


@router.get("/{repo_id}")
async def get_repo(repo_id: str):
    repo = registry.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository not found: {repo_id}")
    latest = registry.latest_job(repo_id)
    return {**repo, "pipeline": latest} if latest else repo


@router.post("/{repo_id}/index")
async def index_repo(repo_id: str, mode: str = "incremental"):
    repo = registry.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository not found: {repo_id}")
    if mode not in {"full", "incremental"}:
        raise HTTPException(status_code=400, detail="mode must be 'full' or 'incremental'")
    latest = registry.latest_job(repo_id)
    if latest and latest["status"] == "running":
        raise HTTPException(status_code=409, detail="Pipeline already running for this repo")

    job_id = uuid.uuid4().hex[:12]
    registry.create_job(
        {
            "id": job_id,
            "repo_id": repo_id,
            "mode": mode,
            "status": "running",
            "phase": "starting",
            "progress": 0,
            "started_at": time.time(),
        }
    )
    registry.update_repo(repo_id, status="indexing")
    _tasks[job_id] = asyncio.create_task(_run_pipeline(job_id, repo_id, repo["local_path"], mode))
    return {"status": "indexing_started", "repo_id": repo_id, "job_id": job_id, "mode": mode}


@router.post("/{repo_id}/stop")
async def stop_pipeline(repo_id: str):
    if not registry.get_repo(repo_id):
        raise HTTPException(status_code=404, detail=f"Repository not found: {repo_id}")
    job = registry.latest_job(repo_id)
    if not job or job["status"] != "running":
        raise HTTPException(status_code=409, detail="No active pipeline to stop")
    task = _tasks.get(job["id"])
    if task:
        task.cancel()
    registry.update_job(
        job["id"], status="cancelled", phase="cancelled", completed_at=time.time()
    )
    registry.update_repo(repo_id, status="cancelled")
    return {"status": "stopped", "repo_id": repo_id, "job_id": job["id"]}


@router.delete("/{repo_id}")
async def remove_repo(repo_id: str):
    repo = registry.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository not found: {repo_id}")
    job = registry.latest_job(repo_id)
    if job and job["status"] == "running":
        task = _tasks.get(job["id"])
        if task:
            task.cancel()
    registry.remove_repo(repo_id)
    return {"status": "removed", "repo_id": repo_id, "name": repo["name"]}


@router.get("/{repo_id}/pipeline")
async def get_pipeline_status(repo_id: str):
    if not registry.get_repo(repo_id):
        raise HTTPException(status_code=404, detail=f"Repository not found: {repo_id}")
    return registry.latest_job(repo_id) or {"status": "idle", "repo_id": repo_id}


async def _run_pipeline(job_id: str, repo_id: str, repo_path: str, mode: str) -> None:
    from repolens.core.pipeline.orchestrator import PipelineOrchestrator

    started_at = time.time()

    def progress(phase: str, percentage: int) -> None:
        registry.update_job(job_id, phase=phase, progress=percentage)

    try:
        orchestrator = PipelineOrchestrator()
        if mode == "full":
            result = await orchestrator.run_full(repo_path, progress)
        else:
            result = await orchestrator.run_incremental(repo_path, None, progress)
        completed_at = time.time()
        stats = result.stats
        registry.update_job(
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
            index_path=str(Path(repo_path) / ".repolens" / "index.db"),
        )
        registry.update_repo(
            repo_id,
            status="indexed",
            last_indexed=completed_at,
            index_duration_s=result.duration_s,
            symbols_count=result.symbols_extracted,
            edges_count=result.edges_resolved,
            chunks_count=stats.get("total_chunks", 0),
        )
    except asyncio.CancelledError:
        registry.update_job(
            job_id, status="cancelled", phase="cancelled", completed_at=time.time()
        )
        registry.update_repo(repo_id, status="cancelled")
    except Exception as exc:
        registry.update_job(
            job_id,
            status="failed",
            phase="error",
            error=str(exc),
            completed_at=time.time(),
            duration_s=time.time() - started_at,
        )
        registry.update_repo(repo_id, status="error")
        logger.exception("Pipeline failed for %s", repo_path)
    finally:
        _tasks.pop(job_id, None)
