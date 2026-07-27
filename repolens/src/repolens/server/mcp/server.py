"""Concurrent FastMCP server setup."""

import asyncio
import contextvars
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from typing import Any, Callable

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext

from repolens.core.repository_selection import (
    select_repository,
    select_repository_by_path,
)

_current_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "repolens_current_session_id",
    default=None,
)
_background_tasks: set[asyncio.Task[Any]] = set()


class MCPActivityMiddleware(Middleware):
    """Persist tool activity and debounce a session-aware incremental index."""

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        session_token = None
        session_id = f"in-process:{os.getpid()}"
        try:
            if context.fastmcp_context is not None:
                try:
                    session_id = context.fastmcp_context.session_id
                except RuntimeError:
                    pass
            session_token = _current_session_id.set(session_id)
            return await call_next(context)
        finally:
            arguments = getattr(context.message, "arguments", None) or {}
            repo_id = arguments.get("repo_id")
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            async def _record_activity() -> None:
                try:
                    await state.run_sync(state.record_activity, session_id, repo_id)
                except Exception:
                    # Activity tracking must never turn a successful MCP tool into a failure.
                    pass

            if loop is not None:
                activity_task = loop.create_task(_record_activity())
                _background_tasks.add(activity_task)
                activity_task.add_done_callback(_background_tasks.discard)
            if session_token is not None:
                _current_session_id.reset(session_token)


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
        context = contextvars.copy_context()

        def invoke():
            return context.run(partial(function, *args, **kwargs))

        return await loop.run_in_executor(
            self._ensure_executor(),
            invoke,
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

        repo = select_repository(
            registry,
            repo_id=repo_id,
            session_id=self.session_id(),
            require_indexed=True,
        )
        if repo is None:
            raise ValueError(
                "No indexed repository is available; register or index a repository first"
            )
        return repo

    def index(self, repo_id: str | None = None):
        from repolens.core.search.repository import RepositorySearch

        return RepositorySearch(self.repository(repo_id)["local_path"])

    def activity_repository(
        self,
        repo_id: str | None = None,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any] | None:
        from repolens.core.persistence import registry

        return select_repository_by_path(
            registry,
            repo_id=repo_id,
            cwd=Path.cwd(),
            session_id=session_id or self.session_id(),
        )

    def record_activity(self, session_id: str, repo_id: str | None = None) -> dict[str, Any]:
        from repolens.core.pipeline.service import indexing_service

        repo = self.activity_repository(repo_id, session_id=session_id)
        return indexing_service.record_mcp_activity(
            session_id,
            repo["id"] if repo else None,
            Path.cwd(),
        )

    def session_id(self) -> str | None:
        return _current_session_id.get()

    def active_repository(self) -> dict[str, Any] | None:
        from repolens.core.persistence import registry

        return select_repository(
            registry,
            session_id=self.session_id(),
            cwd=Path.cwd(),
            require_indexed=False,
        )

    def set_active_repository(
        self,
        repo_id: str | None = None,
        *,
        path: str | Path | None = None,
        register: bool = False,
    ) -> tuple[dict[str, Any], bool]:
        from repolens.core.persistence import registry
        from repolens.core.pipeline.service import indexing_service

        session_id = self.session_id() or f"in-process:{os.getpid()}"
        repo: dict[str, Any] | None = None
        registered = False

        if path is not None:
            target = Path(path).expanduser().resolve()
            if not target.exists():
                raise ValueError(f"Path does not exist: {target}")
            if not target.is_dir():
                raise ValueError(f"Path is not a directory: {target}")
            repo = registry.find_repo_by_path(str(target))
            if repo is None:
                if not register:
                    raise ValueError(
                        "Repository is not registered; pass register=True to add it first"
                    )
                repo, registered = indexing_service.ensure_repository(target)

        if repo is None and repo_id is not None:
            repo = registry.get_repo(repo_id)
            if repo is None:
                raise ValueError(f"Unknown repository: {repo_id}")

        if repo is None:
            repo = select_repository(
                registry,
                session_id=session_id,
                cwd=Path.cwd(),
                require_indexed=False,
            )

        if repo is None:
            raise ValueError("No repository is available to activate")

        session = registry.set_mcp_session_context(
            session_id,
            repo_id=repo["id"],
            working_directory=repo["local_path"],
        )
        repo = registry.get_repo(repo["id"]) or repo
        return ({**repo, "mcp_session": session}, registered)


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
