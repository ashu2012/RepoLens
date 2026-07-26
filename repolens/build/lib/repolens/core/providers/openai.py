"""OpenAI embedding provider for RepoLens.

Uses the OpenAI API for text-embedding-3-small (or configurable model).
Used as a cloud fallback when local Ollama is unavailable.
"""

from __future__ import annotations

import math
import os
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_MODEL = "text-embedding-3-small"
_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_TIMEOUT = 30.0

_MODEL_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


def _l2_normalize(vec: list[float]) -> list[float]:
    """L2-normalize a vector to unit length."""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        norm = 1.0
    return [x / norm for x in vec]


class OpenAIEmbedder:
    """OpenAI embedding adapter implementing the RepoLens Embedder protocol.

    Args:
        model: OpenAI embedding model name.
        api_key: OpenAI API key. Falls back to REPOLENS_OPENAI_API_KEY env var.
        base_url: API base URL (for OpenAI-compatible endpoints).
        dimensions: Optional output dimensions (supported by text-embedding-3-*).
        timeout: Per-request timeout in seconds.
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        dimensions: int | None = None,
        timeout: float | None = None,
    ) -> None:
        self._model = model or os.environ.get("REPOLENS_OPENAI_MODEL") or _DEFAULT_MODEL
        self._api_key = (
            api_key
            or os.environ.get("REPOLENS_OPENAI_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )
        self._base_url = (
            base_url or os.environ.get("REPOLENS_OPENAI_BASE_URL") or _DEFAULT_BASE_URL
        ).rstrip("/")
        self._requested_dimensions = dimensions
        self._dimensions = dimensions or _MODEL_DIMENSIONS.get(self._model, 1536)
        self._timeout = timeout or _DEFAULT_TIMEOUT

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts using OpenAI's API."""
        if not texts:
            return []
        if not self._api_key:
            raise ValueError("OpenAI API key not configured. Set REPOLENS_OPENAI_API_KEY.")

        payload: dict[str, Any] = {
            "model": self._model,
            "input": texts,
        }
        if self._requested_dimensions is not None:
            payload["dimensions"] = self._requested_dimensions

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/embeddings",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

        embeddings = data.get("data", [])
        if len(embeddings) != len(texts):
            raise ValueError(
                f"OpenAI returned {len(embeddings)} embeddings for {len(texts)} inputs."
            )

        sorted_embeddings = sorted(embeddings, key=lambda x: x["index"])
        return [_l2_normalize(e["embedding"]) for e in sorted_embeddings]

    async def is_available(self) -> bool:
        """Check if OpenAI API key is configured."""
        return bool(self._api_key)
