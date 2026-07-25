"""MCP tools for persisted index health."""

import json
import time

from repolens.core.persistence import registry

from .server import mcp, state


@mcp.tool()
async def get_health(repo_id: str | None = None) -> str:
    repo = state.repository(repo_id)
    stats = state.index(repo["id"]).store.get_stats()
    stats["repo_id"] = repo["id"]
    stats["status"] = repo["status"]
    stats["staleness_seconds"] = (
        round(time.time() - repo["last_indexed"], 2) if repo.get("last_indexed") else None
    )
    return json.dumps(stats, indent=2)


@mcp.tool()
async def list_repos() -> str:
    return json.dumps(registry.list_repos(), indent=2)
