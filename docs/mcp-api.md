# MCP and REST API

RepoLens exposes the same persisted repository indexes through FastAPI and FastMCP.

## Repository and job API

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/repos` | Register a local repository |
| `GET` | `/api/repos` | List durable registrations and index state |
| `POST` | `/api/repos/{id}/index?mode=full` | Start a complete index |
| `POST` | `/api/repos/{id}/index?mode=incremental` | Index changed and deleted files |
| `GET` | `/api/repos/{id}/pipeline` | Get the latest durable job |
| `GET` | `/api/jobs` | List job history |
| `GET` | `/api/jobs/{id}` | Inspect one job, counts, and errors |

Repository registrations and jobs are stored in
`$REPOLENS_DATA_DIR/registry.db` (default: `./.repolens/registry.db`). Repository indexes remain
inside each target repository at `.repolens/index.db`. Both databases use SQLite WAL mode,
30-second busy handling, and full synchronous commits. Pipeline checkpoints are atomically
replaced after an `fsync`, so completed indexes, jobs, and MCP session schedules survive restart.

Index work runs in a bounded worker pool instead of the FastAPI or MCP event loop. Jobs are leased
in the registry before execution. A queued job, or a running job whose worker lease expired, is
recovered by the next RepoLens Web or MCP process using the same `REPOLENS_DATA_DIR`.

## Search API

```http
POST /api/search
Content-Type: application/json

{
  "repo_id": "repository-id",
  "query": "calculate invoice total",
  "mode": "hybrid",
  "top_k": 10
}
```

Modes are `bm25`, `semantic`, and `hybrid`. Hybrid mode uses reciprocal-rank fusion across
keyword and vector results. `GET /api/search/symbols` provides exact/partial AST symbol lookup.

For quick browser testing, the same search is available with query parameters:

```text
GET /api/search?repo_id=<id>&query=calculate%20invoice&mode=hybrid&top_k=10
```

Opening `/api/search` without the required `query` parameter returns validation guidance.

## Testing MCP tools through OpenAPI

The FastAPI bridge makes MCP tools testable from
`http://127.0.0.1:8420/api/docs` without starting a separate MCP client:

- `GET /api/mcp/tools` lists registered tools, descriptions, and input schemas.
- `POST /api/mcp/call` executes one registered MCP tool.

Example request:

```json
{
  "tool": "search_symbols",
  "arguments": {
    "name": "calculate_invoice",
    "repo_id": "your-repository-id"
  }
}
```

Example response shape:

```json
{
  "tool": "search_symbols",
  "arguments": {
    "name": "calculate_invoice",
    "repo_id": "your-repository-id"
  },
  "result": {
    "content": [
      {
        "type": "text",
        "text": "[...]"
      }
    ]
  }
}
```

This bridge is intended for local development and OpenAPI exploration. Native MCP clients should
continue using the configured MCP transport.

### Index the current MCP workspace

If the client workspace has not been registered yet, call `index_current_directory`. The tool
registers the MCP server's working directory, starts a full index when `.repolens/index.db` is
missing, and otherwise starts an incremental index. It returns immediately with a durable job ID.

OpenAPI request:

```json
{
  "tool": "index_current_directory",
  "arguments": {
    "mode": "auto"
  }
}
```

Example result:

```json
{
  "tool": "index_current_directory",
  "arguments": {
    "mode": "auto"
  },
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"status\":\"indexing_started\",\"repo_id\":\"...\",\"job_id\":\"...\"}"
      }
    ]
  }
}
```

Monitor the asynchronous job through MCP:

```json
{
  "tool": "get_index_status",
  "arguments": {
    "job_id": "the-returned-job-id"
  }
}
```

The equivalent REST status request is `GET /api/jobs/{job_id}`.

### Session-aware automatic indexing

Every MCP tool call persists the session ID, associated repository, working directory, and last
activity time. The next incremental index is debounced until 10 minutes after the most recent tool
call in that session. A later call moves the deadline forward. The schedule is durable, claimed by
only one running RepoLens process, and executed asynchronously by the indexing worker pool.

Automatic indexing only targets a registered repository. Call `index_current_directory` once when
the current workspace is missing. Set `REPOLENS_AUTO_INDEX_DELAY_SECONDS` to change the 600-second
delay or to use a shorter interval in development.

### Concurrency controls

MCP search, graph, context, architecture, Git, and health operations are dispatched to a bounded
thread pool, allowing independent requests to make progress without blocking the protocol loop.
Index jobs use a separate pool so large AST runs do not consume all query capacity.

| Variable | Default | Purpose |
|---|---:|---|
| `REPOLENS_MCP_WORKERS` | CPU-aware, 4–32 | Concurrent blocking MCP query workers |
| `REPOLENS_INDEX_WORKERS` | CPU-aware, 2–4 | Concurrent repository index workers |
| `REPOLENS_AUTO_INDEX_DELAY_SECONDS` | `600` | Idle debounce after the latest MCP call |
| `REPOLENS_INDEX_POLL_SECONDS` | `2` | Durable queue/session polling interval |
| `REPOLENS_INDEX_LEASE_SECONDS` | `900` | Worker lease before abandoned-job recovery |

## MCP configuration

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

Implemented index-backed tools:

- `search_semantic`
- `search_symbols`
- `get_context`
- `fetch_context`
- `find_callers`
- `find_callees`
- `query_graph`
- `recent_changes`
- `detect_changes`
- `get_architecture`
- `get_communities`
- `get_health`
- `list_repos`
- `index_current_directory`
- `get_index_status`

Pass `repo_id` when more than one indexed repository is registered. Context tools enforce a token
budget, truncate oversized primary symbols rather than returning empty content, and report the
estimated reduction in their rendered output.
