"""MCP tools for durable asynchronous repository indexing."""

from __future__ import annotations

from typing import Any

from repolens.core.pipeline.service import indexing_service
from repolens.core.pipeline.service import resolve_index_target

from .server import mcp, state


@mcp.tool()
async def index_current_directory(
    path: str | None = None,
    mode: str = "auto",
) -> dict[str, Any]:
    """Register and asynchronously index the MCP working directory.

    The default ``auto`` mode performs a full index when no durable index exists
    and an incremental index otherwise. The call returns immediately with a job
    ID; use ``get_index_status`` to monitor it. If ``path`` is omitted, RepoLens
    indexes its own package directory instead of the server process cwd.
    """
    target = resolve_index_target(path)
    return await state.run_sync(indexing_service.index_directory, target, mode)


@mcp.tool()
async def get_index_status(
    job_id: str | None = None,
    repo_id: str | None = None,
) -> dict[str, Any]:
    """Return durable status for an asynchronous index job."""

    def load() -> dict[str, Any]:
        from repolens.core.persistence import registry

        if job_id:
            job = registry.get_job(job_id)
            if not job:
                raise ValueError(f"Unknown index job: {job_id}")
            return job
        repo = state.repository(repo_id)
        return registry.latest_job(repo["id"]) or {
            "repo_id": repo["id"],
            "status": "idle",
            "phase": "idle",
            "progress": 0,
        }

    return await state.run_sync(load)
