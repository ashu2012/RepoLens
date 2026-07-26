"""Token usage tracker for RepoLens.

Tracks token consumption per request, calculates burn rates,
and reports savings from context distillation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from collections import deque

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TokenEvent:
    """A single token consumption event."""

    timestamp: float
    raw_tokens: int
    distilled_tokens: int
    tool_name: str
    repo_name: str = ""

    @property
    def saved(self) -> int:
        return self.raw_tokens - self.distilled_tokens

    @property
    def reduction_pct(self) -> float:
        if self.raw_tokens == 0:
            return 0.0
        return (self.saved / self.raw_tokens) * 100


class TokenTracker:
    """Tracks token usage and savings across the platform.

    Maintains a rolling window of token events for burn-rate
    calculation and trend analysis.
    """

    def __init__(self, window_size: int = 1000) -> None:
        self._events: deque[TokenEvent] = deque(maxlen=window_size)
        self._total_raw: int = 0
        self._total_distilled: int = 0
        self._total_saved: int = 0
        self._request_count: int = 0

    def record(
        self,
        raw_tokens: int,
        distilled_tokens: int,
        tool_name: str,
        repo_name: str = "",
    ) -> TokenEvent:
        """Record a token usage event."""
        event = TokenEvent(
            timestamp=time.time(),
            raw_tokens=raw_tokens,
            distilled_tokens=distilled_tokens,
            tool_name=tool_name,
            repo_name=repo_name,
        )
        self._events.append(event)
        self._total_raw += raw_tokens
        self._total_distilled += distilled_tokens
        self._total_saved += event.saved
        self._request_count += 1

        logger.debug(
            "token_event",
            raw=raw_tokens,
            distilled=distilled_tokens,
            saved=event.saved,
            reduction_pct=f"{event.reduction_pct:.1f}%",
            tool=tool_name,
        )
        return event

    @property
    def total_saved(self) -> int:
        return self._total_saved

    @property
    def avg_reduction_pct(self) -> float:
        if self._total_raw == 0:
            return 0.0
        return (self._total_saved / self._total_raw) * 100

    def burn_rate(self, window_seconds: int = 3600) -> float:
        """Calculate token burn rate (tokens/hour) over recent window."""
        cutoff = time.time() - window_seconds
        recent = [e for e in self._events if e.timestamp > cutoff]
        if not recent:
            return 0.0
        total = sum(e.distilled_tokens for e in recent)
        elapsed = time.time() - recent[0].timestamp
        if elapsed <= 0:
            return 0.0
        return (total / elapsed) * 3600

    def get_summary(self) -> dict:
        """Get summary statistics for dashboard."""
        return {
            "total_requests": self._request_count,
            "total_raw_tokens": self._total_raw,
            "total_distilled_tokens": self._total_distilled,
            "total_saved_tokens": self._total_saved,
            "avg_reduction_pct": round(self.avg_reduction_pct, 1),
            "burn_rate_per_hour": round(self.burn_rate(), 0),
            "recent_events": [
                {
                    "timestamp": e.timestamp,
                    "raw": e.raw_tokens,
                    "distilled": e.distilled_tokens,
                    "saved": e.saved,
                    "tool": e.tool_name,
                }
                for e in list(self._events)[-10:]
            ],
        }


# Global singleton
token_tracker = TokenTracker()
