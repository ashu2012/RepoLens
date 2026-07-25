"""Repository indexing orchestration."""

from __future__ import annotations

import hashlib
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import structlog

logger = structlog.get_logger(__name__)
ProgressCallback = Callable[[str, int], None]


@dataclass
class PhaseResult:
    name: str
    duration_s: float
    items_processed: int
    status: str


@dataclass
class PipelineResult:
    files_processed: int
    symbols_extracted: int
    edges_resolved: int
    duration_s: float
    phases: list[PhaseResult] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)


class PipelineOrchestrator:
    """Build and update repository-local AST, graph, chunk, and vector indexes."""

    IGNORED_DIRS = {".git", ".repolens", "node_modules", "__pycache__", ".venv", "venv"}

    @staticmethod
    def _hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _head(root: Path) -> str | None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            return result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None

    def _discover(self, root: Path, parser) -> list[Path]:
        return sorted(
            (
                path for path in root.rglob("*")
                if path.is_file()
                and not self.IGNORED_DIRS.intersection(path.parts)
                and path.suffix.lower() in parser.SUPPORTED_EXTENSIONS
            ),
            key=lambda path: path.as_posix(),
        )

    async def _embed(self, chunks: list) -> tuple[dict[str, list[float]], str]:
        # Deterministic local embeddings keep indexing offline and make the
        # vector path testable. Configured Ollama/pgvector backends can replace
        # this adapter without changing the persisted chunk contract.
        from repolens.core.providers.base import MockEmbedder
        from repolens.core.providers.ollama import OllamaEmbedder

        provider = os.environ.get("REPOLENS_EMBEDDING_PROVIDER", "mock").lower()
        embedder = MockEmbedder()
        model_name = "repolens-hash-v1"
        if provider == "ollama":
            ollama = OllamaEmbedder()
            if await ollama.is_available():
                embedder = ollama
                model_name = f"ollama:{ollama._model}"
            else:
                logger.warning("ollama_unavailable_using_local_hash_embeddings")
        embeddings: dict[str, list[float]] = {}
        batch_size = 128
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start:start + batch_size]
            vectors = await embedder.embed([chunk.content for chunk in batch])
            embeddings.update({chunk.id: vector for chunk, vector in zip(batch, vectors)})
        return embeddings, model_name

    async def run_full(
        self,
        repo_path: str,
        on_progress: ProgressCallback | None = None,
    ) -> PipelineResult:
        from repolens.core.graph.builder import GraphBuilder
        from repolens.core.graph.store import GraphStore
        from repolens.core.ingestion.call_resolver import CallResolver
        from repolens.core.ingestion.chunker import SymbolChunker
        from repolens.core.ingestion.parser import CodeParser
        from repolens.core.pipeline.checkpoint import Checkpoint

        start = time.time()
        root = Path(repo_path).resolve()
        if not root.is_dir():
            raise ValueError(f"Repository path is not a directory: {root}")
        parser, chunker = CodeParser(), SymbolChunker()
        files = self._discover(root, parser)
        if not files:
            raise ValueError("No supported source files were found")
        phases: list[PhaseResult] = []
        if on_progress:
            on_progress("detect", 5)

        parse_start = time.time()
        nodes, edges, chunks = [], [], []
        file_states: dict[str, tuple[str, str | None, float]] = {}
        for index, path in enumerate(files, 1):
            file_nodes, file_edges = parser.parse_file(path, repo_root=root)
            nodes.extend(file_nodes)
            edges.extend(file_edges)
            chunks.extend(chunker.chunk_file(str(path), file_nodes, file_edges))
            relative = path.relative_to(root).as_posix()
            language = parser._detect_language(path)
            file_states[relative] = (self._hash(path), language, time.time())
            if on_progress:
                on_progress("parse", 5 + int(50 * index / len(files)))
        phases.append(PhaseResult("parse", time.time() - parse_start, len(files), "success"))
        if not nodes:
            raise RuntimeError("AST parsing completed but extracted zero symbols")

        resolve_start = time.time()
        edges = CallResolver().resolve(nodes, edges, {})
        phases.append(PhaseResult("resolve", time.time() - resolve_start, len(edges), "success"))
        if on_progress:
            on_progress("embed", 65)
        embed_start = time.time()
        embeddings, embedding_model = await self._embed(chunks)
        phases.append(PhaseResult("embed", time.time() - embed_start, len(embeddings), "success"))

        if on_progress:
            on_progress("store", 85)
        store_start = time.time()
        store = GraphStore(root / ".repolens" / "index.db")
        store.replace_index(
            GraphBuilder().build(nodes, edges),
            chunks,
            file_states,
            embeddings,
            embedding_model,
        )
        stats = store.get_stats()
        phases.append(PhaseResult("store", time.time() - store_start, sum(stats.values()), "success"))

        checkpoint = Checkpoint()
        checkpoint.last_commit = self._head(root)
        checkpoint.last_full_index = time.time()
        checkpoint.phase_completed = "complete"
        checkpoint.save(str(root))
        if on_progress:
            on_progress("complete", 100)
        return PipelineResult(
            files_processed=len(files),
            symbols_extracted=stats["total_nodes"],
            edges_resolved=stats["total_edges"],
            duration_s=time.time() - start,
            phases=phases,
            stats=stats,
        )

    async def run_incremental(
        self,
        repo_path: str,
        last_commit: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> PipelineResult:
        from repolens.core.graph.builder import GraphBuilder
        from repolens.core.graph.store import GraphStore
        from repolens.core.ingestion.call_resolver import CallResolver
        from repolens.core.ingestion.chunker import SymbolChunker
        from repolens.core.ingestion.models import NodeInfo, NodeKind
        from repolens.core.ingestion.parser import CodeParser
        from repolens.core.pipeline.checkpoint import Checkpoint

        started = time.time()
        root = Path(repo_path).resolve()
        store_path = root / ".repolens" / "index.db"
        if not store_path.exists():
            return await self.run_full(repo_path, on_progress)
        store = GraphStore(store_path)
        parser, chunker = CodeParser(), SymbolChunker()
        files = self._discover(root, parser)
        current = {path.relative_to(root).as_posix(): path for path in files}
        previous = store.get_file_states()
        hashes = {relative: self._hash(path) for relative, path in current.items()}
        changed = {path for path, digest in hashes.items() if previous.get(path) != digest}
        deleted = set(previous) - set(current)
        affected = changed | deleted
        if on_progress:
            on_progress("detect", 15)
        if not affected:
            stats = store.get_stats()
            if on_progress:
                on_progress("complete", 100)
            return PipelineResult(0, 0, 0, time.time() - started, stats=stats)

        # Existing symbols provide the catalog needed to resolve calls in changed files.
        catalog: list[NodeInfo] = []
        for data in store.list_nodes(exclude_paths=affected):
            try:
                node_kind = NodeKind(data["kind"])
            except ValueError:
                node_kind = NodeKind.FUNCTION
            catalog.append(
                NodeInfo(
                    kind=node_kind,
                    name=data["name"],
                    file_path=data["file_path"],
                    line_start=data["line_start"] or 1,
                    line_end=data["line_end"] or 1,
                    language=data["language"] or "",
                    parent_name=data["parent_name"],
                    params=[],
                    return_type=None,
                    modifiers=[],
                    is_test=False,
                    content_hash=data["content_hash"] or "",
                    id=data["id"],
                    qualified_name=data["qualified_name"],
                )
            )

        nodes, edges, chunks = [], [], []
        file_states: dict[str, tuple[str, str | None, float]] = {}
        for index, relative in enumerate(sorted(changed), 1):
            path = current[relative]
            file_nodes, file_edges = parser.parse_file(path, repo_root=root)
            nodes.extend(file_nodes)
            edges.extend(file_edges)
            chunks.extend(chunker.chunk_file(str(path), file_nodes, file_edges))
            file_states[relative] = (
                hashes[relative], parser._detect_language(path), time.time()
            )
            if on_progress:
                on_progress("parse", 15 + int(45 * index / max(1, len(changed))))

        edges = CallResolver().resolve(catalog + nodes, edges, {})
        if on_progress:
            on_progress("embed", 70)
        embeddings, embedding_model = await self._embed(chunks)
        store.apply_incremental(
            affected,
            GraphBuilder().build(nodes, edges),
            chunks,
            file_states,
            embeddings,
            embedding_model,
        )
        stats = store.get_stats()
        checkpoint = Checkpoint.load(str(root)) or Checkpoint()
        checkpoint.last_commit = self._head(root)
        checkpoint.last_incremental = time.time()
        checkpoint.phase_completed = "complete"
        checkpoint.save(str(root))
        if on_progress:
            on_progress("complete", 100)
        return PipelineResult(
            files_processed=len(affected),
            symbols_extracted=len(nodes),
            edges_resolved=len(edges),
            duration_s=time.time() - started,
            phases=[
                PhaseResult("detect", 0, len(affected), "success"),
                PhaseResult("parse", 0, len(changed), "success"),
                PhaseResult("delete", 0, len(deleted), "success"),
            ],
            stats=stats,
        )
