"""Index-backed MCP graph tools."""

import json

from .server import mcp, state


def _related(symbol: str, direction: str, kind: str | None, repo_id: str | None) -> str:
    repo = state.repository(repo_id)
    try:
        return json.dumps(state.index(repo["id"]).related(symbol, direction, kind), indent=2)
    except Exception as exc:
        return json.dumps(
            {
                "ready": False,
                "results": [],
                "error": str(exc),
                "note": "Graph query could not complete right now; try again shortly.",
            },
            indent=2,
        )


@mcp.tool()
async def find_callers(symbol: str, repo_id: str | None = None) -> str:
    return await state.run_sync(_related, symbol, "in", "CALLS", repo_id)


@mcp.tool()
async def find_callees(symbol: str, repo_id: str | None = None) -> str:
    return await state.run_sync(_related, symbol, "out", "CALLS", repo_id)


@mcp.tool()
async def query_graph(
    pattern: str, target: str, repo_id: str | None = None
) -> str:
    patterns = {
        "callers_of": ("in", "CALLS"),
        "callees_of": ("out", "CALLS"),
        "imports_of": ("out", "IMPORTS_FROM"),
        "importers_of": ("in", "IMPORTS_FROM"),
        "children_of": ("out", "CONTAINS"),
        "parents_of": ("in", "CONTAINS"),
    }
    if pattern not in patterns:
        raise ValueError(f"Unsupported pattern. Choose one of: {', '.join(patterns)}")
    direction, kind = patterns[pattern]
    return await state.run_sync(_related, target, direction, kind, repo_id)
