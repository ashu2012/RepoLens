"""MCP tools for persisted index health."""

import json
import time

from .server import mcp, state


@mcp.tool()
async def get_health(repo_id: str | None = None) -> str:
    from repolens.core.persistence import registry

    def collect() -> dict[str, object]:
        if repo_id is None:
            repo = state.active_repository()
            if repo is None:
                raise ValueError("No working repository is available")
        else:
            try:
                repo = state.repository(repo_id)
            except ValueError:
                repo = registry.get_repo(repo_id)
                if repo is None:
                    raise ValueError(f"Unknown repository: {repo_id}")
        stats = {
            "repo_id": repo["id"],
            "status": repo["status"],
            "staleness_seconds": (
                round(time.time() - repo["last_indexed"], 2) if repo.get("last_indexed") else None
            ),
            "ready": repo["status"] == "indexed",
        }
        try:
            stats.update(state.index(repo["id"]).stats())
        except Exception as exc:
            stats["ready"] = False
            stats["note"] = "Index data is temporarily busy or unavailable; returning registry metadata only."
            stats["error"] = str(exc)
        return stats

    stats = await state.run_sync(collect)
    return json.dumps(stats, indent=2)


@mcp.tool()
async def list_repos() -> str:
    from repolens.core.persistence import registry

    repos = await state.run_sync(registry.list_repos)
    return json.dumps(repos, indent=2)
