"""Tests for RepoLens core modules."""

import asyncio
import pytest
import sqlite3


class TestTokenEstimator:
    """Tests for token estimation."""

    def test_estimate_tokens_basic(self):
        from repolens.core.distill.token_estimator import estimate_tokens
        assert estimate_tokens("hello world") >= 1
        assert estimate_tokens("") == 1  # min 1

    def test_estimate_tokens_code(self):
        from repolens.core.distill.token_estimator import estimate_tokens
        code = "def hello():\n    return 'world'\n"
        tokens = estimate_tokens(code)
        assert 5 <= tokens <= 20

    def test_format_savings(self):
        from repolens.core.distill.token_estimator import format_savings
        result = format_savings(1000, 100)
        assert "90.0%" in result
        assert "900" in result

    def test_format_savings_zero(self):
        from repolens.core.distill.token_estimator import format_savings
        result = format_savings(0, 0)
        assert "No content" in result


class TestTokenBudget:
    """Tests for token budget enforcement."""

    def test_budget_can_fit(self):
        from repolens.core.distill.budget import TokenBudget
        budget = TokenBudget(total=100)
        assert budget.can_fit("short text")
        assert budget.remaining == 100

    def test_budget_allocate(self):
        from repolens.core.distill.budget import TokenBudget
        budget = TokenBudget(total=100)
        result = budget.allocate("short")
        assert result is not None
        assert budget.used > 0

    def test_budget_overflow(self):
        from repolens.core.distill.budget import TokenBudget
        budget = TokenBudget(total=2)
        result = budget.allocate("x" * 100)  # Way over budget
        assert result is None

    def test_budget_reset(self):
        from repolens.core.distill.budget import TokenBudget
        budget = TokenBudget(total=100)
        budget.allocate("text")
        budget.reset()
        assert budget.used == 0
        assert budget.remaining == 100


class TestMockEmbedder:
    """Tests for the mock embedding provider."""

    @pytest.mark.asyncio
    async def test_embed_returns_vectors(self):
        from repolens.core.providers.base import MockEmbedder
        embedder = MockEmbedder()
        vectors = await embedder.embed(["hello", "world"])
        assert len(vectors) == 2
        assert len(vectors[0]) == 8

    @pytest.mark.asyncio
    async def test_embed_deterministic(self):
        from repolens.core.providers.base import MockEmbedder
        embedder = MockEmbedder()
        v1 = await embedder.embed(["test"])
        v2 = await embedder.embed(["test"])
        assert v1 == v2

    @pytest.mark.asyncio
    async def test_embed_different_inputs(self):
        from repolens.core.providers.base import MockEmbedder
        embedder = MockEmbedder()
        v1 = await embedder.embed(["hello"])
        v2 = await embedder.embed(["world"])
        assert v1 != v2

    @pytest.mark.asyncio
    async def test_embed_unit_length(self):
        import math
        from repolens.core.providers.base import MockEmbedder
        embedder = MockEmbedder()
        vectors = await embedder.embed(["test"])
        norm = math.sqrt(sum(x * x for x in vectors[0]))
        assert abs(norm - 1.0) < 1e-6

    @pytest.mark.asyncio
    async def test_embed_empty(self):
        from repolens.core.providers.base import MockEmbedder
        embedder = MockEmbedder()
        result = await embedder.embed([])
        assert result == []


class TestEmbeddingRouter:
    """Tests for the embedding router."""

    @pytest.mark.asyncio
    async def test_create_embedder_mock(self):
        from repolens.core.providers.router import create_embedder
        router = await create_embedder(provider="mock", fallback_provider=None)
        vectors = await router.embed(["test"])
        assert len(vectors) == 1
        assert len(vectors[0]) == 8

    @pytest.mark.asyncio
    async def test_router_dimensions(self):
        from repolens.core.providers.router import create_embedder
        router = await create_embedder(provider="mock", fallback_provider=None)
        assert router.dimensions == 8


class TestIndexingPipeline:
    """Regression coverage for the Web UI's real indexing path."""

    @pytest.mark.asyncio
    async def test_full_index_creates_ast_graph_and_chunks(self, tmp_path):
        from repolens.core.pipeline.orchestrator import PipelineOrchestrator

        source = tmp_path / "sample.py"
        source.write_text(
            "import os\n\nclass Greeter:\n"
            "    def hello(self, name):\n"
            "        return os.path.join('hello', name)\n",
            encoding="utf-8",
        )

        result = await PipelineOrchestrator().run_full(str(tmp_path))

        assert result.files_processed == 1
        assert result.symbols_extracted >= 2
        assert (tmp_path / ".repolens" / "index.db").exists()
        with sqlite3.connect(tmp_path / ".repolens" / "index.db") as conn:
            assert conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0] >= 2
            assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] >= 2
            contents = [row[0] for row in conn.execute("SELECT content FROM chunks")]
            assert any("def hello" in content for content in contents)


class TestSkeleton:
    """Tests for code skeleton generation."""

    def test_skeleton_no_symbols(self):
        from repolens.core.distill.skeleton import build_skeleton
        source = "x = 1\ny = 2\n"
        result = build_skeleton(source, symbols=None)
        assert result.mode == "raw"
        assert result.skeleton == source

    def test_skeleton_with_symbols(self):
        from repolens.core.distill.skeleton import build_skeleton, SkeletonSymbol
        source = (
            "import os\n"
            "\n"
            "def hello():\n"
            "    print('hello')\n"
            "    print('world')\n"
            "    return True\n"
            "\n"
            "def goodbye():\n"
            "    print('bye')\n"
            "    return False\n"
        )
        symbols = [
            SkeletonSymbol(name="hello", kind="function", start_line=3, end_line=6),
            SkeletonSymbol(name="goodbye", kind="function", start_line=8, end_line=10),
        ]
        result = build_skeleton(source, symbols=symbols, mode="signatures")
        assert result.mode == "signatures"
        assert result.skeleton_tokens < result.original_tokens
        assert "elided" in result.skeleton

    def test_skeleton_reduction(self):
        from repolens.core.distill.skeleton import build_skeleton, SkeletonSymbol
        # Large function body
        body_lines = "\n".join(f"    line_{i} = {i}" for i in range(50))
        source = f"def big_function():\n{body_lines}\n"
        symbols = [
            SkeletonSymbol(name="big_function", kind="function", start_line=1, end_line=51),
        ]
        result = build_skeleton(source, symbols=symbols)
        assert result.reduction_pct > 50


class TestContextBuilder:
    """Tests for context assembly."""

    def test_build_for_files(self):
        from repolens.core.distill.context_builder import ContextBuilder
        builder = ContextBuilder(budget=1000)

        def reader(path):
            return "def example():\n    pass\n"

        result = builder.build_for_files(
            file_paths=["test.py"],
            file_reader=reader,
        )
        assert result.files_read == 1
        assert result.total_tokens > 0

    def test_context_budget_enforcement(self):
        from repolens.core.distill.context_builder import ContextBuilder
        builder = ContextBuilder(budget=10)  # Very small budget

        def reader(path):
            return "x = 1\n" * 100  # Large file

        result = builder.build_for_files(
            file_paths=["big.py"],
            file_reader=reader,
        )
        # Should have truncated or skipped due to budget
        assert result.total_tokens <= 20  # Budget + some overhead


class TestBM25:
    """Tests for BM25 search."""

    def test_bm25_basic_search(self):
        from repolens.core.search.bm25 import BM25Index
        idx = BM25Index()
        idx.add_documents([
            ("doc1", "python machine learning tensorflow"),
            ("doc2", "javascript react frontend web"),
            ("doc3", "python data science pandas numpy"),
        ])
        results = idx.search("python machine learning", top_k=3)
        assert len(results) > 0
        assert results[0][0] == "doc1"  # Best match

    def test_bm25_empty_query(self):
        from repolens.core.search.bm25 import BM25Index
        idx = BM25Index()
        idx.add_documents([("doc1", "hello world")])
        results = idx.search("", top_k=5)
        assert results == []

    def test_bm25_no_match(self):
        from repolens.core.search.bm25 import BM25Index
        idx = BM25Index()
        idx.add_documents([("doc1", "hello world")])
        results = idx.search("zzzznonexistent", top_k=5)
        assert results == []


class TestObservability:
    """Tests for observability components."""

    def test_metrics_registry(self):
        from repolens.observability.metrics import MetricsRegistry
        m = MetricsRegistry()
        # Should not raise even without prometheus_client
        m.record_token_savings(1000, 100)

    def test_health_check(self):
        from repolens.observability.health import HealthCheck
        hc = HealthCheck()
        assert hc.liveness().healthy is True
        assert hc.readiness().healthy is False  # No components registered
        hc.register_component("db", True)
        assert hc.readiness().healthy is True

    def test_token_tracker(self):
        from repolens.observability.token_tracker import TokenTracker
        tracker = TokenTracker()
        event = tracker.record(1000, 100, "get_context")
        assert event.saved == 900
        assert event.reduction_pct == 90.0
        assert tracker.avg_reduction_pct == 90.0

    def test_pipeline_monitor(self):
        from repolens.observability.pipeline_monitor import PipelineMonitor
        pm = PipelineMonitor()
        pm.start_run("run-1", "/path/repo", "full")
        phase = pm.start_phase("parse")
        pm.end_phase(phase, items=50)
        pm.end_run()
        summary = pm.get_summary()
        assert summary["total_runs"] == 1
        assert summary["total_failures"] == 0

    def test_mcp_monitor(self):
        from repolens.observability.mcp_monitor import MCPMonitor
        mm = MCPMonitor()
        mm.record_call("search", 150.5, True)
        mm.record_call("search", 200.0, True)
        mm.record_call("search", 50.0, False, "timeout")
        stats = mm.get_tool_stats("search")
        assert stats["total_calls"] == 3
        assert stats["errors"] == 1

    def test_rag_monitor(self):
        from repolens.observability.rag_monitor import RAGMonitor
        rm = RAGMonitor()
        rm.record_search("test query", "hybrid", 5, 120.0)
        rm.record_search("empty query", "bm25", 0, 50.0)
        summary = rm.get_summary()
        assert summary["total_queries"] == 2
        assert summary["zero_result_queries"] == 1
        assert summary["hit_rate_pct"] == 50.0


class TestModels:
    """Tests for data models."""

    def test_node_kind_enum(self):
        from repolens.core.ingestion.models import NodeKind
        assert NodeKind.FUNCTION.value == "function"
        assert NodeKind.CLASS.value == "class"

    def test_edge_kind_enum(self):
        from repolens.core.ingestion.models import EdgeKind
        assert EdgeKind.CALLS.value == "calls"
        assert EdgeKind.IMPORTS_FROM.value == "imports_from"
