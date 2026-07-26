"""RAG quality monitor for RepoLens.

Tracks search result quality, relevance feedback, and recall metrics.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class SearchEvent:
    """A tracked search event for quality analysis."""

    query: str
    mode: str
    results_count: int
    latency_ms: float
    timestamp: float = field(default_factory=time.time)
    top_score: float = 0.0
    feedback: str | None = None  # positive/negative/none


class RAGMonitor:
    """Monitors RAG search quality and effectiveness.

    Tracks query patterns, result distributions, and optional
    user feedback for search relevance assessment.
    """

    def __init__(self, window_size: int = 200) -> None:
        self._events: deque[SearchEvent] = deque(maxlen=window_size)
        self._total_queries: int = 0
        self._zero_result_queries: int = 0
        self._feedback_positive: int = 0
        self._feedback_negative: int = 0

    def record_search(
        self,
        query: str,
        mode: str,
        results_count: int,
        latency_ms: float,
        top_score: float = 0.0,
    ) -> None:
        """Record a search event."""
        event = SearchEvent(
            query=query,
            mode=mode,
            results_count=results_count,
            latency_ms=latency_ms,
            top_score=top_score,
        )
        self._events.append(event)
        self._total_queries += 1
        if results_count == 0:
            self._zero_result_queries += 1

    def record_feedback(self, positive: bool) -> None:
        """Record user feedback on search results."""
        if positive:
            self._feedback_positive += 1
        else:
            self._feedback_negative += 1

    def get_summary(self) -> dict:
        """Get RAG quality summary for dashboard."""
        recent = list(self._events)
        avg_latency = (
            sum(e.latency_ms for e in recent) / len(recent) if recent else 0
        )
        avg_results = (
            sum(e.results_count for e in recent) / len(recent) if recent else 0
        )
        hit_rate = (
            (1 - self._zero_result_queries / self._total_queries) * 100
            if self._total_queries > 0
            else 100.0
        )

        mode_distribution: dict[str, int] = {}
        for e in recent:
            mode_distribution[e.mode] = mode_distribution.get(e.mode, 0) + 1

        return {
            "total_queries": self._total_queries,
            "zero_result_queries": self._zero_result_queries,
            "hit_rate_pct": round(hit_rate, 1),
            "avg_latency_ms": round(avg_latency, 1),
            "avg_results_count": round(avg_results, 1),
            "feedback_positive": self._feedback_positive,
            "feedback_negative": self._feedback_negative,
            "mode_distribution": mode_distribution,
        }


# Global singleton
rag_monitor = RAGMonitor()
