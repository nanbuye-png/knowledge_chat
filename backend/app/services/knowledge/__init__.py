"""Knowledge Pipeline — unified document ingestion pipeline.

Orchestrates the end-to-end flow of document processing:
parse → chunk → embed → vector store.
"""

from .pipeline import KnowledgePipeline

__all__ = ["KnowledgePipeline"]