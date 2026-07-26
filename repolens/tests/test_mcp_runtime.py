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


def test_indexing_service_registers_and_persists_job(tmp_path, monkeypatch):
    from repolens.core.persistence.registry import RegistryStore
    from repolens.core.pipeline.service import IndexingService

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
    assert (repository / ".repolens" / "index.db").exists()
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
