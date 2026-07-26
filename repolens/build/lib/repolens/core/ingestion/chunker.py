"""Chunker for breaking down source files into symbol-based chunks."""

import structlog
from typing import List

from repolens.core.ingestion.models import ChunkInfo, EdgeInfo, NodeInfo

logger = structlog.get_logger(__name__)


class SymbolChunker:
    """Chunks source files based on AST symbol boundaries."""

    def __init__(self) -> None:
        pass

    def chunk_file(
        self, file_path: str, nodes: List[NodeInfo], edges: List[EdgeInfo]
    ) -> List[ChunkInfo]:
        """Chunk a file into logical pieces, never splitting a function.

        Args:
            file_path: The path to the file.
            nodes: Extracted nodes from the file.
            edges: Extracted edges from the file.

        Returns:
            A list of ChunkInfo objects.
        """
        chunks: List[ChunkInfo] = []
        source_lines = []
        try:
            source_lines = open(file_path, "r", encoding="utf-8", errors="replace").readlines()
        except OSError as exc:
            logger.warning("chunk.read_failed", file_path=file_path, error=str(exc))

        for node in nodes:
            chunk_id = node.id or f"{node.file_path}::{node.name}::{node.line_start}"
            metadata = {
                "language": node.language,
                "imports": [],
                "symbols_referenced": [],
            }
            chunks.append(
                ChunkInfo(
                    id=chunk_id,
                    content="".join(source_lines[node.line_start - 1:node.line_end]),
                    file_path=node.file_path,
                    symbol_name=node.name,
                    symbol_kind=node.kind.value,
                    line_start=node.line_start,
                    line_end=node.line_end,
                    language=node.language,
                    metadata=metadata,
                )
            )

        return chunks
