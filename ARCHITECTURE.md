# Architecture

RepoLens is a local Python service with four entry surfaces: CLI, FastAPI REST, a Web dashboard,
and FastMCP. These surfaces are intended to share one repository index.

```text
CLI / Web dashboard / REST / MCP
                 │
       pipeline and query services
          ┌──────┴──────┐
   Tree-sitter       context/search
          │               │
 symbols + edges      compact results
          └──────┬────────┘
         repository-local stores
       SQLite graph/chunks + vectors
```

The full indexing transaction discovers supported files, parses ASTs, resolves unambiguous
cross-file calls, produces symbol-boundary chunks and vectors, builds a directed NetworkX graph,
and writes SQLite tables beneath the target repository's `.repolens/` directory. Incremental
transactions use persisted file hashes to replace only changed artifacts and remove deleted ones.

The Web registry and job history are stored separately in
`$REPOLENS_DATA_DIR/registry.db`. REST and MCP queries open the selected repository's durable
index, build BM25 state from its chunks, combine it with vector rankings, and pass retrieved
symbols through token-budgeted context assembly. See [ROADMAP.md](ROADMAP.md) for remaining scale
and precision work and [docs/indexing.md](docs/indexing.md) for pipeline behavior.
