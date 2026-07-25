"""Ollama embedding provider for RepoLens.

Uses Ollama's native ``/api/embed`` endpoint for local embedding generation.
Supports configurable models, dimensions, and timeouts.
"""

from __future__ import annotations

import math
import os
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "nomic-embed-text"
_DEFAULT_TIMEOUT = 30.0


def _infer_dimensions(model: str) -> int:
    """Best-effort dimension hint for common Ollama embedding models."""
    name = model.lower()
    if "all-minilm" in name or "minilm" in name:
        return 384
    if "mxbai-embed-large" in name or "bge-m3" in name:
        return 1024
    if "nomic-embed-text" in name or "embeddinggemma" in name:
        return 768
    if "qwen3-embedding" in name:
        if "4b" in name:
            return 2560
        if "8b" in name:
            return 4096
        return 1024
    return 768


def _l2_normalize(vec: list[float]) -> list[float]:
    """L2-normalize a vector to unit length."""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        norm = 1.0
    return [x / norm for x in vec]


class OllamaEmbedder:
    """Ollama embedding adapter implementing the RepoLens Embedder protocol.

    Args:
        model: Ollama embedding model name. Defaults to ``nomic-embed-text``.
        base_url: Ollama server URL. Defaults to ``http://localhost:11434``.
        dimensions: Optional output dimension hint.
        timeout: Per-request timeout in seconds.
    """

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        dimensions: int | None = None,
        timeout: float | None = None,
    ) -> None:
        self._model = (
            model
            or os.environ.get("REPOLENS_EMBEDDING_MODEL")
            or os.environ.get("OLLAMA_EMBEDDING_MODEL")
            or _DEFAULT_MODEL
        )
        self._base_url = (
            base_url or os.environ.get("REPOLENS_OLLAMA_URL") or _DEFAULT_BASE_URL
        ).rstrip("/")

        env_dims = os.environ.get("REPOLENS_EMBEDDING_DIMS")
        self._requested_dimensions = dimensions or (int(env_dims) if env_dims else None)
        self._dimensions = self._requested_dimensions or _infer_dimensions(self._model)

        env_timeout = os.environ.get("REPOLENS_EMBEDDING_TIMEOUT")
        self._timeout = (
            timeout
            if timeout is not None
            else (float(env_timeout) if env_timeout else _DEFAULT_TIMEOUT)
        )

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts using Ollama's native API."""
        if not texts:
            return []

        payload: dict[str, Any] = {
            "model": self._model,
            "input": texts,
        }
        if self._requested_dimensions is not None:
            payload["dimensions"] = self._requested_dimensions

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/api/embed", json=payload
            )
            response.raise_for_status()
            data = response.json()

        raw_vectors = data.get("embeddings")
        if raw_vectors is None and "embedding" in data:
            raw_vectors = [data["embedding"]]
        if not isinstance(raw_vectors, list):
            raise ValueError("Ollama embedding response did not include embeddings.")
        if len(raw_vectors) != len(texts):
            raise ValueError(
                f"Ollama returned {len(raw_vectors)} embeddings for {len(texts)} inputs."
            )

        return [_l2_normalize([float(v) for v in vec]) for vec in raw_vectors]

    async def is_available(self) -> bool:
        """Check if Ollama server is reachable and model is available."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                if response.status_code == 200:
                    models = response.json().get("models", [])
                    available = [m.get("name", "").split(":")[0] for m in models]
                    return self._model.split(":")[0] in available
        except Exception:
            pass
        return False
