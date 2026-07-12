"""Knowledge Pipeline Context — unified parameter container for document ingestion.

Replaces the growing list of individual ``process_document()`` parameters
with a single, extensible dataclass.  Future fields (user_id, tenant_id,
trace_id, metadata, etc.) are added here without changing method signatures.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class KnowledgePipelineContext:
    """Input context for :meth:`KnowledgePipeline.process_document`.

    Every field is required — the caller must provide all values upfront.

    Attributes:
        file_path: Absolute path to the uploaded file on disk.
        document_id: The document's unique identifier (UUID string).
        filename: Original upload filename (stored as metadata).
        knowledge_base_id: Target knowledge base (isolation boundary).
    """

    file_path: str
    document_id: str
    filename: str
    knowledge_base_id: int