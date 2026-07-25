"""MCP server performance monitor for RepoLens.

Tracks MCP tool call performance, connection counts, latency
percentiles, and error rates.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ToolCallMetric:
    """Metrics for a single MCP tool call."""

    tool_name: str
    timestamp: float
    duration_ms: float
    success: bool
    error: str | None = None


class MCPMonitor:
    """Monitors MCP server tool performance.

    Tracks latency distributions, error rates, and throughput
    per tool, with rolling window statistics.
    """

    def __init__(self, window_size: int = 500) -> None:
        self._calls: deque[ToolCallMetric] = deque(maxlen=window_size)
        self._tool_counts: defaultdict[str, int] = defaultdict(int)
        self._tool_errors: defaultdict[str, int] = defaultdict(int)
        self._tool_latencies: defaultdict[str, list[float]] = defaultdict(list)
        self._connections: int = 0

    def record_call(
        self,
        tool_name: str,
        duration_ms: float,
        success: bool,
        error: str | None = None,
    ) -> None:
        """Record an MCP tool call."""
        metric = ToolCallMetric(
            tool_name=tool_name,
            timestamp=time.time(),
            duration_ms=duration_ms,
            success=success,
            error=error,
        )
        self._calls.append(metric)
        self._tool_counts[tool_name] += 1
        if not success:
            self._tool_errors[tool_name] += 1
        self._tool_latencies[tool_name].append(duration_ms)
        # Keep only last 100 latencies per tool
        if len(self._tool_latencies[tool_name]) > 100:
            self._tool_latencies[tool_name] = self._tool_latencies[tool_name][-100:]

    def connection_opened(self) -> None:
        self._connections += 1

    def connection_closed(self) -> None:
        self._connections = max(0, self._connections - 1)

    def _percentile(self, values: list[float], pct: float) -> float:
        """Calculate percentile from a list of values."""
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        idx = int(len(sorted_vals) * pct / 100)
        idx = min(idx, len(sorted_vals) - 1)
        return sorted_vals[idx]

    def get_tool_stats(self, tool_name: str) -> dict:
        """Get stats for a specific tool."""
        latencies = self._tool_latencies.get(tool_name, [])
        total = self._tool_counts.get(tool_name, 0)
        errors = self._tool_errors.get(tool_name, 0)

        return {
            "total_calls": total,
            "errors": errors,
            "error_rate_pct": round((errors / total) * 100, 1) if total > 0 else 0,
            "p50_ms": round(self._percentile(latencies, 50), 1),
            "p95_ms": round(self._percentile(latencies, 95), 1),
            "p99_ms": round(self._percentile(latencies, 99), 1),
            "avg_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0,
        }

    def get_summary(self) -> dict:
        """Get full MCP performance summary for dashboard."""
        tools = {}
        for tool_name in self._tool_counts:
            tools[tool_name] = self.get_tool_stats(tool_name)

        total_calls = sum(self._tool_counts.values())
        total_errors = sum(self._tool_errors.values())

        return {
            "active_connections": self._connections,
            "total_calls": total_calls,
            "total_errors": total_errors,
            "error_rate_pct": (
                round((total_errors / total_calls) * 100, 1) if total_calls > 0 else 0
            ),
            "tools": tools,
            "recent_calls": [
                {
                    "tool": c.tool_name,
                    "duration_ms": round(c.duration_ms, 1),
                    "success": c.success,
                    "timestamp": c.timestamp,
                }
                for c in list(self._calls)[-10:]
            ],
        }


# Global singleton
mcp_monitor = MCPMonitor()
