import networkx as nx
from typing import Optional, List
from .builder import NodeInfo

class GraphQuery:
    def __init__(self, graph: nx.DiGraph):
        self.graph = graph

    def _node_to_info(self, name: str) -> NodeInfo:
        data = self.graph.nodes[name]
        return NodeInfo(
            id=name,
            name=name,
            kind=data.get("kind", ""),
            file_path=data.get("file_path", ""),
            line_start=data.get("line_start"),
            line_end=data.get("line_end"),
            language=data.get("language")
        )

    def callers_of(self, symbol: str) -> list[NodeInfo]:
        if symbol not in self.graph:
            return []
        callers = [u for u, v, d in self.graph.in_edges(symbol, data=True) if str(d.get("kind")).upper() == "CALLS"]
        return [self._node_to_info(n) for n in callers]

    def callees_of(self, symbol: str) -> list[NodeInfo]:
        if symbol not in self.graph:
            return []
        callees = [v for u, v, d in self.graph.out_edges(symbol, data=True) if str(d.get("kind")).upper() == "CALLS"]
        return [self._node_to_info(n) for n in callees]

    def imports_of(self, file_path: str) -> list[str]:
        imports = []
        for u, v, d in self.graph.edges(data=True):
            if d.get("kind") == "IMPORTS_FROM" and d.get("file_path") == file_path:
                imports.append(v)
        return list(set(imports))

    def importers_of(self, file_path: str) -> list[str]:
        importers = []
        for u, v, d in self.graph.edges(data=True):
            if d.get("kind") == "IMPORTS_FROM":
                target_node = self.graph.nodes.get(v, {})
                if target_node.get("file_path") == file_path:
                    importers.append(d.get("file_path", ""))
        return list(set(importers))

    def children_of(self, symbol: str) -> list[NodeInfo]:
        if symbol not in self.graph:
            return []
        children = [v for u, v, d in self.graph.out_edges(symbol, data=True) if d.get("kind") == "CONTAINS"]
        return [self._node_to_info(n) for n in children]

    def tests_for(self, symbol: str) -> list[NodeInfo]:
        if symbol not in self.graph:
            return []
        tests = [u for u, v, d in self.graph.in_edges(symbol, data=True) if d.get("kind") == "TESTED_BY"]
        return [self._node_to_info(n) for n in tests]

    def inheritors_of(self, class_name: str) -> list[NodeInfo]:
        if class_name not in self.graph:
            return []
        inheritors = [u for u, v, d in self.graph.in_edges(class_name, data=True) if d.get("kind") == "INHERITS"]
        return [self._node_to_info(n) for n in inheritors]

    def traverse(self, start: str, direction: str = "forward", max_hops: int = 3) -> list[NodeInfo]:
        if start not in self.graph:
            return []
        visited = set()
        queue = [(start, 0)]
        while queue:
            current, hop = queue.pop(0)
            if hop > max_hops:
                continue
            if current not in visited:
                visited.add(current)
                if direction == "forward":
                    neighbors = self.graph.successors(current)
                else:
                    neighbors = self.graph.predecessors(current)
                for n in neighbors:
                    queue.append((n, hop + 1))
        return [self._node_to_info(n) for n in visited if n != start]

    def find_symbol(self, name: str, kind: Optional[str] = None) -> list[NodeInfo]:
        matches = []
        name_lower = name.lower()
        for n, d in self.graph.nodes(data=True):
            if name_lower in n.lower():
                if kind is None or d.get("kind") == kind:
                    matches.append(self._node_to_info(n))
        return matches
