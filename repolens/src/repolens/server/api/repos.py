"""Persistent repository management and indexing API."""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from repolens.core.discovery import count_indexable_files
from repolens.core.pipeline.service import indexing_service
from repolens.core.persistence import registry

logger = logging.getLogger(__name__)
router = APIRouter()

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
    from repolens.core.ingestion.parser import CodeParser

    return count_indexable_files(root, CodeParser.SUPPORTED_EXTENSIONS)


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
    try:
        job, created = indexing_service.start_index(repo_id, mode, trigger="web")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not created:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Pipeline already running for this repo",
                "job_id": job["id"],
                "status": job["status"],
            },
        )
    return {
        "status": "indexing_started",
        "repo_id": repo_id,
        "job_id": job["id"],
        "mode": job["mode"],
    }


@router.post("/{repo_id}/stop")
async def stop_pipeline(repo_id: str):
    if not registry.get_repo(repo_id):
        raise HTTPException(status_code=404, detail=f"Repository not found: {repo_id}")
    job = registry.latest_job(repo_id)
    if not job or job["status"] not in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="No active pipeline to stop")
    indexing_service.cancel(job["id"])
    return {"status": "stopped", "repo_id": repo_id, "job_id": job["id"]}


@router.delete("/{repo_id}")
async def remove_repo(repo_id: str):
    repo = registry.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository not found: {repo_id}")
    job = registry.latest_job(repo_id)
    if job and job["status"] in {"queued", "running"}:
        indexing_service.cancel(job["id"])
    registry.remove_repo(repo_id)
    return {"status": "removed", "repo_id": repo_id, "name": repo["name"]}


@router.get("/{repo_id}/pipeline")
async def get_pipeline_status(repo_id: str):
    if not registry.get_repo(repo_id):
        raise HTTPException(status_code=404, detail=f"Repository not found: {repo_id}")
    return registry.latest_job(repo_id) or {"status": "idle", "repo_id": repo_id}
