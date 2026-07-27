# 🔍 RepoLens

[Download Windows installer or portable EXE](https://github.com/ashu2012/RepoLens/releases/latest)
· [Installer build instructions](../docs/releases.md)
· [Discord](https://discord.gg/RveEysUvF)
· [Donate](https://www.paypal.com/paypalme/stocknap)

**Local-first code intelligence platform** — Semantic search, knowledge graphs, and context distillation for AI coding agents.

> *Give your AI coding tools deep understanding of your codebase with 90%+ token savings.*

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org)
[![FastMCP](https://img.shields.io/badge/MCP-FastMCP-green.svg)](https://github.com/jlowin/fastmcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ Features

| Feature | Description |
|---|---|
| **🌲 AST Parsing** | Tree-sitter powered parsing for 15+ languages |
| **🔗 Knowledge Graph** | NetworkX call/import/inheritance graph with community detection |
| **🔎 Hybrid Search** | BM25 + vector (LanceDB) + graph-neighbor reranking |
| **🤖 MCP Server** | 15 tools exposed via FastMCP (stdio + HTTP) |
| **💰 Token Reduction** | 80-95% savings via skeleton generation + context distillation |
| **⏰ Cron Indexing** | APScheduler-based incremental (*/15m) and full (daily) indexing |
| **📊 Observability** | Prometheus metrics + self-hosted HTML dashboard |
| **🖥️ CLI** | Rich terminal interface with init, index, search, serve commands |

## 📊 Comparative Study — RepoLens vs Reference Projects

RepoLens was designed by studying 8 leading open-source projects in the code intelligence, RAG, and AI tooling space, then **combining their best capabilities into a single unified platform**. Here's how they compare:

### Feature Matrix

| Feature | RepoLens | repowise | code-review-graph | graphify | samemind | OmniRoute | AIUsageTracker | open-webui | likec4 |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Primary Focus** | Unified Code Intelligence | Codebase Intelligence | Token-Efficient Review | Multimodal Knowledge Graph | Agent Memory | AI Gateway Router | Usage Monitoring | AI Web Platform | Architecture DSL |
| **Code AST Parsing** | ✅ 15+ langs | ✅ 16 langs | ✅ 30+ langs | ✅ ~40 langs | ❌ | ❌ | ❌ | ❌ | ❌ Custom DSL |
| **BM25 Search** | ✅ Zero-dep | ✅ | ✅ FTS5 | ❌ | ✅ Zero-dep | ✅ FTS5 | ❌ | ✅ | ❌ |
| **Vector Search** | ✅ LanceDB | ✅ LanceDB/PGVector | ✅ | ❌ | ✅ sqlite-vec | ✅ Int8 Vector | ❌ | ✅ 9 backends | ❌ |
| **Hybrid Search (RRF)** | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| **Graph Reranking** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Knowledge Graph** | ✅ NetworkX | ✅ Dependency | ✅ AST Graph | ✅ NetworkX | ✅ OKF Concept | ❌ | ❌ | ❌ | ✅ C4 Model |
| **Community Detection** | ✅ Leiden | ✅ Leiden | ✅ Leiden | ✅ Leiden | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Hub/Bridge Analysis** | ✅ | ❌ | ✅ | ✅ God nodes | ❌ | ❌ | ❌ | ❌ | ❌ |
| **MCP Server** | ✅ 15 tools | ✅ 10 tools | ✅ FastMCP | ✅ Optional | ✅ | ✅ 104 tools | ❌ | ✅ Plugin | ✅ |
| **Token Reduction** | ✅ 80-95% | ✅ Up to 96% | ✅ 82x median | ✅ High | ✅ Budget | ✅ 15-95% | ❌ Tracks only | ✅ Chunked | ❌ |
| **Skeleton Generation** | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Blast Radius** | ✅ 2-hop | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Incremental Indexing** | ✅ SHA-256 diff | ✅ Per-commit | ✅ Under 2s | ✅ Git hooks | ✅ .index cache | ❌ | ❌ | ✅ | ✅ LSP |
| **Cron Scheduler** | ✅ APScheduler | ✅ APScheduler | ✅ crg-daemon | ✅ Watchdog | ❌ Zero-daemon | ✅ Cooldowns | ✅ Polling | ✅ Calendar | ❌ |
| **Prometheus Metrics** | ✅ 30+ metrics | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ OpenTelemetry | ❌ |
| **Web Dashboard** | ✅ Self-hosted | ✅ | ✅ HTML | ✅ HTML | ❌ ASCII only | ✅ Next.js | ✅ WPF/Blazor | ✅ Full UI | ✅ React |
| **CLI** | ✅ Click+Rich | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ Docker | ✅ |
| **Ollama Embeddings** | ✅ Primary | ✅ | ✅ | ✅ Optional | ✅ | ✅ | ❌ | ✅ | ❌ |
| **OpenAI Embeddings** | ✅ Fallback | ✅ | ✅ | ✅ Optional | ❌ | ✅ | ❌ | ✅ | ❌ |
| **Auto-Fallback Router** | ✅ | ❌ | ❌ | ❌ | ✅ BM25 fallback | ✅ 19 strategies | ❌ | ❌ | ❌ |
| **Dimension Guard** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Token Usage Tracking** | ✅ Burn-rate | ✅ Cost dashboard | ✅ Savings telemetry | ❌ | ❌ | ✅ USD headers | ✅ Full monitor | ❌ | ❌ |
| **Health Probes (K8s)** | ✅ 3 probes | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | ❌ |

### What RepoLens Took from Each Project

| Source Project | What RepoLens Adopted | What RepoLens Added |
|:---|:---|:---|
| **repowise** | Pipeline orchestrator pattern, APScheduler cron, MCP tool shapes, skeleton distillation, LanceDB vectors | Prometheus metrics, graph-neighbor reranking, unified dashboard, health probes |
| **code-review-graph** | Tree-sitter multi-language parsing, FastMCP server setup, auto-installer pattern, SHA-256 diff detection, blast radius | Zero-dep pure-Python BM25 (vs SQLite FTS5), Leiden fallback to NetworkX |
| **graphify** | NetworkX graph builder, Leiden community detection, dual-confidence edge tagging, god-node analysis | SQLite WAL persistence, architecture overview endpoint, budget-enforced context |
| **samemind** | Zero-dep BM25 algorithm (ported from JS to Python), MCP JSON-RPC patterns | Hybrid RRF fusion, vector store integration, graph reranking |
| **OmniRoute** | Embedding router with auto-detection, dimension guard, local model fallback | Simplified to 3 providers (Ollama→OpenAI→Mock) vs 278 |
| **AIUsageTracker** | Token burn-rate calculation, pace projection concept | Integrated as observability module, not separate app |
| **open-webui** | RAG UI patterns, hybrid search with reranking, document ingestion flow | Code-specific AST chunking vs generic document chunking |
| **likec4** | Architecture visualization concept, C4-inspired module grouping | Graph-based architecture overview via community detection |

### Unique RepoLens Capabilities

Features that **no single reference project provides**:

| Unique Feature | Description |
|:---|:---|
| **🔀 Hybrid Search + Graph Reranking** | Only platform combining BM25 + vector + RRF + graph-neighbor boost |
| **📊 30+ Prometheus Metrics** | Production-grade observability with counters, histograms, gauges across all subsystems |
| **🛡️ Embedding Dimension Guard** | Prevents vector store corruption when switching embedding providers mid-index |
| **🏥 Kubernetes Health Probes** | Liveness, readiness, and startup probes for container orchestration |
| **📈 5 Dedicated Monitors** | Pipeline, MCP, RAG, Token, and Health monitors with independent metrics |
| **🎯 Unified Dashboard** | Single HTML dashboard with panels for every subsystem + control center links |
| **💰 Token Burn-Rate Forecasting** | Rolling-window calculation predicting token consumption velocity |
| **🔄 Budget-Enforced Context** | Hard token budget with automatic truncation and utilization tracking |

## 🚀 Quick Start

### Download on Windows

Most users should download `RepoLens-<version>-Setup-x64.exe` from the
[latest release](https://github.com/ashu2012/RepoLens/releases/latest). A
portable `RepoLens.exe` and `SHA256SUMS.txt` are published beside it. The
bundles include Python; end users do not need to install Python.

### Installed application lifecycle

```bash
repolens start          # Initialize (if needed), start server, and open dashboard
repolens init           # Initialize runtime only
repolens init --wizard  # Interactive initialization
repolens daemon         # Start background daemon (headless)
repolens status         # Show runtime and daemon status
repolens diagnostics    # Run installation and dependency diagnostics
```

Runtime state is user-scoped: `%LOCALAPPDATA%\RepoLens` on Windows,
`~/.local/state/repolens` on Linux, and
`~/Library/Application Support/RepoLens` on macOS. Generate client
configuration without modifying client files with `repolens mcp-config codex`
or any of: `claude`, `cursor`, `vscode`, `continue`, `gemini`, and `windsurf`.

```bash
# Install
pip install -e .

# Initialize in your project
repolens init /path/to/your/repo

# Add and index
repolens add /path/to/your/repo
repolens index /path/to/your/repo

# Start RepoLens (initializes, starts server, opens dashboard)
repolens start
# → Dashboard: http://localhost:38451/dashboard
# → API Docs:  http://localhost:38451/api/docs
# → Server stays open until Ctrl+C

# Or start server only (without opening dashboard)
repolens serve
# → Dashboard: http://localhost:38451/dashboard
# → API Docs:  http://localhost:38451/api/docs

# Or use as MCP server (for AI coding tools)
repolens mcp

```
## Build EXE & Installer

Build a standalone Windows executable and installer from source:

### Prerequisites

- Python 3.11+
- Windows 10/11 (ARM64 via x64 emulation)

### Build Portable EXE

```bash
# Install build tool
python -m pip install nuitka

# Build portable executable (output: dist/RepoLens.exe)
python packaging/build.py
```

### Build Windows Installer

```powershell
# Install Inno Setup (one time)
winget install --exact --id JRSoftware.InnoSetup

# Build portable EXE + installer (output: dist/RepoLens-{version}-Setup-x64.exe)
.\packaging\windows\build-windows.ps1 -Version 0.2.0 -Python python

# With custom Inno Setup path
.\packaging\windows\build-windows.ps1 `
  -Version 0.2.0 `
  -Python python `
  -Iscc "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

The generated `dist\` folder contains:
- `RepoLens.exe` — Portable standalone executable
- `RepoLens-{version}-Setup-x64.exe` — Windows installer (includes Python runtime)

After installation, launch RepoLens via Start Menu or run:
```bash
RepoLens start
```

The `start` command initializes the runtime (if needed), starts the server, and opens the dashboard — all in a single step. Press **Ctrl+C** to stop.

For full build details, see [packaging/README.md](packaging/README.md).

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                   RepoLens Platform                  │
├──────────┬──────────┬──────────┬───────────┬────────┤
│  CLI     │ REST API │ MCP      │ Dashboard │ Cron   │
│ (Click)  │(FastAPI) │(FastMCP) │  (HTML)   │(APSch) │
├──────────┴──────────┴──────────┴───────────┴────────┤
│              Context Distillation Engine              │
│         (Skeleton + Budget + Token Estimator)         │
├──────────────────────┬──────────────────────────────┤
│   Hybrid Search      │    Knowledge Graph            │
│ (BM25+Vector+RRF)   │ (NetworkX+Communities)        │
├──────────────────────┴──────────────────────────────┤
│              Ingestion Pipeline                       │
│  (Tree-sitter → Chunk → Resolve → Embed → Store)    │
├─────────────────────────────────────────────────────┤
│           Embedding Router (Ollama → OpenAI)         │
├─────────────────────────────────────────────────────┤
│        Observability (Prometheus + Monitors)          │
└─────────────────────────────────────────────────────┘
```

## 🤖 MCP Tools

Configure RepoLens as an MCP server in your AI coding tool:

```json
{
  "mcpServers": {
    "repolens": {
      "command": "repolens",
      "args": ["mcp"]
    }
  }
}
```

### Available Tools

| Tool | Description |
|---|---|
| `search_semantic` | Hybrid search (BM25 + vector + graph reranking) |
| `search_symbols` | Fast AST symbol lookup by name/kind |
| `get_context` | Token-reduced context assembly with budget |
| `fetch_context` | Read files with automatic skeleton compression |
| `find_callers` | Reverse call graph traversal |
| `find_callees` | Forward call graph traversal |
| `query_graph` | Caller, callee, import, and containment patterns |
| `recent_changes` | Git status or diff summary |
| `detect_changes` | Hash-based changed-file detection |
| `get_architecture` | Community-based architecture overview |
| `get_communities` | Group symbols into graph communities |
| `get_health` | Index stats, staleness, coverage |
| `list_repos` | List repositories in the durable registry |
| `index_current_directory` | Register the workspace and start an async index |
| `get_index_status` | Monitor a durable asynchronous index job |

Blocking MCP queries and AST indexing run in separate bounded thread pools. Every MCP session
persists its latest activity and schedules an incremental index 10 minutes after the most recent
tool call. Continued activity postpones the run.

## ⏰ Cron Schedule

| Job | Default | Description |
|---|---|---|
| Incremental Index | `*/15 * * * *` | Re-parse changed files + blast radius |
| Full Re-index | `0 2 * * *` | Complete repository re-scan |
| Staleness Check | `*/30 * * * *` | Flag stale index entries |

## 📊 Dashboard

Access the live dashboard at `http://localhost:38451/dashboard`:

- **System Overview** — repos, symbols, edges, vectors, token savings
- **Pipeline Status** — phase-level execution tracking
- **MCP Performance** — tool latency percentiles, error rates
- **Search & RAG** — query patterns, hit rates, mode distribution
- **Token Savings** — compression ratios, burn rates
- **Cron Schedule** — job status and next run times

## 🔧 Configuration

Edit `config.yaml`:

```yaml
repositories: []  # Add via CLI: repolens add /path

scheduler:
  incremental_cron: "*/15 * * * *"
  full_index_cron: "0 2 * * *"

embedding:
  provider: ollama          # ollama, openai, mock
  model: nomic-embed-text
  fallback_provider: openai

server:
  host: 127.0.0.1
  port: 38451
```

## 🌐 Supported Languages

Python, JavaScript, TypeScript, Go, Rust, Java, C, C++, Ruby, Kotlin, C#, PHP, Swift, Scala, Bash — via Tree-sitter language pack.

## 📦 Project Structure

```
repolens/
├── src/repolens/
│   ├── core/
│   │   ├── ingestion/    # AST parsing, chunking, diff detection
│   │   ├── graph/        # Knowledge graph, communities, analysis
│   │   ├── search/       # BM25, vector store, hybrid search
│   │   ├── providers/    # Embedding router (Ollama, OpenAI)
│   │   ├── distill/      # Skeleton, context builder, token budget
│   │   └── pipeline/     # Orchestrator, incremental, checkpoint
│   ├── server/
│   │   ├── mcp/          # FastMCP tools (15 tools)
│   │   ├── api/          # REST API routes
│   │   ├── installer/    # Auto-installer
│   │   ├── app.py        # FastAPI factory
│   │   └── scheduler.py  # APScheduler cron
│   ├── observability/    # Metrics, monitors, health, dashboard
│   └── cli/              # Click CLI
├── templates/
│   └── dashboard.html    # Self-hosted dashboard
├── config.yaml
└── pyproject.toml
```

## License

MIT
