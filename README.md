# RepoLens

<div align="center">

### Repository intelligence for AI coding agents

Turn a local codebase into a queryable AST, symbol index, knowledge graph, and
token-efficient context layer—without sending your source code to a hosted indexing service.

[![GitHub stars](https://img.shields.io/github/stars/ashu2012/RepoLens?style=for-the-badge&logo=github&label=Stars)](https://github.com/ashu2012/RepoLens/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/ashu2012/RepoLens?style=for-the-badge&logo=github&label=Forks)](https://github.com/ashu2012/RepoLens/forks)
[![Open issues](https://img.shields.io/github/issues/ashu2012/RepoLens?style=for-the-badge&logo=github&label=Open%20issues)](https://github.com/ashu2012/RepoLens/issues)

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/Model_Context_Protocol-ready-6B4EFF)](https://modelcontextprotocol.io/)
[![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Development status](https://img.shields.io/badge/status-early_access-orange)](ROADMAP.md)

[⭐ Star RepoLens](https://github.com/ashu2012/RepoLens) ·
[🚀 Try it locally](#quick-start) ·
[🧩 Pick a contribution](https://github.com/ashu2012/RepoLens/issues) ·
[💬 Start a discussion](https://github.com/ashu2012/RepoLens/discussions)

[Quick start](#quick-start) · [How it works](#how-it-works) ·
[Documentation](#documentation) · [Roadmap](ROADMAP.md) ·
[Contributing](CONTRIBUTING.md)

</div>

---

AI coding tools are excellent at reasoning about code once they have the right context.
Finding that context is the expensive part. RepoLens scans a repository once, extracts its
structure with Tree-sitter, and stores durable local indexes that tools can query instead of
re-reading the entire tree for every task.

> [!IMPORTANT]
> RepoLens is in early access. AST indexing, symbol chunking, local graph persistence, the Web
> dashboard, and core context utilities are available. Semantic retrieval, incremental updates,
> and several MCP tools are under active development. See the [honest feature status](#status)
> before adopting it in production.

## Built in the open

RepoLens is growing from an early working foundation into a community-built repository
intelligence layer. The project is actively looking for its first wave of users and contributors:

- Try RepoLens on a real repository and report the language, scale, and indexing result.
- Help connect persisted chunks to BM25, vectors, and MCP tools.
- Add parser fixtures for your language ecosystem.
- Improve the dashboard, documentation, packaging, and developer experience.

**Community milestone:** help RepoLens reach its first 100 stars and 10 contributors. This is a
public goal—not a claim about current growth.

## Why RepoLens?

- **Code-aware, not text-only.** Index classes, functions, methods, imports, calls, and symbol
  boundaries rather than arbitrary fixed-size text windows.
- **Local by default.** The AST graph and chunks live in `.repolens/index.db` inside the indexed
  repository.
- **Built for agents.** Expose compact, relevant context through REST, CLI, and the Model Context
  Protocol.
- **Observable.** Inspect repository registration, indexing progress, result counts, failures,
  health, and pipeline metrics from one dashboard.
- **Provider-flexible.** Use local Ollama embeddings, OpenAI, or a deterministic mock provider
  during development.

## Quick start

Prerequisites: Python 3.11+ and Git.

```bash
git clone https://github.com/ashu2012/RepoLens.git
cd RepoLens/repolens

python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

python -m pip install -e .
repolens serve
```

Open [http://127.0.0.1:8420/dashboard](http://127.0.0.1:8420/dashboard), add a local repository,
and choose **Full index**. A successful run reports the real number of files, symbols, and edges
written to `<repository>/.repolens/index.db`; zero-output parsing is treated as a failure.

Run the test suite:

```bash
python -m pip install pytest pytest-asyncio
python -m pytest
```

## How it works

```text
Local repository
      │
      ├─ discover supported source files
      ├─ parse syntax with Tree-sitter
      ├─ extract symbols, imports, and calls
      ├─ create symbol-aligned source chunks
      └─ persist graph + chunks in SQLite
                 │
        Search / context / MCP / dashboard
```

RepoLens currently recognizes Python, JavaScript, TypeScript, Go, Rust, Java, C, C++, Ruby,
Kotlin, C#, PHP, Swift, Scala, and shell files through `tree-sitter-language-pack`.

## Status

| Capability | Status | Notes |
|---|:---:|---|
| Repository registration and Web controls | ✅ | Local paths, full-index trigger, progress, cancellation |
| Multi-language AST indexing | ✅ | Tree-sitter symbols, imports, and call expressions |
| Symbol-aligned chunks | ✅ | Source content and symbol metadata persisted in SQLite |
| Knowledge graph persistence | ✅ | Nodes, edges, and chunks in `.repolens/index.db` |
| Context distillation and token budgets | ✅ | Skeleton and budget utilities with tests |
| Dashboard and health probes | ✅ | FastAPI dashboard plus health/metrics endpoints |
| BM25 and vector retrieval | ✅ | Persisted chunks, offline vectors, and hybrid RRF |
| Semantic/hybrid search API | ✅ | Repository-scoped REST search over the durable index |
| MCP server | ✅ | Search, context, graph, change, architecture, and health tools |
| Incremental indexing | ✅ | File-hash updates with added, modified, and deleted file handling |
| Persistent repository registry/jobs | ✅ | Durable SQLite server state and job history |
| Architecture intelligence/GraphRAG | 📋 | Planned |

Legend: ✅ usable · 🧪 experimental · 🚧 in progress · 📋 planned

## MCP

The intended client configuration is:

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

The MCP surface includes semantic and symbol search, budgeted context assembly, callers/callees,
recent changes, architecture, and health. Pass `repo_id` when multiple repositories are indexed.

By default RepoLens uses deterministic offline vectors so the complete local-RAG path works
without a service. Set `REPOLENS_EMBEDDING_PROVIDER=ollama` to use a local semantic embedding
model; see [the indexing guide](docs/indexing.md).

## Project layout

```text
RepoLens/
├── repolens/                 # Installable Python application
│   ├── src/repolens/
│   │   ├── core/             # Ingestion, graph, search, providers, pipeline
│   │   ├── server/           # REST API, Web UI, MCP, scheduler
│   │   ├── observability/    # Metrics, health, pipeline and RAG monitors
│   │   └── cli/              # Command-line interface
│   ├── templates/            # Self-hosted dashboard
│   └── tests/
├── docs/                     # User and contributor documentation
├── implementation_plan.md    # Original technical blueprint
└── ROADMAP.md                # Current delivery status and priorities
```

The other top-level directories are research/reference projects used to study code intelligence,
RAG, architecture, observability, and agent tooling. RepoLens itself lives in `repolens/`.

## Documentation

- [Getting started](docs/getting-started.md)
- [Indexing pipeline](docs/indexing.md)
- [MCP and REST API](docs/mcp-api.md)
- [Architecture](ARCHITECTURE.md)
- [Roadmap](ROADMAP.md)
- [FAQ](docs/faq.md)
- [Benchmarks](docs/benchmarks.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## Contributing

RepoLens is a good fit for contributors interested in compilers, Tree-sitter, information
retrieval, knowledge graphs, developer tools, MCP, or observability. A useful first contribution
can be a parser fixture, a search integration test, documentation, a dashboard improvement, or
one of the open roadmap items.

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before starting a large change. If the project is
useful to you, star it, open an issue with your use case, and share an indexing fixture from your
language ecosystem.

### Contributors

Every avatar below is generated from the repository's real GitHub contribution history.

<a href="https://github.com/ashu2012/RepoLens/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=ashu2012/RepoLens" alt="RepoLens contributors" />
</a>

### Star history

This chart uses public GitHub data and updates as the community grows.

[![RepoLens star history](https://api.star-history.com/svg?repos=ashu2012/RepoLens&type=Date)](https://star-history.com/#ashu2012/RepoLens&Date)

## License

RepoLens is licensed under the [Apache License 2.0](LICENSE).
