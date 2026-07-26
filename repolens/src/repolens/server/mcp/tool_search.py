"""Index-backed MCP search tools."""

import json
from typing import Optional

from .server import mcp, state


@mcp.tool()
async def search_semantic(
    query: str, top_k: int = 10, mode: str = "hybrid", repo_id: str | None = None
) -> str:
    async def search():
        return await state.index(repo_id).search(query, mode=mode, top_k=top_k)

    results = await state.run_async_worker(search)
    return json.dumps(results, indent=2)


@mcp.tool()
async def search_symbols(
    name: str, kind: Optional[str] = None, repo_id: str | None = None
) -> str:
    results = await state.run_sync(lambda: state.index(repo_id).symbols(name, kind=kind))
    return json.dumps(results, indent=2)
