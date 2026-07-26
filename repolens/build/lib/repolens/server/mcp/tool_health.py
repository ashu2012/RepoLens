"""MCP tools for persisted index health."""

import json
import time

from .server import mcp, state


@mcp.tool()
async def get_health(repo_id: str | None = None) -> str:
    def check():
        repo = state.repository(repo_id)
        stats = state.index(repo["id"]).store.get_stats()
        stats["repo_id"] = repo["id"]
        stats["status"] = repo["status"]
        stats["staleness_seconds"] = (
            round(time.time() - repo["last_indexed"], 2) if repo.get("last_indexed") else None
        )
        return stats

    stats = await state.run_sync(check)
    return json.dumps(stats, indent=2)


@mcp.tool()
async def list_repos() -> str:
    from repolens.core.persistence import registry

    repos = await state.run_sync(registry.list_repos)
    return json.dumps(repos, indent=2)
