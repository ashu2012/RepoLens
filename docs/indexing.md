# Indexing pipeline

RepoLens converts supported source files into a durable SQLite index at
`<repository>/.repolens/index.db`.

Indexing is executed by a bounded worker pool. Web and MCP requests enqueue durable jobs in
`$REPOLENS_DATA_DIR/registry.db` and return immediately. The worker owns a renewable lease while it
runs; queued work and expired leases are recoverable after a process restart.

## Full index

1. **Detect** scans the repository for supported extensions. `.git`, `.repolens`,
   `node_modules`, virtual environments, and Python cache directories are ignored.
2. **Parse** uses `tree-sitter-language-pack` to extract classes, functions, methods, types,
   imports, and call expressions.
3. **Resolve** maps calls to stable cross-file symbol identities when a definition is known.
4. **Chunk** copies each symbol's exact source range into a symbol-aligned chunk.
5. **Embed** generates offline deterministic vectors by default, or Ollama vectors when enabled.
6. **Store** replaces `nodes`, `edges`, `chunks`, vectors, and file hashes transactionally.
7. **Verify** rejects a run that found supported files but extracted zero symbols.

SQLite uses WAL mode and full synchronous commits. Index replacement and incremental updates occur
inside immediate transactions, so readers continue using the last committed snapshot while a
worker prepares the next one. The JSON pipeline checkpoint is written to a temporary file, flushed
to disk, and atomically replaced.

The Web UI exposes the phase, percentage, duration, files processed, symbols extracted, edges
resolved, and index path. Exceptions produce an `error` phase and message; they are not reported
as successful runs.

## Incremental mode

Incremental indexing hashes supported source files and compares them with the durable
`file_state` table. It reparses and re-embeds added or modified files, removes deleted-file
symbols/chunks/edges, retains unchanged artifacts, and updates the Git checkpoint when available.
If no index exists, an incremental request automatically performs the initial full index.

Symbols use stable IDs derived from repository-relative path, qualified name, and symbol kind.
This prevents same-named functions in different files from collapsing into one graph node.

MCP sessions automatically enqueue an incremental run 10 minutes after their most recent tool
call. This is a debounce: continued activity postpones the run, preventing repeated indexing while
an agent is actively making calls. Session activity and the deadline are persisted in the registry.

## Embeddings and local RAG

The default `mock` provider is an offline deterministic vectorizer intended for reliable setup
and tests. It enables the complete vector storage/retrieval path but is not a substitute for a
semantic model. For useful local semantic retrieval, run Ollama with `nomic-embed-text` and set:

```bash
REPOLENS_EMBEDDING_PROVIDER=ollama
REPOLENS_EMBEDDING_MODEL=nomic-embed-text
```

If Ollama is unavailable during indexing, RepoLens records local hash embeddings and continues.
SQLite is the default durable store. PostgreSQL/pgvector remains an optional future scale backend;
it is not required for local operation.

## Inspecting an index

```bash
sqlite3 /path/to/repository/.repolens/index.db \
  "select count(*) as symbols from nodes; select count(*) as chunks from chunks;"
```

Removing `.repolens/index.db` is safe when the server is stopped; the next full index recreates
it. Do not commit `.repolens/` to a source repository.

## Supported files

`.py`, `.js`, `.jsx`, `.ts`, `.tsx`, `.go`, `.rs`, `.java`, `.c`, `.h`, `.cpp`, `.hpp`,
`.cc`, `.rb`, `.kt`, `.cs`, `.php`, `.swift`, `.scala`, `.sh`, and `.bash`.

## Known limitations

- Cross-file call resolution is best-effort and is not yet type-aware.
- Dynamic dispatch and runtime-generated imports cannot always be resolved statically.
- Ignore rules are currently built-in rather than fully `.gitignore` aware.
