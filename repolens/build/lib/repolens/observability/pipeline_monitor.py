"""Pipeline monitor for RepoLens.

Tracks pipeline execution metrics: phase durations, file counts,
error rates, and throughput for each indexing run.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from collections import deque

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PhaseMetric:
    """Metrics for a single pipeline phase execution."""

    name: str
    started_at: float = 0.0
    completed_at: float = 0.0
    items_processed: int = 0
    errors: int = 0
    status: str = "pending"

    @property
    def duration_s(self) -> float:
        if self.completed_at and self.started_at:
            return self.completed_at - self.started_at
        return 0.0


@dataclass
class PipelineRun:
    """Metrics for a complete pipeline run."""

    run_id: str
    repo_path: str
    mode: str  # full or incremental
    started_at: float = field(default_factory=time.time)
    completed_at: float = 0.0
    phases: list[PhaseMetric] = field(default_factory=list)
    status: str = "running"
    error: str | None = None

    @property
    def duration_s(self) -> float:
        if self.completed_at:
            return self.completed_at - self.started_at
        return time.time() - self.started_at

    @property
    def total_items(self) -> int:
        return sum(p.items_processed for p in self.phases)


class PipelineMonitor:
    """Monitors pipeline execution performance.

    Maintains a history of pipeline runs and provides
    aggregate metrics for dashboard display.
    """

    def __init__(self, history_size: int = 50) -> None:
        self._runs: deque[PipelineRun] = deque(maxlen=history_size)
        self._current_run: PipelineRun | None = None
        self._total_runs: int = 0
        self._total_failures: int = 0

    def start_run(self, run_id: str, repo_path: str, mode: str) -> PipelineRun:
        """Start tracking a new pipeline run."""
        run = PipelineRun(run_id=run_id, repo_path=repo_path, mode=mode)
        self._current_run = run
        self._total_runs += 1
        logger.info("pipeline_run_started", run_id=run_id, repo=repo_path, mode=mode)
        return run

    def start_phase(self, phase_name: str) -> PhaseMetric:
        """Start tracking a pipeline phase."""
        phase = PhaseMetric(name=phase_name, started_at=time.time(), status="running")
        if self._current_run:
            self._current_run.phases.append(phase)
        return phase

    def end_phase(self, phase: PhaseMetric, items: int = 0, errors: int = 0) -> None:
        """Complete a pipeline phase."""
        phase.completed_at = time.time()
        phase.items_processed = items
        phase.errors = errors
        phase.status = "error" if errors > 0 else "success"
        logger.info(
            "pipeline_phase_complete",
            phase=phase.name,
            duration_s=round(phase.duration_s, 2),
            items=items,
            errors=errors,
        )

    def end_run(self, error: str | None = None) -> None:
        """Complete the current pipeline run."""
        if self._current_run:
            self._current_run.completed_at = time.time()
            self._current_run.status = "error" if error else "success"
            self._current_run.error = error
            if error:
                self._total_failures += 1
            self._runs.append(self._current_run)
            logger.info(
                "pipeline_run_complete",
                run_id=self._current_run.run_id,
                duration_s=round(self._current_run.duration_s, 2),
                items=self._current_run.total_items,
                status=self._current_run.status,
            )
            self._current_run = None

    def get_summary(self) -> dict:
        """Get pipeline monitoring summary for dashboard."""
        recent_runs = list(self._runs)[-10:]
        avg_duration = (
            sum(r.duration_s for r in recent_runs) / len(recent_runs)
            if recent_runs
            else 0.0
        )

        return {
            "total_runs": self._total_runs,
            "total_failures": self._total_failures,
            "success_rate_pct": (
                round((1 - self._total_failures / self._total_runs) * 100, 1)
                if self._total_runs > 0
                else 100.0
            ),
            "avg_duration_s": round(avg_duration, 2),
            "current_run": (
                {
                    "run_id": self._current_run.run_id,
                    "repo": self._current_run.repo_path,
                    "mode": self._current_run.mode,
                    "elapsed_s": round(self._current_run.duration_s, 1),
                    "phases": [
                        {"name": p.name, "status": p.status, "duration_s": round(p.duration_s, 2)}
                        for p in self._current_run.phases
                    ],
                }
                if self._current_run
                else None
            ),
            "recent_runs": [
                {
                    "run_id": r.run_id,
                    "repo": r.repo_path,
                    "mode": r.mode,
                    "status": r.status,
                    "duration_s": round(r.duration_s, 2),
                    "items": r.total_items,
                }
                for r in recent_runs
            ],
        }


# Global singleton
pipeline_monitor = PipelineMonitor()
