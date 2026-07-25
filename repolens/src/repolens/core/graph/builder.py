import networkx as nx
from dataclasses import dataclass
from typing import Optional

@dataclass
class NodeInfo:
    id: str
    name: str
    kind: str
    file_path: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    language: Optional[str] = None
    parent_name: Optional[str] = None
    content_hash: Optional[str] = None

@dataclass
class EdgeInfo:
    source: str
    target: str
    kind: str
    file_path: str
    line: Optional[int] = None
    confidence: float = 1.0
    raw_target: Optional[str] = None

class GraphBuilder:
    def build(self, nodes: list[NodeInfo], edges: list[EdgeInfo]) -> nx.DiGraph:
        graph = nx.DiGraph()
        
        # Stable AST ids prevent same-named symbols in different files from merging.
        seen_nodes = set()
        
        for node in nodes:
            node_key = node.id
            if node_key not in seen_nodes:
                seen_nodes.add(node_key)
                graph.add_node(
                    node.id,
                    name=node.name,
                    qualified_name=getattr(node, "qualified_name", node.name),
                    kind=node.kind.value if hasattr(node.kind, "value") else node.kind,
                    file_path=node.file_path, 
                    line_start=node.line_start, 
                    line_end=node.line_end, 
                    language=node.language,
                    parent_name=node.parent_name,
                    content_hash=node.content_hash
                )
        
        for edge in edges:
            graph.add_edge(
                edge.source,
                edge.target,
                kind=edge.kind.value if hasattr(edge.kind, "value") else edge.kind,
                confidence=edge.confidence.value if hasattr(edge.confidence, "value") else edge.confidence,
                raw_target=getattr(edge, "raw_target", None),
                file_path=edge.file_path,
                line=edge.line
            )
            
        return graph
