"""Embedder protocol and mock implementation for RepoLens.

The Embedder protocol is structural (runtime_checkable) so any object with
an ``embed()`` method and a ``dimensions`` property satisfies it without
inheriting from a base class.
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    """Structural protocol for text embedding models.

    All implementations must produce unit-length (L2-normalized) vectors so
    that cosine similarity equals the dot product.
    """

    @property
    def dimensions(self) -> int:
        """Number of dimensions in the embedding vector."""
        ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts.

        Args:
            texts: Non-empty list of strings to embed.

        Returns:
            List of unit-length float vectors, one per input string.
            Each vector has exactly ``self.dimensions`` elements.
        """
        ...


def _l2_normalize(vec: list[float]) -> list[float]:
    """L2-normalize a vector to unit length."""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        norm = 1.0
    return [x / norm for x in vec]


class MockEmbedder:
    """Deterministic 8-dimensional embedder for testing.

    Uses the first 8 bytes of SHA-256(text) interpreted as unsigned bytes,
    divided by 255.0, then L2-normalised to unit length.
    """

    dimensions: int = 8

    async def embed(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            raw = [digest[i] / 255.0 for i in range(8)]
            results.append(_l2_normalize(raw))
        return results
