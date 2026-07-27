import networkx as nx
from typing import Dict, List, Any

ARCHITECTURE_NODE_KINDS = {"class", "function", "method", "type", "test"}
ARCHITECTURE_EDGE_KINDS = {"CALLS", "CONTAINS", "INHERITS", "IMPLEMENTS", "TESTED_BY"}


def architecture_focus_graph(graph: nx.DiGraph) -> nx.DiGraph:
    focused = nx.DiGraph()
    for node, data in graph.nodes(data=True):
        if str(data.get("kind", "")).lower() not in ARCHITECTURE_NODE_KINDS:
            continue
        focused.add_node(node, **data)
    for source, target, data in graph.edges(data=True):
        if source not in focused or target not in focused:
            continue
        if str(data.get("kind", "")).upper() not in ARCHITECTURE_EDGE_KINDS:
            continue
        focused.add_edge(source, target, **data)
    return focused

class GraphAnalyzer:
    def hub_nodes(self, graph: nx.DiGraph, top_k: int = 10) -> list:
        graph = architecture_focus_graph(graph)
        in_degrees = dict(graph.in_degree())
        sorted_nodes = sorted(in_degrees.items(), key=lambda x: x[1], reverse=True)
        return [node for node, degree in sorted_nodes[:top_k]]

    def bridge_nodes(self, graph: nx.DiGraph, top_k: int = 10) -> list:
        graph = architecture_focus_graph(graph)
        bridge_scores = {}
        for node in graph.nodes():
            node_comm = graph.nodes[node].get("community")
            if node_comm is None:
                continue
                
            connected_comms = set()
            for neighbor in graph.successors(node):
                neighbor_comm = graph.nodes[neighbor].get("community")
                if neighbor_comm is not None and neighbor_comm != node_comm:
                    connected_comms.add(neighbor_comm)
            for neighbor in graph.predecessors(node):
                neighbor_comm = graph.nodes[neighbor].get("community")
                if neighbor_comm is not None and neighbor_comm != node_comm:
                    connected_comms.add(neighbor_comm)
                    
            bridge_scores[node] = len(connected_comms)
            
        sorted_bridges = sorted(bridge_scores.items(), key=lambda x: x[1], reverse=True)
        return [node for node, score in sorted_bridges[:top_k] if score > 0]

    def god_nodes(self, graph: nx.DiGraph, threshold: int = 20) -> list:
        graph = architecture_focus_graph(graph)
        degrees = dict(graph.degree())
        return [node for node, degree in degrees.items() if degree > threshold]

    def architecture_overview(self, graph: nx.DiGraph) -> dict:
        graph = architecture_focus_graph(graph)
        overview = {
            "communities": {},
            "key_nodes": self.hub_nodes(graph, 5),
            "cross_community_edges": 0
        }
        
        for node, data in graph.nodes(data=True):
            comm = data.get("community")
            if comm is not None:
                if comm not in overview["communities"]:
                    overview["communities"][comm] = 0
                overview["communities"][comm] += 1
                
        for u, v in graph.edges():
            u_comm = graph.nodes[u].get("community")
            v_comm = graph.nodes[v].get("community")
            if u_comm is not None and v_comm is not None and u_comm != v_comm:
                overview["cross_community_edges"] += 1
                
        return overview
