"""HTTP/OpenAPI bridge for exercising RepoLens MCP tools."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from repolens.server.mcp.server import _format_mcp_arguments, mcp

router = APIRouter()


class MCPToolCall(BaseModel):
    tool: str = Field(description="Registered MCP tool name")
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments passed to the MCP tool",
    )


def _serialize_result(result: Any) -> Any:
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    if hasattr(result, "content"):
        content = []
        for item in result.content:
            if hasattr(item, "model_dump"):
                content.append(item.model_dump(mode="json"))
            else:
                content.append(str(item))
        return {"content": content}
    return str(result)


def _trace_http_call(
    phase: str,
    tool: str,
    arguments: dict[str, Any],
    *,
    duration_ms: float | None = None,
    error: str | None = None,
) -> None:
    parts = [
        f"[RepoLens MCP HTTP] {phase}",
        f"tool={tool}",
        f"args={_format_mcp_arguments(arguments)}",
    ]
    if duration_ms is not None:
        parts.append(f"duration_ms={duration_ms:.1f}")
    if error is not None:
        parts.append(f"error={error}")
    print(" ".join(parts), flush=True)


@router.get("/tools")
async def list_mcp_tools():
    """List MCP tools and their input schemas for interactive API testing."""
    tools = await mcp.list_tools()
    return {
        "count": len(tools),
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters,
            }
            for tool in tools
        ],
    }


@router.post("/call")
async def call_mcp_tool(request: MCPToolCall):
    """Call an MCP tool over HTTP and return its structured response."""
    started_at = time.perf_counter()
    _trace_http_call("start", request.tool, request.arguments)
    available = {tool.name for tool in await mcp.list_tools()}
    if request.tool not in available:
        duration_ms = (time.perf_counter() - started_at) * 1000
        _trace_http_call(
            "error",
            request.tool,
            request.arguments,
            duration_ms=duration_ms,
            error="Unknown tool",
        )
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"Unknown MCP tool: {request.tool}",
                "available_tools": sorted(available),
            },
        )
    try:
        result = await mcp.call_tool(request.tool, request.arguments)
    except (ValueError, FileNotFoundError) as exc:
        duration_ms = (time.perf_counter() - started_at) * 1000
        _trace_http_call(
            "error",
            request.tool,
            request.arguments,
            duration_ms=duration_ms,
            error=f"{exc.__class__.__name__}: {exc}",
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        duration_ms = (time.perf_counter() - started_at) * 1000
        _trace_http_call(
            "error",
            request.tool,
            request.arguments,
            duration_ms=duration_ms,
            error=f"{exc.__class__.__name__}: {exc}",
        )
        raise HTTPException(
            status_code=500,
            detail=f"MCP tool '{request.tool}' failed: {exc}",
        ) from exc
    duration_ms = (time.perf_counter() - started_at) * 1000
    _trace_http_call(
        "done",
        request.tool,
        request.arguments,
        duration_ms=duration_ms,
    )
    return {
        "tool": request.tool,
        "arguments": request.arguments,
        "result": _serialize_result(result),
    }
