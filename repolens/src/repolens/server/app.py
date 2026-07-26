"""FastAPI application factory for RepoLens server.

Creates the app with REST API routes, dashboard, health probes,
optional scheduler, and Prometheus metrics endpoint.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse

from .api import installer, jobs, mcp as mcp_api, repos, search

logger = logging.getLogger(__name__)


def create_app(config: Any = None) -> FastAPI:
    """Factory to create and configure the FastAPI application.

    Args:
        config: Optional configuration object. If None, uses defaults.
              Called with no args by uvicorn factory mode.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        logger.info("RepoLens server starting up")
        from repolens.core.pipeline.service import indexing_service

        indexing_service.start_runtime()
        app.state.indexing_service = indexing_service

        # Try to start the scheduler (graceful if apscheduler missing)
        try:
            from .scheduler import setup_scheduler

            scheduler = setup_scheduler(config, None, None)
            scheduler.start()
            app.state.scheduler = scheduler
            logger.info("Scheduler started (incremental: */15m, full: 2am, staleness: */30m)")
        except ImportError:
            logger.warning("apscheduler not installed — scheduler disabled")
        except Exception as e:
            logger.warning(f"Scheduler failed to start: {e}")

        yield

        # Shutdown
        logger.info("RepoLens server shutting down")
        if hasattr(app.state, "scheduler"):
            try:
                app.state.scheduler.shutdown()
            except Exception:
                pass
        indexing_service.stop_runtime()

    app = FastAPI(
        lifespan=lifespan,
        title="RepoLens",
        description="Local-first code intelligence platform",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    # CORS for local development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── REST API Routes ──────────────────────────────────────────────
    app.include_router(repos.router, prefix="/api/repos", tags=["repos"])
    app.include_router(search.router, prefix="/api/search", tags=["search"])
    app.include_router(jobs.router, prefix="/api", tags=["jobs"])
    app.include_router(mcp_api.router, prefix="/api/mcp", tags=["mcp"])
    app.include_router(installer.router, prefix="/api/installer", tags=["installer"])

    # ── Dashboard ────────────────────────────────────────────────────
    try:
        from repolens.observability.dashboard import router as dashboard_router
        app.include_router(dashboard_router)
    except ImportError:
        logger.warning("Dashboard module not available")

    # ── Health Probes ────────────────────────────────────────────────
    @app.get("/health/live", tags=["health"])
    async def health_live():
        """Kubernetes liveness probe."""
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def health_ready():
        """Kubernetes readiness probe."""
        try:
            from repolens.observability.health import health
            result = health.readiness()
            return {"status": "ready" if result.healthy else "not_ready", "checks": result.checks}
        except ImportError:
            return {"status": "ready"}

    @app.get("/health/startup", tags=["health"])
    async def health_startup():
        """Kubernetes startup probe."""
        return {"status": "ok"}

    # ── Prometheus Metrics ───────────────────────────────────────────
    @app.get("/metrics", tags=["observability"])
    async def prometheus_metrics():
        """Prometheus-compatible metrics endpoint."""
        try:
            from repolens.observability.metrics import metrics
            result = metrics.get_prometheus_output()
            if isinstance(result, tuple):
                content, content_type = result
            else:
                content, content_type = str(result), "text/plain"
            return PlainTextResponse(content=content, media_type=content_type)
        except ImportError:
            return PlainTextResponse(content="# metrics not available\n")

    # ── Dashboard Data API ───────────────────────────────────────────
    @app.get("/api/dashboard/data", tags=["dashboard"])
    async def dashboard_data():
        """Live dashboard metrics as JSON."""
        data = {}
        try:
            from repolens.observability.metrics import metrics
            data["metrics"] = metrics.get_dashboard_data()
        except ImportError:
            data["metrics"] = {}
        try:
            from repolens.observability.health import health
            data["health"] = health.full_status()
        except ImportError:
            data["health"] = {}
        try:
            from repolens.observability.token_tracker import token_tracker
            data["tokens"] = token_tracker.get_summary()
        except ImportError:
            data["tokens"] = {}
        try:
            from repolens.observability.pipeline_monitor import pipeline_monitor
            data["pipeline"] = pipeline_monitor.get_summary()
        except ImportError:
            data["pipeline"] = {}
        try:
            from repolens.observability.mcp_monitor import mcp_monitor
            data["mcp"] = mcp_monitor.get_summary()
        except ImportError:
            data["mcp"] = {}
        try:
            from repolens.observability.rag_monitor import rag_monitor
            data["rag"] = rag_monitor.get_summary()
        except ImportError:
            data["rag"] = {}
        return data

    # ── Root Redirect ────────────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    async def root():
        """Redirect root to dashboard."""
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/dashboard")

    return app
