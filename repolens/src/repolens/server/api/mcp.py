"""HTTP/OpenAPI bridge for exercising RepoLens MCP tools."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from repolens.server.mcp.server import mcp

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
    available = {tool.name for tool in await mcp.list_tools()}
    if request.tool not in available:
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
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"MCP tool '{request.tool}' failed: {exc}",
        ) from exc
    return {
        "tool": request.tool,
        "arguments": request.arguments,
        "result": _serialize_result(result),
    }
