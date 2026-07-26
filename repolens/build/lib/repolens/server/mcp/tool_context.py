"""Token-budgeted MCP context retrieval."""

from pathlib import Path
from typing import Optional

from repolens.core.distill.context_builder import ContextBuilder
from repolens.core.distill.skeleton import SkeletonSymbol, build_skeleton

from .server import mcp, state


@mcp.tool()
async def get_context(
    targets: list[str], budget: int = 4000, repo_id: str | None = None
) -> str:
    def build() -> str:
        index = state.index(repo_id)
        symbols = index.context_targets(targets)
        result = ContextBuilder(budget=max(100, budget)).build_for_symbols(
            symbols,
            file_reader=index.read_file,
        )
        return result.render()

    return await state.run_sync(build)


@mcp.tool()
async def fetch_context(
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    budget: int = 1800,
    repo_id: str | None = None,
) -> str:
    def fetch() -> str:
        index = state.index(repo_id)
        source = index.read_file(file_path)
        if start_line is not None or end_line is not None:
            lines = source.splitlines()
            start = max(1, start_line or 1)
            end = min(len(lines), end_line or len(lines))
            return "\n".join(lines[start - 1:end])
        symbols = [
            SkeletonSymbol(
                name=node["name"],
                kind=node["kind"],
                start_line=node["line_start"],
                end_line=node["line_end"],
            )
            for node in index.store.list_nodes()
            if node["file_path"] == Path(file_path).as_posix()
        ]
        return build_skeleton(source, symbols=symbols, token_budget=budget).skeleton

    return await state.run_sync(fetch)
