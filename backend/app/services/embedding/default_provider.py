"""Backward‑compatible re‑export shim.

The canonical ``DefaultEmbeddingProvider`` now lives under
``embedding.providers.default``.  This module is kept so existing
importers (e.g. ``embedding_service``) continue to work unchanged.
"""

from .providers.default import DefaultEmbeddingProvider  # noqa: F401

__all__ = ["DefaultEmbeddingProvider"]
