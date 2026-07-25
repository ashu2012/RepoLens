"""Search and context access over a persisted RepoLens index."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from repolens.core.graph.store import GraphStore
from repolens.core.providers.base import MockEmbedder
from repolens.core.search.bm25 import BM25Index


class RepositorySearch:
    def __init__(self, repo_path: str | Path) -> None:
        self.repo_path = Path(repo_path).resolve()
        index_path = self.repo_path / ".repolens" / "index.db"
        if not index_path.exists():
            raise FileNotFoundError(f"Repository is not indexed: {self.repo_path}")
        self.store = GraphStore(index_path)

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        denominator = math.sqrt(sum(v * v for v in left)) * math.sqrt(sum(v * v for v in right))
        return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0.0

    async def search(self, query: str, mode: str = "hybrid", top_k: int = 10) -> list[dict[str, Any]]:
        if not query.strip():
            return []
        if mode == "default" or mode == "auto":
            mode = "hybrid"
        if mode not in {"bm25", "semantic", "hybrid"}:
            raise ValueError("mode must be bm25, semantic, hybrid, or auto")
        chunks = self.store.load_chunks()
        if not chunks:
            return []

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
        by_id = {chunk["id"]: chunk for chunk in chunks}
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
            semantic = (
                sorted(
                    (
                        (chunk["id"], self._cosine(query_vector, chunk["embedding"]))
                        for chunk in chunks if chunk["embedding"]
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
