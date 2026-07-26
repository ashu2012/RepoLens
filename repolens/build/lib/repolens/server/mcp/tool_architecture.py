"""Index-backed architecture summaries."""

import json
from collections import Counter

from repolens.core.graph.analysis import GraphAnalyzer
from repolens.core.graph.community import CommunityDetector

from .server import mcp, state


@mcp.tool()
async def get_architecture(repo_id: str | None = None) -> str:
    def analyze() -> str:
        graph = state.index(repo_id).store.load_graph()
        declared = [node for node, data in graph.nodes(data=True) if data.get("kind")]
        languages = Counter(graph.nodes[node].get("language") for node in declared)
        kinds = Counter(graph.nodes[node].get("kind") for node in declared)
        overview = {
            "symbols": len(declared),
            "edges": graph.number_of_edges(),
            "languages": dict(languages),
            "symbol_kinds": dict(kinds),
            "hub_symbols": GraphAnalyzer().hub_nodes(graph, 10),
        }
        return json.dumps(overview, indent=2)

    return await state.run_sync(analyze)


@mcp.tool()
async def get_communities(repo_id: str | None = None) -> str:
    def detect() -> str:
        graph = state.index(repo_id).store.load_graph()
        declared = graph.subgraph(
            [node for node, data in graph.nodes(data=True) if data.get("kind")]
        ).copy()
        if not declared.nodes:
            return "[]"
        communities = CommunityDetector().detect(declared)
        grouped: dict[int, list[str]] = {}
        for node, community in communities.items():
            grouped.setdefault(community, []).append(
                declared.nodes[node].get("qualified_name", node)
            )
        return json.dumps(grouped, indent=2)

    return await state.run_sync(detect)
