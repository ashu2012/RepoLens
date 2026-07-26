"""Concurrent FastMCP server setup."""

import asyncio
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from typing import Any, Callable

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext


class MCPActivityMiddleware(Middleware):
    """Persist tool activity and debounce a session-aware incremental index."""

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        try:
            return await call_next(context)
        finally:
            arguments = getattr(context.message, "arguments", None) or {}
            repo_id = arguments.get("repo_id")
            session_id = f"in-process:{os.getpid()}"
            if context.fastmcp_context is not None:
                try:
                    session_id = context.fastmcp_context.session_id
                except RuntimeError:
                    pass
            try:
                await state.run_sync(state.record_activity, session_id, repo_id)
            except Exception:
                # Activity tracking must never turn a successful MCP tool into a failure.
                pass


mcp = FastMCP(
    "repolens",
    instructions=(
        "RepoLens provides durable, local repository indexing, AST/graph lookup, "
        "hybrid search, and token-budgeted context."
    ),
    middleware=[MCPActivityMiddleware()],
)


class ServerState:
    """Shared state object for MCP tools."""

    def __init__(self, max_workers: int | None = None):
        self.graph = None
        self.search_index = None
        self.config = None
        self.max_workers = max_workers or int(
            os.environ.get("REPOLENS_MCP_WORKERS", min(32, max(4, (os.cpu_count() or 2) + 4)))
        )
        self._executor: ThreadPoolExecutor | None = None
        self._executor_lock = threading.RLock()

    def _ensure_executor(self) -> ThreadPoolExecutor:
        with self._executor_lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=max(1, self.max_workers),
                    thread_name_prefix="repolens-mcp",
                )
            return self._executor

    async def run_sync(self, function: Callable, *args, **kwargs):
        """Run blocking repository work without blocking the MCP event loop."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._ensure_executor(),
            partial(function, *args, **kwargs),
        )

    async def run_async_worker(self, function: Callable, *args, **kwargs):
        """Run a complete async operation on a worker thread with its own loop."""

        def invoke():
            return asyncio.run(function(*args, **kwargs))

        return await self.run_sync(invoke)

    def shutdown(self) -> None:
        with self._executor_lock:
            executor, self._executor = self._executor, None
        if executor:
            executor.shutdown(wait=False, cancel_futures=False)

    def repository(self, repo_id: str | None = None) -> dict:
        from repolens.core.persistence import registry

        if repo_id:
            repo = registry.get_repo(repo_id)
            if not repo:
                raise ValueError(f"Unknown repository: {repo_id}")
            return repo
        indexed = [repo for repo in registry.list_repos() if repo["status"] == "indexed"]
        if len(indexed) != 1:
            raise ValueError(
                "repo_id is required unless exactly one indexed repository is registered"
            )
        return indexed[0]

    def index(self, repo_id: str | None = None):
        from repolens.core.search.repository import RepositorySearch

        return RepositorySearch(self.repository(repo_id)["local_path"])

    def activity_repository(self, repo_id: str | None = None) -> dict[str, Any] | None:
        from repolens.core.persistence import registry

        if repo_id:
            return registry.get_repo(repo_id)
        current = registry.find_repo_by_path(str(Path.cwd().resolve()))
        if current:
            return current
        repos = registry.list_repos()
        return repos[0] if len(repos) == 1 else None

    def record_activity(self, session_id: str, repo_id: str | None = None) -> dict[str, Any]:
        from repolens.core.pipeline.service import indexing_service

        repo = self.activity_repository(repo_id)
        return indexing_service.record_mcp_activity(
            session_id,
            repo["id"] if repo else None,
            Path.cwd(),
        )


state = ServerState()

# Import tool modules to register their decorators with `mcp`
from . import (
    tool_architecture,
    tool_changes,
    tool_context,
    tool_graph,
    tool_health,
    tool_indexing,
    tool_files,
    tool_search,
)


async def run_stdio():
    """Run the MCP server over stdio transport."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    from repolens.core.pipeline.service import indexing_service

    indexing_service.start_runtime()
    try:
        await mcp.run_async(transport="stdio", show_banner=False)
    finally:
        indexing_service.stop_runtime()
        state.shutdown()


async def run_http(host: str = "127.0.0.1", port: int = 5000):
    """Run the MCP server over HTTP transport."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    from repolens.core.pipeline.service import indexing_service

    indexing_service.start_runtime()
    try:
        await mcp.run_async(transport="sse", host=host, port=port, show_banner=False)
    finally:
        indexing_service.stop_runtime()
        state.shutdown()
