"""Verify RepoLens imports work correctly without external dependencies."""
import sys, types
sys.path.insert(0, r'T:\development\RepoLens\repolens\src')

# Proper mock that handles class inheritance
class MockModule(types.ModuleType):
    def __init__(self, name="mock"):
        super().__init__(name)
    def __getattr__(self, name):
        # Return a real class that can be subclassed
        if name[0].isupper():
            return type(name, (), {})
        m = MockModule(name)
        return m
    def __call__(self, *a, **k):
        return self

for mod in ['structlog', 'httpx', 'pydantic', 'pydantic_settings', 'yaml',
            'watchdog', 'watchdog.observers', 'watchdog.events',
            'pathspec', 'tree_sitter', 'tree_sitter_language_pack',
            'networkx', 'sqlalchemy', 'aiosqlite', 'lancedb',
            'fastapi', 'fastapi.responses', 'fastapi.middleware.cors',
            'uvicorn', 'fastmcp', 'apscheduler', 'apscheduler.schedulers.asyncio',
            'apscheduler.triggers.cron', 'click', 'rich', 'rich.console',
            'rich.table', 'rich.panel', 'rich.progress',
            'prometheus_client', 'scipy', 'numpy', 'git', 'jinja2',
            'tenacity', 'gitpython']:
    if mod not in sys.modules:
        sys.modules[mod] = MockModule(mod)

# --- Helpers ---
def assert_eq(a, b):
    assert a == b, f"{a!r} != {b!r}"
def assert_in(needle, haystack):
    assert needle in haystack, f"{needle!r} not in {haystack!r}"
def assert_true(val):
    assert val is True, f"Expected True, got {val!r}"
def assert_false(val):
    assert val is False, f"Expected False, got {val!r}"

passed = 0
failed = 0
def check(label, func):
    global passed, failed
    try:
        func()
        print(f"  [PASS] {label}")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {label}: {e}")
        failed += 1

print("=" * 55)
print("  RepoLens v0.1.0 — Import & Unit Verification")
print("=" * 55)

# 1. Package root
print("\n[1] Package Root")
check("repolens.__version__", lambda: assert_eq(__import__('repolens').__version__, "0.1.0"))

# 2. Token Estimator
print("\n[2] Token Estimator (pure Python)")
from repolens.core.distill.token_estimator import estimate_tokens, format_savings, TokenStats, estimate_tokens_detailed
check("estimate_tokens('hello') >= 1", lambda: assert_true(estimate_tokens("hello") >= 1))
check("estimate_tokens long text", lambda: assert_true(estimate_tokens("x" * 400) == 100))
check("format_savings(1000, 100)", lambda: assert_in("90.0%", format_savings(1000, 100)))
check("format_savings(0, 0)", lambda: assert_in("No content", format_savings(0, 0)))
check("TokenStats.tokens property", lambda: assert_eq(TokenStats(estimated=10, char_count=40, line_count=2).tokens, 10))
check("estimate_tokens_detailed", lambda: assert_eq(estimate_tokens_detailed("abcd").char_count, 4))

# 3. Token Budget
print("\n[3] Token Budget")
from repolens.core.distill.budget import TokenBudget
check("can_fit short text", lambda: assert_true(TokenBudget(total=100).can_fit("hi")))
check("allocate returns content", lambda: assert_eq(TokenBudget(total=100).allocate("hi"), "hi"))
check("allocate overflow returns None", lambda: assert_eq(TokenBudget(total=1).allocate("x" * 100), None))
def _budget_reset():
    b = TokenBudget(total=100); b.allocate("text"); b.reset()
    assert b.used == 0 and b.remaining == 100
check("reset clears budget", _budget_reset)
check("utilization property", lambda: assert_eq(TokenBudget(total=100, used=50).utilization, 0.5))

# 4. Skeleton Generator
print("\n[4] Skeleton Generator")
from repolens.core.distill.skeleton import build_skeleton, SkeletonSymbol, SkeletonResult
check("raw mode (no symbols)", lambda: assert_eq(build_skeleton("x=1\n", symbols=None).mode, "raw"))
def _skel_sigs():
    src = "def foo():\n    x=1\n    y=2\n    return x+y\n"
    r = build_skeleton(src, symbols=[SkeletonSymbol(name="foo", kind="function", start_line=1, end_line=4)])
    assert r.mode == "signatures"
    assert r.skeleton_tokens <= r.original_tokens
check("signatures mode", _skel_sigs)
def _skel_reduction():
    body = "\n".join(f"    line_{i} = {i}" for i in range(50))
    src = f"def big():\n{body}\n"
    r = build_skeleton(src, symbols=[SkeletonSymbol(name="big", kind="function", start_line=1, end_line=51)])
    assert r.reduction_pct > 30, f"reduction was {r.reduction_pct:.1f}%"
check("large function reduction > 30%", _skel_reduction)
check("savings_summary contains %", lambda: assert_in("%", build_skeleton("def f():\n    pass\n",
    symbols=[SkeletonSymbol(name="f", kind="function", start_line=1, end_line=2)]).savings_summary))

# 5. Context Builder
print("\n[5] Context Builder")
from repolens.core.distill.context_builder import ContextBuilder, ContextResult, ContextSection
check("create builder", lambda: ContextBuilder(budget=4000))
def _ctx_files():
    b = ContextBuilder(budget=1000)
    r = b.build_for_files(["test.py"], file_reader=lambda p: "def x(): pass\n")
    assert r.files_read == 1 and r.total_tokens > 0
check("build_for_files", _ctx_files)
def _ctx_render():
    r = ContextResult(sections=[ContextSection(label="Test", content="code", tokens=5, source_file="f.py", priority=10)])
    r.total_tokens = 5; r.raw_tokens = 100
    assert "## Test" in r.render()
    assert r.reduction_pct == 95.0
check("render and reduction", _ctx_render)

# 6. Ingestion Models
print("\n[6] Ingestion Models")
from repolens.core.ingestion.models import NodeKind, EdgeKind, ChangeType, Confidence, NodeInfo, EdgeInfo, ChunkInfo, FileChange
check("NodeKind.FUNCTION", lambda: assert_eq(NodeKind.FUNCTION.value, "function"))
check("NodeKind.CLASS", lambda: assert_eq(NodeKind.CLASS.value, "class"))
check("EdgeKind.CALLS", lambda: assert_eq(EdgeKind.CALLS.value, "calls"))
check("EdgeKind.IMPORTS_FROM", lambda: assert_eq(EdgeKind.IMPORTS_FROM.value, "imports_from"))
check("ChangeType.ADDED", lambda: ChangeType.ADDED)
check("Confidence.EXTRACTED", lambda: Confidence.EXTRACTED)

# 7. Health Check
print("\n[7] Health Check")
from repolens.observability.health import HealthCheck
check("liveness always healthy", lambda: assert_true(HealthCheck().liveness().healthy))
check("readiness empty = unhealthy", lambda: assert_false(HealthCheck().readiness().healthy))
def _hc_ready():
    hc = HealthCheck(); hc.register_component("db", True)
    assert hc.readiness().healthy is True
check("readiness with component", _hc_ready)
def _hc_startup():
    hc = HealthCheck(); assert hc.startup().healthy is False
    hc.mark_startup_complete(); assert hc.startup().healthy is True
check("startup probe", _hc_startup)
check("full_status dict", lambda: assert_in("liveness", HealthCheck().full_status()))

# 8. Metrics Registry
print("\n[8] Metrics Registry")
from repolens.observability.metrics import MetricsRegistry
check("create registry", lambda: MetricsRegistry())
check("record_token_savings", lambda: MetricsRegistry().record_token_savings(1000, 100))
check("get_dashboard_data", lambda: assert_in("recent_events", MetricsRegistry().get_dashboard_data()))
check("get_prometheus_output", lambda: MetricsRegistry().get_prometheus_output())

# 9. Token Tracker
print("\n[9] Token Tracker")
from repolens.observability.token_tracker import TokenTracker, TokenEvent
def _tt():
    tt = TokenTracker()
    e = tt.record(1000, 100, "get_context", "myrepo")
    assert e.saved == 900 and e.reduction_pct == 90.0
    assert tt.total_saved == 900
    assert tt.avg_reduction_pct == 90.0
    s = tt.get_summary()
    assert s["total_requests"] == 1
    assert s["avg_reduction_pct"] == 90.0
check("full token tracking flow", _tt)

# 10. Pipeline Monitor
print("\n[10] Pipeline Monitor")
from repolens.observability.pipeline_monitor import PipelineMonitor
def _pm():
    pm = PipelineMonitor()
    pm.start_run("r1", "/repo", "full")
    p = pm.start_phase("parse")
    pm.end_phase(p, items=50, errors=0)
    p2 = pm.start_phase("embed")
    pm.end_phase(p2, items=50, errors=2)
    pm.end_run()
    s = pm.get_summary()
    assert s["total_runs"] == 1 and s["total_failures"] == 0
    assert len(s["recent_runs"]) == 1
check("full pipeline monitor flow", _pm)

# 11. MCP Monitor
print("\n[11] MCP Monitor")
from repolens.observability.mcp_monitor import MCPMonitor
def _mm():
    mm = MCPMonitor()
    mm.record_call("search", 150.0, True)
    mm.record_call("search", 200.0, True)
    mm.record_call("search", 50.0, False, "timeout")
    mm.connection_opened()
    s = mm.get_summary()
    assert s["total_calls"] == 3
    assert s["total_errors"] == 1
    assert s["active_connections"] == 1
    ts = mm.get_tool_stats("search")
    assert ts["errors"] == 1
    assert ts["p50_ms"] > 0
check("full MCP monitor flow", _mm)

# 12. RAG Monitor
print("\n[12] RAG Monitor")
from repolens.observability.rag_monitor import RAGMonitor
def _rm():
    rm = RAGMonitor()
    rm.record_search("python class", "hybrid", 5, 120.0, 0.95)
    rm.record_search("nonexistent xyz", "bm25", 0, 50.0, 0.0)
    rm.record_feedback(True)
    rm.record_feedback(False)
    s = rm.get_summary()
    assert s["total_queries"] == 2
    assert s["zero_result_queries"] == 1
    assert s["hit_rate_pct"] == 50.0
    assert s["feedback_positive"] == 1
check("full RAG monitor flow", _rm)

# 13. Installer
print("\n[13] Auto-Installer")
from repolens.server.installer import detect_platform, ensure_data_directory
check("detect_platform", lambda: assert_in("os", detect_platform()))

# Final tally
print(f"\n{'=' * 55}")
print(f"  Results: {passed} passed, {failed} failed, {passed + failed} total")
if failed == 0:
    print("  === ALL TESTS PASSED ===")
else:
    print(f"  === {failed} TESTS FAILED ===")
print("=" * 55)
sys.exit(0 if failed == 0 else 1)
