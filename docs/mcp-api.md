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
inside each target repository at `.repolens/index.db`.

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

Pass `repo_id` when more than one indexed repository is registered. Context tools enforce a token
budget, truncate oversized primary symbols rather than returning empty content, and report the
estimated reduction in their rendered output.
