"""Citation — reference tracking for RAG results.

Provides structured citation models and a builder that transforms raw
retrieval chunks into traceable source references.
"""

from .builder import CitationBuilder
from .models import Citation

__all__ = ["Citation", "CitationBuilder"]