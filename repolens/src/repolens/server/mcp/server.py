"""Main FastMCP server setup."""
import asyncio
import sys
from fastmcp import FastMCP

mcp = FastMCP("repolens", instructions="RepoLens code intelligence...")

class ServerState:
    """Shared state object for MCP tools."""
    def __init__(self):
        self.graph = None
        self.search_index = None
        self.config = None

    def repository(self, repo_id: str | None = None) -> dict:
        from repolens.core.persistence import registry

        if repo_id:
            repo = registry.get_repo(repo_id)
            if not repo:
                raise ValueError(f"Unknown repository: {repo_id}")
            return repo
        indexed = [repo for repo in registry.list_repos() if repo["status"] == "indexed"]
        if len(indexed) != 1:
            raise ValueError(
                "repo_id is required unless exactly one indexed repository is registered"
            )
        return indexed[0]

    def index(self, repo_id: str | None = None):
        from repolens.core.search.repository import RepositorySearch

        return RepositorySearch(self.repository(repo_id)["local_path"])

state = ServerState()

# Import tool modules to register their decorators with `mcp`
from . import (
    tool_architecture,
    tool_changes,
    tool_context,
    tool_graph,
    tool_health,
    tool_search,
)

async def run_stdio():
    """Run the MCP server over stdio transport."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    def _run():
        mcp.run()
        
    await asyncio.to_thread(_run)

async def run_http(host: str = "127.0.0.1", port: int = 5000):
    """Run the MCP server over HTTP transport."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    def _run():
        mcp.run(transport="sse", host=host, port=port)
        
    await asyncio.to_thread(_run)
