"""Index-backed MCP search tools."""

import json
from typing import Optional

from .server import mcp, state


@mcp.tool()
async def search_semantic(
    query: str, top_k: int = 10, mode: str = "hybrid", repo_id: str | None = None
) -> str:
    async def search():
        repo = state.repository(repo_id)
        return await state.index(repo["id"]).search(query, mode=mode, top_k=top_k)

    try:
        results = await state.run_async_worker(search)
    except Exception as exc:
        return json.dumps(
            {
                "results": [],
                "ready": False,
                "error": str(exc),
                "note": "Semantic search could not finish right now; please try again shortly.",
            },
            indent=2,
        )
    return json.dumps(results, indent=2)


@mcp.tool()
async def search_symbols(
    name: str, kind: Optional[str] = None, repo_id: str | None = None
) -> str:
    try:
        results = await state.run_sync(
            lambda: state.index(state.repository(repo_id)["id"]).symbols(name, kind=kind)
        )
    except Exception as exc:
        return json.dumps(
            {
                "results": [],
                "ready": False,
                "error": str(exc),
                "note": "Symbol search could not complete right now; please try again shortly.",
            },
            indent=2,
        )
    return json.dumps(results, indent=2)
