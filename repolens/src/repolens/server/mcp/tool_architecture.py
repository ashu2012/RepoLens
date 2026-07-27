"""Index-backed architecture summaries."""

import json
from collections import Counter
from pathlib import Path

from repolens.core.graph.analysis import GraphAnalyzer, architecture_focus_graph
from repolens.core.paths import repolens_architecture_snapshot_path

from .server import mcp, state


def _load_snapshot(repo_root: str | Path) -> dict | None:
    path = repolens_architecture_snapshot_path(repo_root)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


@mcp.tool()
async def get_architecture(repo_id: str | None = None) -> str:
    def analyze() -> str:
        repo = state.repository(repo_id)
        snapshot = _load_snapshot(repo["local_path"])
        if snapshot is not None:
            overview = {
                "symbols": snapshot.get("symbols", 0),
                "edges": snapshot.get("edges", 0),
                "languages": snapshot.get("languages", {}),
                "symbol_kinds": snapshot.get("symbol_kinds", {}),
                "hub_symbols": [
                    hub for hub in snapshot.get("hub_symbols", [])
                    if "import" not in str(hub).lower()
                ],
            }
        else:
            graph = architecture_focus_graph(state.index(repo["id"]).graph())
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
        repo = state.repository(repo_id)
        snapshot = _load_snapshot(repo["local_path"])
        if snapshot is not None and snapshot.get("communities") is not None:
            cleaned = {
                community: [
                    node for node in nodes
                    if "import" not in str(node).lower()
                ]
                for community, nodes in snapshot["communities"].items()
            }
            cleaned = {community: nodes for community, nodes in cleaned.items() if nodes}
            return json.dumps(cleaned, indent=2)
        graph = architecture_focus_graph(state.index(repo["id"]).graph())
        declared = graph.subgraph([node for node, data in graph.nodes(data=True) if data.get("kind")]).copy()
        if not declared.nodes:
            return "[]"
        from repolens.core.graph.community import CommunityDetector

        communities = CommunityDetector().detect(declared)
        grouped: dict[int, list[str]] = {}
        for node, community in communities.items():
            grouped.setdefault(community, []).append(
                declared.nodes[node].get("qualified_name", node)
            )
        return json.dumps(grouped, indent=2)

    return await state.run_sync(detect)
