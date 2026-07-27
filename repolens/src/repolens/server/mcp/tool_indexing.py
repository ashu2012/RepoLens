"""MCP tools for durable asynchronous repository indexing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from repolens.core.pipeline.service import indexing_service
from repolens.core.pipeline.service import resolve_index_target
from repolens.core.paths import repolens_cleanup_staging_indexes
from repolens.core.paths import repolens_current_index_path

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


def _repo_payload(repo: dict[str, Any], *, registered: bool = False) -> dict[str, Any]:
    index_path = repolens_current_index_path(repo["local_path"])
    return {
        "repo_id": repo["id"],
        "repository": repo["name"],
        "local_path": repo["local_path"],
        "repository_status": repo.get("status"),
        "registered": registered,
        "indexed": index_path is not None,
        "index_path": str(index_path) if index_path else None,
        "session_id": state.session_id(),
    }


@mcp.tool()
async def get_working_repository() -> dict[str, Any]:
    """Return the repository currently selected for this MCP session, if any."""
    repo = await state.run_sync(state.active_repository)
    if repo is None:
        return {
            "status": "no_active_repository",
            "repo": None,
            "session_id": state.session_id(),
        }
    return {
        "status": "active_repository",
        **_repo_payload(repo),
    }


@mcp.tool()
async def switch_working_repository(
    repo_id: str | None = None,
    path: str | None = None,
    register: bool = False,
) -> dict[str, Any]:
    """Switch the current MCP session to a repository or project directory."""
    repo, registered = await state.run_sync(
        state.set_active_repository,
        repo_id,
        path=path,
        register=register,
    )
    return {
        "status": "repository_selected",
        "registered": registered,
        **_repo_payload(repo),
        "session": repo.get("mcp_session"),
    }


@mcp.tool()
async def index_repository(
    repo_id: str | None = None,
    path: str | None = None,
    mode: str = "auto",
    register: bool = True,
) -> dict[str, Any]:
    """Select a repository and queue a durable index job for it."""
    repo, registered = await state.run_sync(
        state.set_active_repository,
        repo_id,
        path=path,
        register=register,
    )
    job, created = await state.run_sync(
        indexing_service.start_index,
        repo["id"],
        mode,
        trigger="mcp",
        session_id=state.session_id(),
    )
    return {
        "status": "indexing_started" if created else "indexing_already_active",
        "registered": registered,
        **_repo_payload(repo),
        "session": repo.get("mcp_session"),
        "job_id": job["id"],
        "job_status": job["status"],
        "mode": job["mode"],
    }


@mcp.tool()
async def reindex_repository(
    repo_id: str | None = None,
    path: str | None = None,
    mode: str = "full",
    register: bool = True,
) -> dict[str, Any]:
    """Force a full or incremental rebuild for the selected repository."""
    return await index_repository(repo_id=repo_id, path=path, mode=mode, register=register)


@mcp.tool()
async def cleanup_staging_artifacts(
    repo_id: str | None = None,
    path: str | None = None,
    all_repos: bool = False,
) -> dict[str, Any]:
    """Remove staging copies for one repository or every idle repository."""

    def load() -> dict[str, Any]:
        from repolens.core.persistence import registry

        if all_repos:
            if repo_id is not None or path is not None:
                raise ValueError("all_repos cannot be combined with repo_id or path")
            removed = indexing_service.prune_staging_artifacts()
            return {
                "status": "cleanup_completed",
                "scope": "all_repositories",
                "removed": removed,
                "session_id": state.session_id(),
            }

        if path is not None:
            target = Path(path).expanduser().resolve()
            if not target.exists():
                raise ValueError(f"Path does not exist: {target}")
            if not target.is_dir():
                raise ValueError(f"Path is not a directory: {target}")
            removed = repolens_cleanup_staging_indexes(target)
            return {
                "status": "cleanup_completed",
                "scope": "path",
                "removed": removed,
                "local_path": str(target),
                "repo_id": repo_id,
                "session_id": state.session_id(),
            }

        if repo_id is not None:
            repo = registry.get_repo(repo_id)
            if repo is None:
                raise ValueError(f"Unknown repository: {repo_id}")
        else:
            repo = state.active_repository()
            if repo is None:
                raise ValueError("No repository is available to clean up")

        removed = repolens_cleanup_staging_indexes(repo["local_path"])
        return {
            "status": "cleanup_completed",
            "scope": "repository",
            "removed": removed,
            **_repo_payload(repo),
        }

    return await state.run_sync(load)


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
        if repo_id is None:
            repo = state.active_repository()
            if repo is None:
                return {
                    "status": "idle",
                    "phase": "idle",
                    "progress": 0,
                    "repo_id": None,
                }
        else:
            repo = registry.get_repo(repo_id)
            if repo is None:
                raise ValueError(f"Unknown repository: {repo_id}")
        return registry.latest_job(repo["id"]) or {
            "repo_id": repo["id"],
            "status": "idle",
            "phase": "idle",
            "progress": 0,
        }

    return await state.run_sync(load)
