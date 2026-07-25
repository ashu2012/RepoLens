"""Resolves cross-file symbol references and calls."""

import re
import structlog
from typing import Dict, List

from repolens.core.ingestion.models import Confidence, EdgeInfo, EdgeKind, NodeInfo

logger = structlog.get_logger(__name__)


class CallResolver:
    """Resolves cross-file calls and import relationships."""

    def __init__(self) -> None:
        pass

    def resolve(
        self, nodes: List[NodeInfo], edges: List[EdgeInfo], file_index: Dict[str, str]
    ) -> List[EdgeInfo]:
        """Resolve import targets to actual definitions.

        Args:
            nodes: Extracted nodes.
            edges: Extracted edges.
            file_index: A dictionary mapping symbol names to file paths.

        Returns:
            A list of resolved EdgeInfo objects.
        """
        by_name: Dict[str, List[NodeInfo]] = {}
        by_qualified: Dict[str, NodeInfo] = {}
        by_id = {node.id: node for node in nodes}
        for node in nodes:
            by_name.setdefault(node.name, []).append(node)
            by_qualified[node.qualified_name] = node

        resolved_edges: List[EdgeInfo] = []
        for edge in edges:
            if edge.kind == EdgeKind.CONTAINS or edge.target in by_id:
                resolved_edges.append(edge)
                continue

            raw_target = edge.target
            candidate_name = raw_target.strip()
            if edge.kind == EdgeKind.CALLS:
                candidate_name = re.split(r"[.(\[]", candidate_name)[-1] or candidate_name
                candidate_name = raw_target.split(".")[-1].split("(")[0].strip()
            elif edge.kind == EdgeKind.IMPORTS_FROM:
                statement = raw_target.replace(",", " ")
                parts = statement.split()
                if parts and parts[0] in {"from", "import", "use", "require"}:
                    candidate_name = parts[1].split(".")[-1].strip("();'\"")

            candidates = by_name.get(candidate_name, [])
            if candidates:
                same_file = [node for node in candidates if node.file_path == edge.file_path]
                target = (same_file or candidates)[0]
                resolved_edges.append(
                    EdgeInfo(
                        kind=edge.kind,
                        source=edge.source,
                        target=target.id,
                        file_path=edge.file_path,
                        line=edge.line,
                        confidence=Confidence.INFERRED,
                        raw_target=raw_target,
                    )
                )
            else:
                edge.raw_target = raw_target
                resolved_edges.append(edge)

        return resolved_edges
