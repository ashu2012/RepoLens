"""Prometheus-compatible metrics registry for RepoLens.

Collects metrics across all subsystems: pipeline, MCP server,
RAG search, token reduction, embeddings, and system health.
Falls back to no-op counters if prometheus_client is not installed.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Try to import prometheus_client; use no-op fallbacks if unavailable
try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )
    _probe_registry = CollectorRegistry()
    Counter("_repolens_probe_total", "probe", registry=_probe_registry)
    PROMETHEUS_AVAILABLE = True
except (ImportError, TypeError):
    PROMETHEUS_AVAILABLE = False


class _NoOpMetric:
    """No-op metric for when prometheus_client is not installed."""

    def inc(self, amount=1, **kwargs):
        pass

    def dec(self, amount=1, **kwargs):
        pass

    def set(self, value, **kwargs):
        pass

    def observe(self, value, **kwargs):
        pass

    def labels(self, **kwargs):
        return self


_CURRENT_REGISTRY = None


def _make_counter(name: str, doc: str, labels: list[str] | None = None):
    if PROMETHEUS_AVAILABLE:
        return Counter(name, doc, labels or [], registry=_CURRENT_REGISTRY)
    return _NoOpMetric()


def _make_histogram(name: str, doc: str, labels: list[str] | None = None):
    if PROMETHEUS_AVAILABLE:
        return Histogram(name, doc, labels or [], registry=_CURRENT_REGISTRY)
    return _NoOpMetric()


def _make_gauge(name: str, doc: str, labels: list[str] | None = None):
    if PROMETHEUS_AVAILABLE:
        return Gauge(name, doc, labels or [], registry=_CURRENT_REGISTRY)
    return _NoOpMetric()


class MetricsRegistry:
    """Central metrics registry for all RepoLens subsystems.

    Provides Prometheus-compatible metrics when prometheus_client is installed,
    and falls back to no-op counters otherwise.
    """

    def __init__(self) -> None:
        global _CURRENT_REGISTRY
        self._registry = CollectorRegistry() if PROMETHEUS_AVAILABLE else None
        _CURRENT_REGISTRY = self._registry
        # --- Pipeline Metrics ---
        self.pipeline_runs_total = _make_counter(
            "repolens_pipeline_runs_total",
            "Total pipeline executions",
            ["mode", "status"],
        )
        self.pipeline_duration_seconds = _make_histogram(
            "repolens_pipeline_duration_seconds",
            "Pipeline execution time",
            ["mode", "phase"],
        )
        self.files_indexed_total = _make_counter(
            "repolens_files_indexed_total",
            "Files processed",
        )
        self.symbols_extracted_total = _make_counter(
            "repolens_symbols_extracted_total",
            "AST symbols extracted",
        )

        # --- MCP Server Metrics ---
        self.mcp_tool_calls_total = _make_counter(
            "repolens_mcp_tool_calls_total",
            "MCP tool invocations",
            ["tool_name", "status"],
        )
        self.mcp_tool_latency_seconds = _make_histogram(
            "repolens_mcp_tool_latency_seconds",
            "MCP tool response time",
            ["tool_name"],
        )
        self.mcp_active_connections = _make_gauge(
            "repolens_mcp_active_connections",
            "Active MCP client connections",
        )

        # --- RAG / Search Metrics ---
        self.search_queries_total = _make_counter(
            "repolens_search_queries_total",
            "Search queries processed",
            ["mode"],
        )
        self.search_latency_seconds = _make_histogram(
            "repolens_search_latency_seconds",
            "Search response time",
            ["mode"],
        )
        self.search_results_count = _make_histogram(
            "repolens_search_results_count",
            "Results returned per query",
        )

        # --- Token Reduction Metrics ---
        self.tokens_saved_total = _make_counter(
            "repolens_tokens_saved_total",
            "Tokens saved by distillation",
        )
        self.token_reduction_ratio = _make_histogram(
            "repolens_token_reduction_ratio",
            "Compression ratio per request",
        )
        self.context_budget_utilization = _make_histogram(
            "repolens_context_budget_utilization",
            "Fraction of token budget used",
        )

        # --- Embedding Metrics ---
        self.embedding_requests_total = _make_counter(
            "repolens_embedding_requests_total",
            "Embedding API calls",
            ["provider", "status"],
        )
        self.embedding_latency_seconds = _make_histogram(
            "repolens_embedding_latency_seconds",
            "Embedding generation time",
            ["provider"],
        )

        # --- System Health ---
        self.index_staleness_seconds = _make_gauge(
            "repolens_index_staleness_seconds",
            "Seconds since last successful index",
            ["repo"],
        )
        self.vector_store_size = _make_gauge(
            "repolens_vector_store_size",
            "Number of vectors in store",
            ["repo"],
        )
        self.graph_node_count = _make_gauge(
            "repolens_graph_node_count",
            "Knowledge graph node count",
            ["repo"],
        )
        self.graph_edge_count = _make_gauge(
            "repolens_graph_edge_count",
            "Knowledge graph edge count",
            ["repo"],
        )

        # Internal tracking for dashboard
        self._recent_events: list[dict] = []
        self._max_events = 100

    @contextmanager
    def track_mcp_tool(self, tool_name: str):
        """Context manager to track MCP tool call latency and status."""
        start = time.monotonic()
        try:
            yield
            duration = time.monotonic() - start
            self.mcp_tool_calls_total.labels(tool_name=tool_name, status="success").inc()
            self.mcp_tool_latency_seconds.labels(tool_name=tool_name).observe(duration)
            self._record_event("mcp_tool", tool_name=tool_name, duration_ms=duration * 1000, status="success")
        except Exception:
            duration = time.monotonic() - start
            self.mcp_tool_calls_total.labels(tool_name=tool_name, status="error").inc()
            self.mcp_tool_latency_seconds.labels(tool_name=tool_name).observe(duration)
            self._record_event("mcp_tool", tool_name=tool_name, duration_ms=duration * 1000, status="error")
            raise

    @contextmanager
    def track_search(self, mode: str):
        """Context manager to track search latency."""
        start = time.monotonic()
        try:
            yield
            duration = time.monotonic() - start
            self.search_queries_total.labels(mode=mode).inc()
            self.search_latency_seconds.labels(mode=mode).observe(duration)
        except Exception:
            raise

    @contextmanager
    def track_pipeline(self, mode: str, phase: str):
        """Context manager to track pipeline phase duration."""
        start = time.monotonic()
        try:
            yield
            duration = time.monotonic() - start
            self.pipeline_duration_seconds.labels(mode=mode, phase=phase).observe(duration)
        except Exception:
            raise

    def record_token_savings(self, raw_tokens: int, reduced_tokens: int) -> None:
        """Record token savings from context distillation."""
        saved = raw_tokens - reduced_tokens
        if saved > 0:
            self.tokens_saved_total.inc(saved)
        if raw_tokens > 0:
            ratio = reduced_tokens / raw_tokens
            self.token_reduction_ratio.observe(ratio)

    def _record_event(self, event_type: str, **kwargs) -> None:
        """Record an event for dashboard display."""
        event = {"type": event_type, "timestamp": time.time(), **kwargs}
        self._recent_events.append(event)
        if len(self._recent_events) > self._max_events:
            self._recent_events = self._recent_events[-self._max_events:]

    def get_prometheus_output(self) -> tuple[str, str]:
        """Generate Prometheus exposition format output.

        Returns:
            Tuple of (content, content_type).
        """
        if PROMETHEUS_AVAILABLE:
            return generate_latest(self._registry).decode("utf-8"), CONTENT_TYPE_LATEST
        return "# prometheus_client not installed\n", "text/plain"

    def get_dashboard_data(self) -> dict[str, Any]:
        """Get metrics summary for dashboard display."""
        return {
            "recent_events": self._recent_events[-20:],
            "prometheus_available": PROMETHEUS_AVAILABLE,
        }


# Global singleton
metrics = MetricsRegistry()
