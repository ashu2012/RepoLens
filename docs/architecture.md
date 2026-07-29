# RepoLens low-level architecture

This document describes the runtime boundaries that make RepoLens responsive under load:
the async event loop stays thin, blocking work moves to worker threads, and repository indexes
are published as durable snapshots rather than being mutated in place.

See also:

- [Indexing pipeline](indexing.md)
- [MCP and REST API](mcp-api.md)

## Runtime surfaces

| Surface | Entry point | Main responsibility |
|---|---|---|
| CLI | `src/repolens/cli/__init__.py` | Starts the server, daemon, or MCP transport |
| FastAPI | `src/repolens/server/app.py` | REST API, dashboard support, and the OpenAPI bridge |
| FastMCP | `src/repolens/server/mcp/server.py` | MCP tool registration and request dispatch |
| Indexing service | `src/repolens/core/pipeline/service.py` | Durable job scheduling, worker pools, and publish/cleanup |
| Orchestrator | `src/repolens/core/pipeline/orchestrator.py` | Parse/resolve/chunk/embed/store pipeline |
| Registry store | `src/repolens/core/persistence/registry.py` | Repositories, jobs, MCP sessions, and leases |
| Graph store | `src/repolens/core/graph/store.py` | SQLite-backed nodes, edges, chunks, and file state |
| Repository search | `src/repolens/core/search/repository.py` | Snapshot caching, BM25, semantic ranking, graph queries |
| Path helpers | `src/repolens/core/paths.py` | Staging paths, published snapshots, active pointer, cleanup |

## Data layout

RepoLens keeps two different kinds of durable state:

1. Server-wide operational state in the registry database.
2. Repository-local code intelligence state in each repository tree.

### Registry database

`$REPOLENS_DATA_DIR/repositories/registry.db` stores:

- repository registrations
- index jobs
- MCP session activity
- job leases and retry metadata

This database is the durable journal for the scheduler. It is opened with SQLite
WAL mode and full synchronous writes so jobs survive process restarts.

### Repository-local index state

Each repository gets a `.repolens/` directory with these important paths:

| Path | Role |
|---|---|
| `.repolens/staging/<job-id>/index.db` | Temporary build target for a new index |
| `.repolens/versions/<version-id>/index.db` | Published read snapshot for a completed build |
| `.repolens/index.active` | Pointer to the current active snapshot |
| `.repolens/index.db` | Compatibility mirror of the active snapshot |
| `.repolens/state.json` | Pipeline checkpoint for resume/recovery |
| `.repolens/architecture.json` | Cached architecture summary for fast reads |

The important rule is simple: the writer builds in staging, then publishes a completed snapshot.
Readers should never depend on the staging tree.

## Event loop and worker model

The main event loop is only for protocol I/O and orchestration. It should not parse source files,
open SQLite write transactions, or do long-running filesystem work directly.

RepoLens uses three layers of execution:

1. The async event loop handles HTTP and MCP request framing.
2. `state.run_sync(...)` moves blocking work to a bounded `ThreadPoolExecutor`.
3. `IndexingService` has its own executor plus a dispatcher thread for durable job recovery
   and session-driven reindexing.

On Windows the server switches to `WindowsSelectorEventLoopPolicy` before starting the transport.
That keeps stdio and file-driven workflows predictable on this platform.

The practical outcome is that query calls, health calls, and indexing control calls can return
quickly even while a heavy parse/store job is running somewhere else.

## Indexing lifecycle

Indexing is deliberately split into a control plane and a data plane.

The control plane:

- registers the repository
- creates a durable job row
- returns a job ID immediately
- records MCP session activity for debounce/retry

The data plane:

- discovers indexable files
- parses ASTs
- resolves call edges
- chunks symbol ranges
- generates embeddings
- writes the graph and chunks to SQLite

The pipeline phases are:

1. Detect indexable source files.
2. Parse symbols and local edges.
3. Resolve call targets where possible.
4. Chunk each symbol's source range.
5. Embed the chunks.
6. Store the graph, chunks, vectors, and file state.
7. Publish the completed snapshot.
8. Clean up staging artifacts.

The orchestrator uses the repository's current supported-file set and ignores build outputs,
virtual environments, `.git/`, `.repolens/`, `node_modules/`, and similar noise directories.

### Why staging exists

Staging prevents readers from seeing a half-written database.
The worker writes to a temporary index under `.repolens/staging/`, then publishes only after the
SQLite file is complete.

That publish step matters on Windows, where file locking is less forgiving than on many UNIX
systems. The pattern is:

- build privately
- commit atomically
- flip a small pointer
- mirror to the legacy `index.db` path for compatibility

## Query lifecycle

Search, graph, health, and context tools follow the same shape:

1. Resolve the active repository from `repo_id`, session state, or workspace context.
2. Resolve the current snapshot through `index.active` or the fallback path logic.
3. Reuse an in-memory snapshot if the file signature has not changed.
4. Open the SQLite snapshot in read-only mode.
5. Return JSON payloads to the caller.

`RepositorySearch` caches:

- the loaded chunks
- the BM25 index
- the graph snapshot

The cache key is the snapshot signature, so repeated semantic or symbol searches do not keep
reopening and rebuilding the same in-memory structures.

## Journaling, locking, and crash recovery

RepoLens uses journaling at three levels:

### 1. SQLite journaling

Both the registry and the per-repo index use SQLite WAL mode for durability. Writers use
`BEGIN IMMEDIATE` so the database acquires the write lock up front instead of failing midway
through a transaction.

Important settings:

- `PRAGMA journal_mode=WAL`
- `PRAGMA synchronous=FULL`
- `PRAGMA foreign_keys=ON`
- `PRAGMA busy_timeout=...`

### 2. Durable job journaling

The registry database keeps the job history, job lease state, and MCP session schedule.
That means a restart does not lose:

- queued jobs
- running jobs with expired leases
- debounced session reindex deadlines

### 3. Pipeline checkpoint journaling

`state.json` stores the last known commit and index completion marker. This gives the orchestrator
a small recovery journal even before the next job is claimed.

### Locking rules

- Readers open the published snapshot read-only.
- Writers write only to staging.
- The active pointer is the only mutable read-selection file.
- Background bookkeeping must never block the protocol loop.

Those rules are what keep the server responsive while indexing is happening.

## Sequence diagram: indexing and publish

```mermaid
sequenceDiagram
    participant Client as "CLI / REST / MCP client"
    participant Loop as "Async event loop"
    participant Registry as "Registry SQLite"
    participant Queue as "IndexingService"
    participant Worker as "Index worker thread"
    participant Staging as "Staging DB"
    participant Snapshot as "Versioned snapshot"
    participant Pointer as "index.active"
    participant Mirror as "Legacy .repolens/index.db"

    Client->>Loop: Start index / reindex request
    Loop->>Registry: create durable job row
    Loop-->>Client: return job_id immediately

    Loop->>Queue: schedule _run_job(job_id)
    Queue->>Worker: parse / resolve / chunk / embed
    Worker->>Staging: write SQLite tables in transaction
    Worker->>Snapshot: backup completed staging DB
    Worker->>Pointer: atomically swap active snapshot pointer
    Worker->>Mirror: mirror active snapshot for compatibility
    Worker->>Registry: mark job complete + update repo stats
    Worker->>Staging: remove staging artifacts
```

## Sequence diagram: query and context retrieval

```mermaid
sequenceDiagram
    participant Client as "MCP / REST client"
    participant Loop as "Async event loop"
    participant Worker as "Query worker"
    participant Select as "Repository selection"
    participant Cache as "RepositorySearch cache"
    participant DB as "Read-only snapshot"

    Client->>Loop: search_symbols / search_semantic / get_context
    Loop->>Worker: offload blocking query work
    Worker->>Select: resolve repo_id, session, or workspace
    Worker->>Cache: reuse snapshot when signature is unchanged

    alt cache miss or changed snapshot
        Cache->>DB: load chunks and graph from SQLite
    end

    Worker->>DB: query nodes, edges, chunks, or file content
    Worker-->>Loop: JSON result
    Loop-->>Client: response
```

## Key architectural discussion

- Indexing is a durable job, not an inline request. The caller should never wait for full AST
  parsing and embedding unless it explicitly polls the job status.
- The event loop / I/O loop should stay thin. Any blocking filesystem, SQLite, or parsing work
  belongs in a worker thread.
- Journaling is not just for SQLite. The registry, the checkpoint file, and the active pointer all
  participate in recovery.
- The publish step is the safety boundary. Readers should only ever see a completed snapshot.
- Cleanup matters. Staging trees are temporary by design and should never accumulate forever.

## Operational invariants

- Never create an index in the user's home directory by accident.
- Never index into the current process cwd unless the caller explicitly selected that repository.
- Never block MCP or FastAPI handlers on indexing work.
- Never read from staging.
- Never treat the canonical mirror as the only source of truth; the active snapshot pointer wins.

These invariants are what make RepoLens reliable enough for long-running agent sessions.
