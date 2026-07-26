"""End-to-end coverage for persistent indexing, retrieval, and context."""

import asyncio

import pytest


@pytest.mark.asyncio
async def test_full_search_cross_file_and_incremental(tmp_path):
    from repolens.core.graph.store import GraphStore
    from repolens.core.pipeline.orchestrator import PipelineOrchestrator
    from repolens.core.search.repository import RepositorySearch

    (tmp_path / "helpers.py").write_text(
        "def normalize_name(value):\n    return value.strip().lower()\n",
        encoding="utf-8",
    )
    (tmp_path / "service.py").write_text(
        "from helpers import normalize_name\n\n"
        "class UserService:\n"
        "    def create_user(self, name):\n"
        "        return normalize_name(name)\n",
        encoding="utf-8",
    )

    orchestrator = PipelineOrchestrator()
    full = await orchestrator.run_full(str(tmp_path))
    assert full.files_processed == 2
    assert full.stats["total_files"] == 2
    assert full.stats["total_vectors"] == full.stats["total_chunks"]

    index = RepositorySearch(tmp_path)
    results = await index.search("normalize user name", mode="hybrid", top_k=5)
    assert results
    assert any(result["symbol_name"] == "normalize_name" for result in results)

    callers = index.store.related("normalize_name", "in", "CALLS")
    assert any(row["name"] == "create_user" for row in callers)

    # Same-named top-level symbols in different files retain distinct stable ids.
    (tmp_path / "other.py").write_text("def normalize_name(value):\n    return value\n", encoding="utf-8")
    incremental = await orchestrator.run_incremental(str(tmp_path))
    assert incremental.files_processed == 1
    matches = RepositorySearch(tmp_path).symbols("normalize_name")
    assert len({match["id"] for match in matches}) == 2

    # Deleted files and their chunks are removed without rebuilding unchanged files.
    (tmp_path / "other.py").unlink()
    deleted = await orchestrator.run_incremental(str(tmp_path))
    assert deleted.files_processed == 1
    store = GraphStore(tmp_path / ".repolens" / "index.db")
    assert store.get_stats()["total_files"] == 2
    assert len(store.find_symbols("normalize_name")) == 1


def test_registry_survives_reopen(tmp_path):
    from repolens.core.persistence.registry import RegistryStore

    db = tmp_path / "registry.db"
    first = RegistryStore(db)
    first.add_repo(
        {
            "id": "repo-1",
            "name": "demo",
            "local_path": str(tmp_path / "demo"),
            "status": "registered",
            "files_count": 4,
            "is_git": True,
            "created_at": 1.0,
        }
    )
    first.create_job(
        {
            "id": "job-1",
            "repo_id": "repo-1",
            "mode": "full",
            "status": "running",
            "phase": "parse",
            "progress": 50,
            "started_at": 2.0,
        }
    )
    first.update_job("job-1", status="completed", phase="complete", progress=100)

    reopened = RegistryStore(db)
    assert reopened.get_repo("repo-1")["name"] == "demo"
    assert reopened.get_job("job-1")["status"] == "completed"


def test_edge_reconciliation_collapses_duplicate_resolved_calls(tmp_path):
    import networkx as nx

    from repolens.core.graph.store import GraphStore

    graph = nx.DiGraph()
    graph.add_node(
        "caller-id",
        name="caller",
        qualified_name="caller",
        kind="function",
        file_path="service.py",
        line_start=1,
        line_end=3,
        language="python",
    )
    graph.add_node(
        "target-id",
        name="normalize",
        qualified_name="normalize",
        kind="function",
        file_path="helpers.py",
        line_start=1,
        line_end=2,
        language="python",
    )
    graph.add_edge(
        "caller-id",
        "normalize",
        raw_target="normalize",
        kind="CALLS",
        file_path="service.py",
        line=2,
    )
    graph.add_edge(
        "caller-id",
        "helpers.normalize",
        raw_target="helpers.normalize",
        kind="CALLS",
        file_path="service.py",
        line=2,
    )
    store = GraphStore(tmp_path / "index.db")
    store.save_graph(graph)

    assert store.reconcile_edges() == 1
    assert store.get_stats()["total_edges"] == 1
    assert store.related("normalize", "in", "CALLS")[0]["name"] == "caller"


def test_web_api_indexes_searches_and_calls_mcp(tmp_path, monkeypatch):
    import importlib

    from fastapi.testclient import TestClient

    from repolens.core.persistence.registry import RegistryStore
    from repolens.server.api import jobs, repos, search
    from repolens.server.app import create_app

    repository = tmp_path / "project"
    repository.mkdir()
    (repository / "orders.py").write_text(
        "class OrderService:\n"
        "    def calculate_invoice(self, subtotal):\n"
        "        return subtotal * 1.2\n",
        encoding="utf-8",
    )
    durable_registry = RegistryStore(tmp_path / "server" / "registry.db")
    monkeypatch.setattr(repos, "registry", durable_registry)
    monkeypatch.setattr(jobs, "registry", durable_registry)
    monkeypatch.setattr(search, "registry", durable_registry)
    monkeypatch.setattr(
        importlib.import_module("repolens.core.persistence"), "registry", durable_registry
    )
    monkeypatch.setattr(
        importlib.import_module("repolens.core.persistence.registry"),
        "registry",
        durable_registry,
    )

    with TestClient(create_app()) as client:
        created = client.post(
            "/api/repos", json={"local_path": str(repository), "name": "orders"}
        )
        assert created.status_code == 200, created.text
        repo_id = created.json()["id"]
        started = client.post(f"/api/repos/{repo_id}/index?mode=full")
        assert started.status_code == 200, started.text
        job_id = started.json()["job_id"]
        for _ in range(200):
            job = client.get(f"/api/jobs/{job_id}").json()
            if job["status"] != "running":
                break
            import time
            time.sleep(0.01)
        assert job["status"] == "completed", job
        assert job["symbols_extracted"] >= 2

        response = client.post(
            "/api/search",
            json={
                "repo_id": repo_id,
                "query": "calculate invoice subtotal",
                "mode": "hybrid",
                "top_k": 5,
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["results"][0]["symbol_name"] == "calculate_invoice"

        browser_response = client.get(
            "/api/search",
            params={
                "repo_id": repo_id,
                "query": "calculate invoice subtotal",
                "mode": "hybrid",
                "top_k": 5,
            },
        )
        assert browser_response.status_code == 200, browser_response.text
        assert browser_response.json()["results"]

        tools = client.get("/api/mcp/tools")
        assert tools.status_code == 200, tools.text
        assert "search_symbols" in {tool["name"] for tool in tools.json()["tools"]}

        mcp_response = client.post(
            "/api/mcp/call",
            json={
                "tool": "search_symbols",
                "arguments": {"name": "calculate_invoice", "repo_id": repo_id},
            },
        )
        assert mcp_response.status_code == 200, mcp_response.text
        assert "calculate_invoice" in str(mcp_response.json()["result"])


@pytest.mark.asyncio
async def test_context_is_built_from_persisted_symbols_under_budget(tmp_path):
    from repolens.core.distill.context_builder import ContextBuilder
    from repolens.core.pipeline.orchestrator import PipelineOrchestrator
    from repolens.core.search.repository import RepositorySearch

    (tmp_path / "large.py").write_text(
        "def calculate_total(values):\n"
        "    total = 0\n"
        + "".join(f"    total += {number}\n" for number in range(100))
        + "    return total\n",
        encoding="utf-8",
    )
    await PipelineOrchestrator().run_full(str(tmp_path))
    index = RepositorySearch(tmp_path)
    targets = index.context_targets(["calculate_total"])
    result = ContextBuilder(budget=80).build_for_symbols(targets, file_reader=index.read_file)
    assert result.total_tokens <= 80
    assert result.raw_tokens > result.total_tokens


@pytest.mark.asyncio
async def test_mcp_search_and_context_tools_use_persisted_index(tmp_path, monkeypatch):
    import importlib

    from repolens.core.persistence.registry import RegistryStore
    from repolens.core.pipeline.orchestrator import PipelineOrchestrator
    from repolens.server.mcp.server import mcp

    (tmp_path / "catalog.py").write_text(
        "def lookup_product(sku):\n    return {'sku': sku}\n",
        encoding="utf-8",
    )
    result = await PipelineOrchestrator().run_full(str(tmp_path))
    durable_registry = RegistryStore(tmp_path / "registry.db")
    durable_registry.add_repo(
        {
            "id": "catalog",
            "name": "catalog",
            "local_path": str(tmp_path),
            "status": "indexed",
            "files_count": 1,
            "is_git": False,
            "created_at": 1.0,
        }
    )
    durable_registry.update_repo(
        "catalog",
        symbols_count=result.symbols_extracted,
        edges_count=result.edges_resolved,
        chunks_count=result.stats["total_chunks"],
        last_indexed=1.0,
    )
    registry_module = importlib.import_module("repolens.core.persistence.registry")
    persistence_package = importlib.import_module("repolens.core.persistence")
    monkeypatch.setattr(registry_module, "registry", durable_registry)
    monkeypatch.setattr(persistence_package, "registry", durable_registry)

    names = {tool.name for tool in await mcp.list_tools()}
    assert {"search_semantic", "search_symbols", "get_context", "get_health"} <= names
    search_result = await mcp.call_tool(
        "search_symbols", {"name": "lookup_product", "repo_id": "catalog"}
    )
    assert "lookup_product" in str(search_result)
    context_result = await mcp.call_tool(
        "get_context",
        {"targets": ["lookup_product"], "budget": 200, "repo_id": "catalog"},
    )
    assert "def lookup_product" in str(context_result)
