"""Concurrency, durability, and session-aware MCP indexing coverage."""

from __future__ import annotations

import asyncio
import importlib
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


def _replace_registry(monkeypatch, registry):
    registry_module = importlib.import_module("repolens.core.persistence.registry")
    persistence_package = importlib.import_module("repolens.core.persistence")
    monkeypatch.setattr(registry_module, "registry", registry)
    monkeypatch.setattr(persistence_package, "registry", registry)


def _make_indexed_repo(root: Path) -> Path:
    index_dir = root / ".repolens"
    index_dir.mkdir(parents=True, exist_ok=True)
    index_file = index_dir / "index.db"
    index_file.write_text("index", encoding="utf-8")
    (index_dir / "index.active").write_text(str(index_file), encoding="utf-8")
    return index_file


def test_default_data_dir_uses_runtime_repositories(monkeypatch):
    monkeypatch.delenv("REPOLENS_DATA_DIR", raising=False)
    from repolens.core.persistence.registry import default_data_dir
    from repolens.core.paths import repolens_project_root

    assert default_data_dir() == repolens_project_root() / ".repolens" / "repositories"


def test_resolve_index_target_without_path_uses_package_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from repolens.core.paths import repolens_package_root
    from repolens.core.pipeline.service import resolve_index_target

    assert resolve_index_target() == repolens_package_root()


def test_server_state_prefers_indexed_repo_in_current_workspace(tmp_path, monkeypatch):
    from repolens.core.persistence.registry import RegistryStore
    from repolens.server.mcp.server import ServerState

    workspace = tmp_path / "workspace"
    repo_a = workspace / "repo-a"
    repo_b = workspace / "repo-b"
    nested = repo_a / "nested"
    nested.mkdir(parents=True)
    repo_b.mkdir()
    _make_indexed_repo(repo_a)
    _make_indexed_repo(repo_b)

    durable_registry = RegistryStore(tmp_path / "data" / "registry.db")
    _replace_registry(monkeypatch, durable_registry)
    durable_registry.add_repo(
        {
            "id": "repo-a",
            "name": "Repo A",
            "local_path": str(repo_a),
            "status": "indexed",
            "created_at": 1.0,
            "last_indexed": 10.0,
        }
    )
    durable_registry.add_repo(
        {
            "id": "repo-b",
            "name": "Repo B",
            "local_path": str(repo_b),
            "status": "indexed",
            "created_at": 2.0,
            "last_indexed": 20.0,
        }
    )
    monkeypatch.chdir(nested)

    state = ServerState()
    assert state.repository()["id"] == "repo-a"


def test_server_state_prefers_repo_lens_install_root_when_indexed(tmp_path, monkeypatch):
    from repolens.core.persistence.registry import RegistryStore
    from repolens.server.mcp.server import ServerState
    import repolens.core.repository_selection as repository_selection

    install_root = tmp_path / "install-root"
    install_repo = install_root / "RepoLens"
    install_repo.mkdir(parents=True)
    _make_indexed_repo(install_repo)

    other_repo = tmp_path / "other"
    other_repo.mkdir()
    _make_indexed_repo(other_repo)

    durable_registry = RegistryStore(tmp_path / "data" / "registry.db")
    _replace_registry(monkeypatch, durable_registry)
    durable_registry.add_repo(
        {
            "id": "install",
            "name": "RepoLens",
            "local_path": str(install_repo),
            "status": "indexed",
            "created_at": 1.0,
            "last_indexed": 30.0,
        }
    )
    durable_registry.add_repo(
        {
            "id": "other",
            "name": "Other",
            "local_path": str(other_repo),
            "status": "indexed",
            "created_at": 2.0,
            "last_indexed": 40.0,
        }
    )
    monkeypatch.setattr(repository_selection, "repolens_project_root", lambda: install_repo)
    monkeypatch.setattr(repository_selection, "repolens_package_root", lambda: install_repo)
    monkeypatch.chdir(tmp_path)

    state = ServerState()
    assert state.repository()["id"] == "install"


def test_indexing_service_registers_and_persists_job(tmp_path, monkeypatch):
    from repolens.core.persistence.registry import RegistryStore
    from repolens.core.pipeline.service import IndexingService
    from repolens.core.paths import (
        repolens_active_index_pointer,
        repolens_current_index_path,
        repolens_versioned_index_root,
    )

    repository = tmp_path / "project"
    repository.mkdir()
    (repository / "inventory.py").write_text(
        "def available_stock(items):\n    return sum(items)\n",
        encoding="utf-8",
    )
    (repository / ".venv-release").mkdir()
    (repository / ".venv-release" / "ignored.py").write_text("value = 1\n", encoding="utf-8")
    (repository / "dist").mkdir()
    (repository / "dist" / "bundle.py").write_text("value = 2\n", encoding="utf-8")
    registry_path = tmp_path / "data" / "registry.db"
    durable_registry = RegistryStore(registry_path)
    _replace_registry(monkeypatch, durable_registry)
    service = IndexingService(index_workers=2, poll_interval=0.01)

    repo, registered = service.ensure_repository(repository)
    result = service.index_directory(repository)
    job = service.wait(result["job_id"], timeout=30)

    assert registered is True
    assert repo["files_count"] == 1
    assert result["registered"] is False
    assert job["status"] == "completed"
    current_index = repolens_current_index_path(repository)
    assert current_index is not None
    assert current_index.parent.parent == repolens_versioned_index_root(repository)
    assert repolens_active_index_pointer(repository).exists()
    assert Path(repolens_active_index_pointer(repository).read_text(encoding="utf-8").strip()) == current_index
    assert (repository / ".repolens" / "index.db").exists()
    assert not (repository / ".repolens" / "staging").exists()
    reopened = RegistryStore(registry_path)
    assert reopened.get_repo(result["repo_id"])["status"] == "indexed"
    assert reopened.get_job(result["job_id"])["status"] == "completed"
    service.stop_runtime()


@pytest.mark.asyncio
async def test_mcp_index_current_directory_returns_async_job(tmp_path, monkeypatch):
    from repolens.core.persistence.registry import RegistryStore
    from repolens.core.pipeline.service import indexing_service
    from repolens.server.mcp.server import mcp

    repository = tmp_path / "workspace"
    repository.mkdir()
    (repository / "billing.py").write_text(
        "class BillingService:\n"
        "    def total(self, values):\n"
        "        return sum(values)\n",
        encoding="utf-8",
    )
    durable_registry = RegistryStore(tmp_path / "data" / "registry.db")
    _replace_registry(monkeypatch, durable_registry)

    result = await mcp.call_tool(
        "index_current_directory",
        {"path": str(repository), "mode": "auto"},
    )
    payload = result.structured_content or {}
    job = indexing_service.wait(payload["job_id"], timeout=30)
    status_result = await mcp.call_tool(
        "get_index_status",
        {"job_id": payload["job_id"]},
    )

    assert payload["status"] == "indexing_started"
    assert job["status"] == "completed"
    assert status_result.structured_content["status"] == "completed"


@pytest.mark.asyncio
async def test_repository_search_reuses_cached_snapshot(tmp_path, monkeypatch):
    from repolens.core.graph.store import GraphStore
    from repolens.core.persistence.registry import RegistryStore
    from repolens.core.pipeline.service import IndexingService
    from repolens.core.search.repository import RepositorySearch

    repository = tmp_path / "cache-workspace"
    repository.mkdir()
    (repository / "searchable.py").write_text(
        "def lookup(value):\n    return value.strip().lower()\n",
        encoding="utf-8",
    )
    durable_registry = RegistryStore(tmp_path / "data" / "registry.db")
    _replace_registry(monkeypatch, durable_registry)
    service = IndexingService(index_workers=1, poll_interval=0.01)
    result = service.index_directory(repository)
    assert service.wait(result["job_id"], timeout=30)["status"] == "completed"
    service.stop_runtime()

    RepositorySearch.clear_cache()
    load_calls = 0
    original_load_chunks = GraphStore.load_chunks

    def wrapped_load_chunks(self):
        nonlocal load_calls
        load_calls += 1
        return original_load_chunks(self)

    monkeypatch.setattr(GraphStore, "load_chunks", wrapped_load_chunks)
    search = RepositorySearch(repository)

    first = await search.search("lookup", mode="hybrid", top_k=3)
    second = await RepositorySearch(repository).search("lookup", mode="hybrid", top_k=3)

    assert first
    assert second
    assert load_calls == 1


@pytest.mark.asyncio
async def test_get_health_uses_active_index_when_repo_is_indexing(monkeypatch):
    from repolens.server.mcp import tool_health

    repo = {
        "id": "repo-1",
        "status": "indexing",
        "last_indexed": 123.0,
    }

    monkeypatch.setattr(tool_health.state, "repository", lambda repo_id=None: repo)
    class FakeIndex:
        def stats(self):
            return {"total_nodes": 1, "total_edges": 2, "total_chunks": 3, "total_vectors": 1, "total_files": 1}

    called = {"value": False}

    def fake_index(*args, **kwargs):
        called["value"] = True
        return FakeIndex()

    monkeypatch.setattr(tool_health.state, "index", fake_index)

    result = await tool_health.get_health("repo-1")
    payload = json.loads(result)

    assert payload["repo_id"] == "repo-1"
    assert payload["status"] == "indexing"
    assert payload["ready"] is False
    assert payload["total_nodes"] == 1
    assert payload["total_files"] == 1
    assert called["value"] is True


@pytest.mark.asyncio
async def test_mcp_activity_middleware_records_in_background(monkeypatch):
    from repolens.server.mcp.server import MCPActivityMiddleware, state

    completed = asyncio.Event()

    async def fake_run_sync(function, *args, **kwargs):
        await asyncio.sleep(0.2)
        function(*args, **kwargs)
        completed.set()
        return {"recorded": True}

    monkeypatch.setattr(state, "run_sync", fake_run_sync)
    monkeypatch.setattr(state, "record_activity", lambda *args, **kwargs: {"recorded": True})

    middleware = MCPActivityMiddleware()
    context = SimpleNamespace(
        fastmcp_context=None,
        message=SimpleNamespace(arguments={"repo_id": "repo-1"}),
    )

    async def call_next(_context):
        return "ok"

    started = time.perf_counter()
    result = await middleware.on_call_tool(context, call_next)
    elapsed = time.perf_counter() - started

    assert result == "ok"
    assert elapsed < 0.1
    await asyncio.wait_for(completed.wait(), timeout=1)


@pytest.mark.asyncio
async def test_get_architecture_prefers_cached_snapshot(tmp_path, monkeypatch):
    from repolens.core.pipeline.orchestrator import PipelineOrchestrator
    from repolens.core.search.repository import RepositorySearch
    from repolens.server.mcp import tool_architecture

    repository = tmp_path / "arch-workspace"
    repository.mkdir()
    (repository / "alpha.py").write_text(
        "def alpha():\n    return 1\n",
        encoding="utf-8",
    )
    (repository / "beta.py").write_text(
        "def beta():\n    return alpha()\n",
        encoding="utf-8",
    )
    await PipelineOrchestrator().run_full(str(repository))
    search = RepositorySearch(repository)
    graph = search.graph()
    PipelineOrchestrator._write_architecture_snapshot(repository, graph, search.stats())

    monkeypatch.setattr(
        tool_architecture.state,
        "repository",
        lambda repo_id=None: {"id": "repo-1", "local_path": str(repository)},
    )

    result = await tool_architecture.get_architecture("repo-1")
    payload = json.loads(result)

    assert payload["symbols"] == 2
    assert payload["edges"] >= 1
    assert payload["hub_symbols"]


@pytest.mark.asyncio
async def test_query_graph_returns_json_error_payload_when_repo_resolution_fails(monkeypatch):
    from repolens.server.mcp import tool_graph

    monkeypatch.setattr(
        tool_graph.state,
        "repository",
        lambda repo_id=None: (_ for _ in ()).throw(RuntimeError("repository unavailable")),
    )

    result = await tool_graph.query_graph(
        pattern="callers_of",
        target="MarketApp",
        repo_id="missing-repo",
    )
    payload = json.loads(result)

    assert payload["ready"] is False
    assert payload["results"] == []
    assert "repository unavailable" in payload["error"]


@pytest.mark.asyncio
async def test_mcp_index_current_directory_without_path_uses_repo_package_root(monkeypatch, tmp_path):
    from repolens.core.paths import repolens_package_root
    from repolens.server.mcp import tool_indexing

    monkeypatch.chdir(tmp_path)
    captured: dict[str, object] = {}

    async def fake_run_sync(function, *args, **kwargs):
        captured["function"] = function
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"status": "indexing_started", "job_id": "job-1"}

    monkeypatch.setattr(tool_indexing.state, "run_sync", fake_run_sync)

    result = await tool_indexing.index_current_directory()

    assert result["job_id"] == "job-1"
    assert captured["args"][0] == repolens_package_root()


@pytest.mark.asyncio
async def test_cleanup_staging_artifacts_tool_removes_repository_staging(tmp_path, monkeypatch):
    from repolens.core.persistence.registry import RegistryStore
    from repolens.core.paths import repolens_staging_index_path
    from repolens.server.mcp import tool_indexing

    repository = tmp_path / "cleanup-project"
    repository.mkdir()
    (repository / "cleanup.py").write_text("def cleanup():\n    return True\n", encoding="utf-8")
    durable_registry = RegistryStore(tmp_path / "data" / "registry.db")
    _replace_registry(monkeypatch, durable_registry)
    repo = durable_registry.add_repo(
        {
            "id": "cleanup-repo",
            "name": "cleanup-project",
            "local_path": str(repository),
            "status": "indexed",
            "files_count": 1,
            "is_git": False,
            "created_at": 1.0,
            "last_indexed": 1.0,
        }
    )
    staging = repolens_staging_index_path(repository, "job-cleanup").parent
    staging.mkdir(parents=True, exist_ok=True)
    (staging / "index.db").write_text("stale", encoding="utf-8")

    cleaned = await tool_indexing.cleanup_staging_artifacts(repo_id=repo["id"])

    assert cleaned["status"] == "cleanup_completed"
    assert cleaned["scope"] == "repository"
    assert cleaned["removed"] == 1
    assert not staging.exists()


def test_prune_staging_artifacts_removes_stale_builds(tmp_path, monkeypatch):
    from repolens.core.persistence.registry import RegistryStore
    from repolens.core.pipeline.service import IndexingService
    from repolens.core.paths import repolens_staging_index_path

    repo_one = tmp_path / "repo-one"
    repo_two = tmp_path / "repo-two"
    repo_one.mkdir()
    repo_two.mkdir()
    (repo_one / "src.py").write_text("value = 1\n", encoding="utf-8")
    (repo_two / "src.py").write_text("value = 2\n", encoding="utf-8")
    durable_registry = RegistryStore(tmp_path / "data" / "registry.db")
    _replace_registry(monkeypatch, durable_registry)
    repo_one_entry = durable_registry.add_repo(
        {
            "id": "repo-one",
            "name": "repo-one",
            "local_path": str(repo_one),
            "status": "indexed",
            "files_count": 1,
            "is_git": False,
            "created_at": 1.0,
            "last_indexed": 1.0,
        }
    )
    durable_registry.add_repo(
        {
            "id": "repo-two",
            "name": "repo-two",
            "local_path": str(repo_two),
            "status": "indexed",
            "files_count": 1,
            "is_git": False,
            "created_at": 2.0,
            "last_indexed": 2.0,
        }
    )
    for repo in (repo_one, repo_two):
        staging = repolens_staging_index_path(repo, "old-job").parent
        staging.mkdir(parents=True, exist_ok=True)
        (staging / "index.db").write_text("stale", encoding="utf-8")

    service = IndexingService(index_workers=1, poll_interval=0.01)
    removed = service.prune_staging_artifacts()
    service.stop_runtime()

    assert removed == 2
    assert not (repo_one / ".repolens" / "staging").exists()
    assert not (repo_two / ".repolens" / "staging").exists()


@pytest.mark.asyncio
async def test_switch_working_repository_then_index_and_search_without_repo_id(tmp_path, monkeypatch):
    from repolens.core.persistence.registry import RegistryStore
    from repolens.core.pipeline.service import indexing_service
    from repolens.server.mcp import server, tool_indexing, tool_search

    repository = tmp_path / "agent-workspace"
    repository.mkdir()
    (repository / "prices.py").write_text(
        "def lookup_price(symbol):\n    return symbol.lower()\n",
        encoding="utf-8",
    )
    durable_registry = RegistryStore(tmp_path / "data" / "registry.db")
    _replace_registry(monkeypatch, durable_registry)

    token = server._current_session_id.set("session-switch-1")
    try:
        switched = await tool_indexing.switch_working_repository(path=str(repository), register=True)
        assert switched["status"] == "repository_selected"
        assert switched["indexed"] is False

        active = await tool_indexing.get_working_repository()
        assert active["repo_id"] == switched["repo_id"]

        queued = await tool_indexing.index_repository(mode="auto")
        job = indexing_service.wait(queued["job_id"], timeout=30)
        assert job["status"] == "completed"

        search_result = await tool_search.search_symbols("lookup_price")
        assert "lookup_price" in search_result
    finally:
        server._current_session_id.reset(token)
        indexing_service.stop_runtime()


def test_openapi_bridge_indexes_current_directory(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from repolens.core.persistence.registry import RegistryStore
    from repolens.server.api import jobs, repos, search
    from repolens.server.app import create_app

    repository = tmp_path / "openapi-workspace"
    repository.mkdir()
    (repository / "shipping.py").write_text(
        "def shipping_cost(weight):\n    return weight * 2\n",
        encoding="utf-8",
    )
    durable_registry = RegistryStore(tmp_path / "data" / "registry.db")
    _replace_registry(monkeypatch, durable_registry)
    monkeypatch.setattr(repos, "registry", durable_registry)
    monkeypatch.setattr(jobs, "registry", durable_registry)
    monkeypatch.setattr(search, "registry", durable_registry)

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/mcp/call",
            json={
                "tool": "index_current_directory",
                "arguments": {"path": str(repository), "mode": "auto"},
            },
        )
        assert response.status_code == 200, response.text
        payload = json.loads(response.json()["result"]["content"][0]["text"])
        for _ in range(300):
            job = client.get(f"/api/jobs/{payload['job_id']}").json()
            if job["status"] not in {"queued", "running"}:
                break
            time.sleep(0.01)

    assert payload["status"] == "indexing_started"
    assert job["status"] == "completed"


def test_session_activity_debounces_and_queues_incremental_index(tmp_path, monkeypatch):
    from repolens.core.persistence.registry import RegistryStore
    from repolens.core.pipeline.service import IndexingService

    repository = tmp_path / "project"
    repository.mkdir()
    source = repository / "catalog.py"
    source.write_text("def lookup(sku):\n    return sku\n", encoding="utf-8")
    durable_registry = RegistryStore(tmp_path / "data" / "registry.db")
    _replace_registry(monkeypatch, durable_registry)
    service = IndexingService(index_workers=2, poll_interval=0.01)
    initial = service.index_directory(repository)
    assert service.wait(initial["job_id"], timeout=30)["status"] == "completed"

    source.write_text(
        "def lookup(sku):\n    return sku\n\n"
        "def normalize(sku):\n    return sku.strip().lower()\n",
        encoding="utf-8",
    )
    service.record_mcp_activity(
        "session-1",
        initial["repo_id"],
        repository,
        delay_seconds=0,
    )
    assert service.process_due_sessions() == 1
    auto_job = durable_registry.latest_job(initial["repo_id"])
    completed = service.wait(auto_job["id"], timeout=30)
    session = RegistryStore(durable_registry.db_path).get_mcp_session("session-1")

    assert completed["status"] == "completed"
    assert completed["mode"] == "incremental"
    assert completed["trigger"] == "mcp-auto"
    assert session["next_index_at"] is None
    assert session["last_auto_index_at"] is not None
    service.stop_runtime()


@pytest.mark.asyncio
async def test_mcp_blocking_work_uses_multiple_worker_threads():
    from repolens.server.mcp.server import ServerState

    server_state = ServerState(max_workers=2)
    barrier = threading.Barrier(2)

    def worker() -> int:
        barrier.wait(timeout=2)
        return threading.get_ident()

    first, second = await asyncio.gather(
        server_state.run_sync(worker),
        server_state.run_sync(worker),
    )
    server_state.shutdown()

    assert first != second


@pytest.mark.asyncio
async def test_run_async_worker_uses_separate_thread_pool():
    from repolens.server.mcp.server import ServerState

    server_state = ServerState(max_workers=2)
    complete = threading.Event()

    async def _fake_search():
        complete.wait(timeout=5)

    async_task = asyncio.create_task(server_state.run_async_worker(_fake_search))
    await asyncio.sleep(0.1)

    sync_done = threading.Event()

    def _quick_sync():
        sync_done.set()
        return threading.get_ident()

    sync_result = await server_state.run_sync(_quick_sync)
    assert sync_done.is_set()
    assert isinstance(sync_result, int)

    complete.set()
    await async_task
    server_state.shutdown()


@pytest.mark.asyncio
async def test_concurrent_async_workers_do_not_starve_run_sync():
    from repolens.server.mcp.server import ServerState

    server_state = ServerState(max_workers=2)

    async_running = threading.Event()
    sync_done = threading.Event()

    def _blocking_work():
        async_running.set()
        async_running.wait(timeout=5)

    async def _slow_coroutine():
        await asyncio.to_thread(_blocking_work)

    async_tasks = [
        asyncio.create_task(server_state.run_async_worker(_slow_coroutine))
        for _ in range(6)
    ]
    async_running.wait(timeout=2)

    def _health_check():
        sync_done.set()
        return "healthy"

    health_task = asyncio.create_task(server_state.run_sync(_health_check))

    await asyncio.sleep(0.2)
    assert sync_done.is_set(), "run_sync must not be starved while async workers are running"

    health_result = await asyncio.wait_for(health_task, timeout=2)
    assert health_result == "healthy"

    async_running.clear()
    await asyncio.gather(*async_tasks)
    server_state.shutdown()


@pytest.mark.asyncio
async def test_run_async_worker_executors_are_distinct():
    from repolens.server.mcp.server import ServerState

    server_state = ServerState(max_workers=2)

    server_state._ensure_executor()
    server_state._ensure_async_executor()

    sync_executor = server_state._executor
    async_executor = server_state._async_executor

    assert sync_executor is not None
    assert async_executor is not None
    assert sync_executor is not async_executor, (
        "run_async_worker must use a separate executor from run_sync"
        " to prevent thread starvation under concurrent load"
    )

    thread_ids = set()
    lock = threading.Lock()

    def _capture_sync():
        with lock:
            thread_ids.add(("sync", threading.get_ident()))
        return "ok"

    async def _capture_async():
        with lock:
            thread_ids.add(("async", threading.get_ident()))
        return "ok"

    tasks = [
        asyncio.create_task(server_state.run_sync(_capture_sync)),
        asyncio.create_task(server_state.run_sync(_capture_sync)),
        asyncio.create_task(server_state.run_async_worker(_capture_async)),
        asyncio.create_task(server_state.run_async_worker(_capture_async)),
    ]
    await asyncio.gather(*tasks)

    assert len({tid for kind, tid in thread_ids}) >= 2
    server_state.shutdown()


@pytest.mark.asyncio
async def test_run_sync_health_check_completes_while_async_workers_saturated():
    from repolens.server.mcp.server import ServerState

    server_state = ServerState(max_workers=1)

    running = threading.Event()
    sync_done = threading.Event()

    def _blocking():
        running.set()
        running.wait(timeout=5)

    async def _long_async():
        await asyncio.to_thread(_blocking)

    async_tasks = [
        asyncio.create_task(server_state.run_async_worker(_long_async))
        for _ in range(6)
    ]
    running.wait(timeout=2)

    def _health():
        sync_done.set()
        return "ok"

    health_task = asyncio.create_task(server_state.run_sync(_health))

    await asyncio.sleep(0.2)
    assert sync_done.is_set(), (
        "run_sync health check must not be starved by async workers"
    )
    health_result = await asyncio.wait_for(health_task, timeout=2)
    assert health_result == "ok"

    running.clear()
    await asyncio.gather(*async_tasks)
    server_state.shutdown()
