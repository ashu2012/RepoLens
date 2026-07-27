"""Search and context access over a persisted RepoLens index."""

from __future__ import annotations

import os
import math
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repolens.core.graph.store import GraphStore
from repolens.core.providers.base import MockEmbedder
from repolens.core.search.bm25 import BM25Index


@dataclass(frozen=True)
class _SearchSnapshot:
    signature: tuple[int, int]
    chunks: list[dict[str, Any]]
    by_id: dict[str, dict[str, Any]]
    bm25: BM25Index
    semantic_chunks: list[tuple[str, list[float]]]


class RepositorySearch:
    _cache_lock = threading.RLock()
    _snapshot_cache: "OrderedDict[Path, _SearchSnapshot]" = OrderedDict()
    _max_cache_entries = max(1, int(os.environ.get("REPOLENS_SEARCH_CACHE_LIMIT", "8")))

    def __init__(self, repo_path: str | Path) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.index_path = self.repo_path / ".repolens" / "index.db"
        if not self.index_path.exists():
            raise FileNotFoundError(f"Repository is not indexed: {self.repo_path}")
        self.store = GraphStore(self.index_path, read_only=True)

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        denominator = math.sqrt(sum(v * v for v in left)) * math.sqrt(sum(v * v for v in right))
        return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0.0

    @staticmethod
    def _normalize(vector: list[float]) -> list[float]:
        denominator = math.sqrt(sum(value * value for value in vector))
        return [value / denominator for value in vector] if denominator else vector

    def _snapshot_signature(self) -> tuple[int, int]:
        stat = self.index_path.stat()
        return stat.st_mtime_ns, stat.st_size

    def _build_snapshot(self, signature: tuple[int, int]) -> _SearchSnapshot:
        chunks = self.store.load_chunks()
        by_id = {chunk["id"]: chunk for chunk in chunks}
        bm25 = BM25Index()
        bm25.add_documents(
            [
                (
                    chunk["id"],
                    f"{chunk['symbol_name']} {chunk['file_path']} {chunk['content']}",
                )
                for chunk in chunks
            ]
        )
        semantic_chunks = [
            (chunk["id"], self._normalize([float(value) for value in chunk["embedding"]]))
            for chunk in chunks
            if chunk.get("embedding")
        ]
        return _SearchSnapshot(
            signature=signature,
            chunks=chunks,
            by_id=by_id,
            bm25=bm25,
            semantic_chunks=semantic_chunks,
        )

    def _snapshot(self) -> _SearchSnapshot:
        signature = self._snapshot_signature()
        with self._cache_lock:
            cached = self._snapshot_cache.get(self.index_path)
            if cached and cached.signature == signature:
                self._snapshot_cache.move_to_end(self.index_path)
                return cached

        snapshot = self._build_snapshot(signature)
        with self._cache_lock:
            cached = self._snapshot_cache.get(self.index_path)
            if cached and cached.signature == signature:
                self._snapshot_cache.move_to_end(self.index_path)
                return cached
            self._snapshot_cache[self.index_path] = snapshot
            self._snapshot_cache.move_to_end(self.index_path)
            while len(self._snapshot_cache) > self._max_cache_entries:
                self._snapshot_cache.popitem(last=False)
        return snapshot

    @classmethod
    def clear_cache(cls) -> None:
        with cls._cache_lock:
            cls._snapshot_cache.clear()
            cls._graph_cache.clear()

    async def search(self, query: str, mode: str = "hybrid", top_k: int = 10) -> list[dict[str, Any]]:
        if not query.strip():
            return []
        if mode == "default" or mode == "auto":
            mode = "hybrid"
        if mode not in {"bm25", "semantic", "hybrid"}:
            raise ValueError("mode must be bm25, semantic, hybrid, or auto")
        snapshot = self._snapshot()
        chunks = snapshot.chunks
        if not chunks:
            return []
        bm25 = snapshot.bm25
        by_id = snapshot.by_id
        rankings: dict[str, float] = {}
        sources: dict[str, set[str]] = {}
        rrf_k = 60

        if mode in {"bm25", "hybrid"}:
            for rank, (chunk_id, _) in enumerate(bm25.search(query, top_k=max(top_k * 4, 20))):
                rankings[chunk_id] = rankings.get(chunk_id, 0.0) + 1 / (rrf_k + rank + 1)
                sources.setdefault(chunk_id, set()).add("bm25")

        if mode in {"semantic", "hybrid"}:
            model_name = next(
                (chunk["embedding_model"] for chunk in chunks if chunk["embedding_model"]),
                "repolens-hash-v1",
            )
            if model_name.startswith("ollama:"):
                from repolens.core.providers.ollama import OllamaEmbedder

                try:
                    query_vector = (
                        await OllamaEmbedder(model=model_name.split(":", 1)[1]).embed([query])
                    )[0]
                except Exception:
                    query_vector = []
            else:
                query_vector = (await MockEmbedder().embed([query]))[0]
            query_vector = self._normalize([float(value) for value in query_vector])
            semantic = (
                sorted(
                    (
                        (chunk_id, sum(a * b for a, b in zip(query_vector, chunk_vec)))
                        for chunk_id, chunk_vec in snapshot.semantic_chunks
                    ),
                    key=lambda item: item[1],
                    reverse=True,
                )
                if query_vector else []
            )
            for rank, (chunk_id, _) in enumerate(semantic[:max(top_k * 4, 20)]):
                rankings[chunk_id] = rankings.get(chunk_id, 0.0) + 1 / (rrf_k + rank + 1)
                sources.setdefault(chunk_id, set()).add("semantic")

        results = []
        for chunk_id, score in sorted(rankings.items(), key=lambda item: item[1], reverse=True)[:top_k]:
            chunk = by_id[chunk_id]
            content = chunk["content"].strip()
            results.append(
                {
                    "chunk_id": chunk_id,
                    "score": round(score, 8),
                    "file_path": chunk["file_path"],
                    "symbol_name": chunk["symbol_name"],
                    "symbol_kind": chunk["symbol_kind"],
                    "line_start": chunk["line_start"],
                    "line_end": chunk["line_end"],
                    "snippet": content[:700],
                    "source": "+".join(sorted(sources.get(chunk_id, {"unknown"}))),
                }
            )
        return results

    def symbols(self, name: str, kind: str | None = None, limit: int = 50) -> list[dict]:
        return self.store.find_symbols(name, kind=kind, limit=limit)

    def graph(self) -> nx.DiGraph:
        return self._graph_snapshot().graph

    @dataclass(frozen=True)
    class _GraphSnapshot:
        signature: tuple[int, int]
        graph: Any

    _graph_cache: "OrderedDict[Path, _GraphSnapshot]" = OrderedDict()

    def _graph_snapshot(self) -> _GraphSnapshot:
        signature = self._snapshot_signature()
        with self._cache_lock:
            cached = self._graph_cache.get(self.index_path)
            if cached and cached.signature == signature:
                self._graph_cache.move_to_end(self.index_path)
                return cached

        graph = self.store.load_graph()
        snapshot = self._GraphSnapshot(signature=signature, graph=graph)
        with self._cache_lock:
            cached = self._graph_cache.get(self.index_path)
            if cached and cached.signature == signature:
                self._graph_cache.move_to_end(self.index_path)
                return cached
            self._graph_cache[self.index_path] = snapshot
            self._graph_cache.move_to_end(self.index_path)
            while len(self._graph_cache) > self._max_cache_entries:
                self._graph_cache.popitem(last=False)
        return snapshot

    def context_targets(self, targets: list[str]) -> list[dict]:
        found: dict[str, dict] = {}
        for target in targets:
            for symbol in self.symbols(target, limit=10):
                found[symbol["id"]] = symbol
        return list(found.values())

    def read_file(self, relative_path: str) -> str:
        candidate = (self.repo_path / relative_path).resolve()
        try:
            candidate.relative_to(self.repo_path)
        except ValueError as exc:
            raise ValueError("File path escapes the registered repository") from exc
        return candidate.read_text(encoding="utf-8", errors="replace")
