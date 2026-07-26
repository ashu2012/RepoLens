"""Dashboard route handler for RepoLens.

Serves the self-hosted HTML dashboard with panels for all subsystems:
pipeline status, MCP performance, RAG quality, token savings, index health,
and cron schedule. Acts as the common UI with links to all project parts.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["dashboard"])

_TEMPLATE_DIR = Path(__file__).parent.parent.parent.parent / "templates"


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Serve the main RepoLens dashboard."""
    template_path = _TEMPLATE_DIR / "dashboard.html"
    if template_path.exists():
        content = template_path.read_text(encoding="utf-8")
        return HTMLResponse(content=content)
    return HTMLResponse(content=_FALLBACK_DASHBOARD)


@router.get("/api/dashboard/data")
async def dashboard_data():
    """API endpoint returning live dashboard metrics as JSON."""
    from repolens.observability.metrics import metrics
    from repolens.observability.health import health

    return {
        "health": health.full_status(),
        "metrics": metrics.get_dashboard_data(),
    }


# Inline fallback dashboard if template file is missing
_FALLBACK_DASHBOARD = """<!DOCTYPE html>
<html><head><title>RepoLens Dashboard</title>
<style>body{font-family:sans-serif;background:#111;color:#eee;padding:2rem;}
h1{color:#60a5fa;}a{color:#34d399;}</style></head>
<body><h1>RepoLens Dashboard</h1><p>Template not found. Run from project root.</p></body></html>"""
