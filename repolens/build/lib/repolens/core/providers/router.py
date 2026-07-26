"""Embedding provider router for RepoLens.

Automatically detects available local embedding services (Ollama) and
falls back to cloud providers (OpenAI, Gemini) when local is unavailable.
Includes dimension safety guard to prevent vector store corruption.
"""

from __future__ import annotations

import structlog

from repolens.core.providers.base import Embedder, MockEmbedder
from repolens.core.providers.ollama import OllamaEmbedder
from repolens.core.providers.openai import OpenAIEmbedder

logger = structlog.get_logger(__name__)

# Provider registry mapping names to classes
_PROVIDERS: dict[str, type] = {
    "ollama": OllamaEmbedder,
    "openai": OpenAIEmbedder,
    "mock": MockEmbedder,
}


class DimensionMismatchError(Exception):
    """Raised when a provider returns vectors with unexpected dimensions."""


class EmbeddingRouter:
    """Routes embedding requests through available providers with fallback.

    The router tries providers in priority order:
    1. Primary provider (configured, default: ollama)
    2. Fallback provider (configured, default: openai)
    3. Mock embedder (always available, for testing)

    Includes a dimension guard that rejects provider switches that would
    change embedding dimensions mid-index, preventing vector store corruption.

    Args:
        primary: Primary embedding provider instance.
        fallback: Fallback embedding provider instance (optional).
        expected_dimensions: Expected vector dimensions. If set, rejects
            providers that produce different dimensions.
    """

    def __init__(
        self,
        primary: Embedder,
        fallback: Embedder | None = None,
        expected_dimensions: int | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._expected_dimensions = expected_dimensions or primary.dimensions
        self._active_provider: Embedder | None = None

    @property
    def dimensions(self) -> int:
        return self._expected_dimensions

    @property
    def active_provider_name(self) -> str:
        """Name of the currently active provider."""
        if self._active_provider is None:
            return "none"
        return type(self._active_provider).__name__

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts using available providers with automatic fallback.

        Tries the primary provider first, falls back to secondary if
        primary fails. Validates dimension consistency.
        """
        if not texts:
            return []

        # Try primary provider
        try:
            vectors = await self._primary.embed(texts)
            self._validate_dimensions(vectors, self._primary)
            self._active_provider = self._primary
            return vectors
        except Exception as e:
            logger.warning(
                "primary_embedding_failed",
                provider=type(self._primary).__name__,
                error=str(e),
            )

        # Try fallback provider
        if self._fallback is not None:
            try:
                self._check_dimension_guard(self._fallback)
                vectors = await self._fallback.embed(texts)
                self._validate_dimensions(vectors, self._fallback)
                self._active_provider = self._fallback
                logger.info(
                    "using_fallback_embedding",
                    provider=type(self._fallback).__name__,
                )
                return vectors
            except DimensionMismatchError:
                raise
            except Exception as e:
                logger.warning(
                    "fallback_embedding_failed",
                    provider=type(self._fallback).__name__,
                    error=str(e),
                )

        raise RuntimeError(
            "All embedding providers failed. Ensure Ollama is running locally "
            "or configure an API key for a cloud provider."
        )

    def _check_dimension_guard(self, provider: Embedder) -> None:
        """Reject providers whose dimensions differ from expected."""
        if (
            self._expected_dimensions
            and hasattr(provider, "dimensions")
            and provider.dimensions != self._expected_dimensions
        ):
            raise DimensionMismatchError(
                f"Provider {type(provider).__name__} produces {provider.dimensions}D "
                f"vectors but index expects {self._expected_dimensions}D. "
                f"Switching providers mid-index would corrupt the vector store."
            )

    def _validate_dimensions(
        self, vectors: list[list[float]], provider: Embedder
    ) -> None:
        """Validate that returned vectors match expected dimensions."""
        if vectors and len(vectors[0]) != self._expected_dimensions:
            raise DimensionMismatchError(
                f"Provider {type(provider).__name__} returned {len(vectors[0])}D "
                f"vectors but expected {self._expected_dimensions}D."
            )


async def create_embedder(
    provider: str = "ollama",
    fallback_provider: str | None = "openai",
    model: str | None = None,
    dimensions: int | None = None,
    **kwargs,
) -> EmbeddingRouter:
    """Factory function to create an EmbeddingRouter with configured providers.

    Args:
        provider: Primary provider name ('ollama', 'openai', 'mock').
        fallback_provider: Fallback provider name (optional).
        model: Model name override for the primary provider.
        dimensions: Expected embedding dimensions.

    Returns:
        Configured EmbeddingRouter instance.
    """
    primary_cls = _PROVIDERS.get(provider)
    if primary_cls is None:
        raise ValueError(f"Unknown embedding provider: {provider}. Available: {list(_PROVIDERS)}")

    primary_kwargs = {}
    if model:
        primary_kwargs["model"] = model
    if dimensions:
        primary_kwargs["dimensions"] = dimensions

    primary = primary_cls(**primary_kwargs) if primary_kwargs else primary_cls()

    fallback = None
    if fallback_provider and fallback_provider in _PROVIDERS:
        fallback_cls = _PROVIDERS[fallback_provider]
        fallback = fallback_cls()

    # Auto-detect: if primary is Ollama, check availability and swap if needed
    if provider == "ollama" and isinstance(primary, OllamaEmbedder):
        if not await primary.is_available():
            logger.warning(
                "ollama_not_available",
                msg="Ollama not running locally, will use fallback on first embed call",
            )

    return EmbeddingRouter(
        primary=primary,
        fallback=fallback,
        expected_dimensions=dimensions,
    )
