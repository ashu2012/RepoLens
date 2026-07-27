"""Concurrency, durability, and session-aware MCP indexing coverage."""

from __future__ import annotations

import asyncio
import importlib
import json
import threading
import time

import pytest


def _replace_registry(monkeypatch, registry):
    registry_module = importlib.import_module("repolens.core.persistence.registry")
    persistence_package = importlib.import_module("repolens.core.persistence")
    monkeypatch.setattr(registry_module, "registry", registry)
    monkeypatch.setattr(persistence_package, "registry", registry)


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


def test_indexing_service_registers_and_persists_job(tmp_path, monkeypatch):
    from repolens.core.persistence.registry import RegistryStore
    from repolens.core.pipeline.service import IndexingService
    from repolens.core.paths import repolens_current_index_path, repolens_active_index_pointer

    repository = tmp_path / "project"
    repository.mkdir()
    (repository / "inventory.py").write_text(
        "def available_stock(items):\n    return sum(items)\n",
        encoding="utf-8",
    )
    registry_path = tmp_path / "data" / "registry.db"
    durable_registry = RegistryStore(registry_path)
    _replace_registry(monkeypatch, durable_registry)
    service = IndexingService(index_workers=2, poll_interval=0.01)

    result = service.index_directory(repository)
    job = service.wait(result["job_id"], timeout=30)

    assert result["registered"] is True
    assert job["status"] == "completed"
    assert repolens_current_index_path(repository) is not None
    assert repolens_active_index_pointer(repository).exists()
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
    from repolens.core.pipeline.service import IndexingService
    from repolens.core.search.repository import RepositorySearch

    repository = tmp_path / "cache-workspace"
    repository.mkdir()
    (repository / "searchable.py").write_text(
        "def lookup(value):\n    return value.strip().lower()\n",
        encoding="utf-8",
    )
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
