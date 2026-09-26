"""Citation — reference tracking for RAG results.

Provides structured citation models and a builder that transforms raw
retrieval chunks into traceable source references.
"""

from .builder import CitationBuilder
from .locator import extract_page, extract_section, resolve_pages, resolve_sections
from .models import Citation
from .validator import (
    CitationValidation,
    documents_exist,
    extract_reference_indices,
    filter_live_citations,
    validate_citations,
)

__all__ = [
    "Citation",
    "CitationBuilder",
    "CitationValidation",
    "extract_page",
    "extract_section",
    "extract_reference_indices",
    "resolve_pages",
    "resolve_sections",
    "documents_exist",
    "filter_live_citations",
    "validate_citations",
]