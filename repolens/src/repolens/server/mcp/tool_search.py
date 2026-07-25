"""Index-backed MCP search tools."""

import json
from typing import Optional

from .server import mcp, state


@mcp.tool()
async def search_semantic(
    query: str, top_k: int = 10, mode: str = "hybrid", repo_id: str | None = None
) -> str:
    results = await state.index(repo_id).search(query, mode=mode, top_k=top_k)
    return json.dumps(results, indent=2)


@mcp.tool()
async def search_symbols(
    name: str, kind: Optional[str] = None, repo_id: str | None = None
) -> str:
    return json.dumps(state.index(repo_id).symbols(name, kind=kind), indent=2)
