# Roadmap

RepoLens is early-access software. This roadmap distinguishes working foundations from planned
product claims.

## Working foundation

- [x] Web repository registration and pipeline controls
- [x] Multi-language Tree-sitter AST extraction
- [x] Symbol-aligned source chunks
- [x] SQLite graph/chunk persistence
- [x] Pipeline result counts and honest error states
- [x] Context skeletons and token budgets
- [x] Dashboard, metrics primitives, and health probes
- [x] Persistent repository registry and job history
- [x] Stable repository-relative qualified symbol IDs
- [x] File-hash incremental updates and deletion handling
- [x] BM25 plus persisted vector retrieval
- [x] Index-backed REST search and core MCP tools
- [x] Best-effort cross-file call resolution

## Next: make retrieval useful

- [x] Add embedding creation to the indexing transaction
- [x] Add exact symbol lookup and source retrieval
- [x] Add end-to-end Web/API indexing tests
- [ ] Add PostgreSQL/pgvector as an optional large-index backend
- [ ] Replace deterministic fallback vectors with a stronger bundled local model
- [ ] Add query-time graph reranking to hybrid retrieval

## Then: complete the agent surface

- [x] Back the documented MCP tools with the persisted index
- [x] Resolve unambiguous callers and callees across files
- [x] Implement incremental updates and deletion handling
- [ ] Respect `.gitignore` and configurable excludes
- [ ] Persist scheduler state and expose real job history
- [ ] Add MCP integration tests with representative clients

## Later

- [ ] Architecture communities and service boundaries
- [ ] GraphRAG and cross-repository intelligence
- [ ] Index freshness and architecture-drift alerts
- [ ] VS Code and JetBrains integrations
- [ ] Reproducible quality, latency, and token-reduction benchmarks
