"""Health check endpoints for RepoLens.

Provides liveness, readiness, and startup probes compatible
with Kubernetes and monitoring systems.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class HealthStatus:
    """Health check result."""

    healthy: bool
    checks: dict[str, bool] = field(default_factory=dict)
    details: dict[str, str] = field(default_factory=dict)
    uptime_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "status": "healthy" if self.healthy else "unhealthy",
            "uptime_seconds": round(self.uptime_seconds, 1),
            "checks": self.checks,
            "details": self.details,
        }


class HealthCheck:
    """Health check manager for RepoLens services.

    Tracks component status and provides structured health responses
    for liveness, readiness, and startup probes.
    """

    def __init__(self) -> None:
        self._start_time = time.monotonic()
        self._components: dict[str, bool] = {}
        self._details: dict[str, str] = {}
        self._startup_complete = False

    @property
    def uptime(self) -> float:
        """Seconds since health check was initialized."""
        return time.monotonic() - self._start_time

    def register_component(self, name: str, healthy: bool = False, detail: str = "") -> None:
        """Register or update a component's health status."""
        self._components[name] = healthy
        if detail:
            self._details[name] = detail

    def mark_startup_complete(self) -> None:
        """Mark that initial startup has completed."""
        self._startup_complete = True
        logger.info("startup_complete", uptime_s=round(self.uptime, 1))

    def liveness(self) -> HealthStatus:
        """Liveness probe: is the process running?

        Always returns healthy unless the process itself is stuck.
        """
        return HealthStatus(
            healthy=True,
            checks={"process": True},
            uptime_seconds=self.uptime,
        )

    def readiness(self) -> HealthStatus:
        """Readiness probe: is the service ready to accept requests?

        Requires database connection and at least one indexed repo.
        """
        checks = dict(self._components)
        healthy = all(checks.values()) if checks else False
        return HealthStatus(
            healthy=healthy,
            checks=checks,
            details=dict(self._details),
            uptime_seconds=self.uptime,
        )

    def startup(self) -> HealthStatus:
        """Startup probe: has initial indexing completed?"""
        return HealthStatus(
            healthy=self._startup_complete,
            checks={"startup_complete": self._startup_complete},
            uptime_seconds=self.uptime,
        )

    def full_status(self) -> dict:
        """Complete health status for dashboard display."""
        return {
            "liveness": self.liveness().to_dict(),
            "readiness": self.readiness().to_dict(),
            "startup": self.startup().to_dict(),
            "components": {
                name: {
                    "healthy": healthy,
                    "detail": self._details.get(name, ""),
                }
                for name, healthy in self._components.items()
            },
        }


# Global singleton
health = HealthCheck()
