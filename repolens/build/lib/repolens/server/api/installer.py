"""Post-installation and MCP configuration endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from repolens.server.installer import SUPPORTED_MCP_CLIENTS, generate_mcp_config

router = APIRouter()


@router.get("/clients")
async def clients() -> dict:
    return {"clients": SUPPORTED_MCP_CLIENTS}


@router.get("/mcp-config/{client}")
async def mcp_config(client: str, install_path: str | None = Query(default=None)) -> dict:
    try:
        return generate_mcp_config(client, install_path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
