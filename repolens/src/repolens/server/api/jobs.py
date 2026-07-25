"""Durable pipeline job API."""

from fastapi import APIRouter, HTTPException, Query

from repolens.core.persistence import registry

router = APIRouter()


@router.get("/jobs")
async def list_jobs(repo_id: str | None = None, limit: int = Query(100, ge=1, le=500)):
    return registry.list_jobs(repo_id=repo_id, limit=limit)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = registry.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job


@router.get("/scheduler")
async def get_scheduler():
    return {
        "status": "configured",
        "note": "Scheduler execution history is recorded in /api/jobs.",
    }
