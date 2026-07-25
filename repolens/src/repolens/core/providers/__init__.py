# RepoLens — Embedding Providers
"""Embedding provider protocol and implementations."""

from repolens.core.providers.base import Embedder, MockEmbedder
from repolens.core.providers.router import EmbeddingRouter, create_embedder

__all__ = ["Embedder", "MockEmbedder", "EmbeddingRouter", "create_embedder"]
