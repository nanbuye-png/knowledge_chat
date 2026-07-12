"""Recursive Chunker — paragraph‑aware chunking with overlap.

Migrated from :mod:`app.utils.text_chunker`.  Algorithm is unchanged.
"""

import re

from loguru import logger

from .base import BaseChunker


class RecursiveChunker(BaseChunker):
    """Split text into overlapping chunks at natural boundaries.

    Strategy:
        1. Split by paragraphs (double newlines).
        2. Merge small paragraphs into chunks.
        3. Break large chunks at sentence boundaries.
        4. Maintain overlap between consecutive chunks.
    """

    def __init__(self, chunk_size: int, chunk_overlap: int) -> None:
        """Initialize the chunker.

        Args:
            chunk_size: Target chunk size in characters.
            chunk_overlap: Number of overlapping characters between chunks.
        """
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    # ------------------------------------------------------------------
    # BaseChunker interface
    # ------------------------------------------------------------------

    def chunk(self, text: str) -> list[str]:
        """Split *text* into overlapping chunks.

        Args:
            text: Raw document text.

        Returns:
            A list of chunk strings (may be empty if input is empty).
        """
        return self._chunk_text(text)

    # ------------------------------------------------------------------
    # Internal (identical to original chunk_text + _find_split_point)
    # ------------------------------------------------------------------

    def _chunk_text(self, text: str) -> list[str]:
        if not text or not text.strip():
            return []

        # Clean text: normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()

        chunks: list[str] = []
        current_chunk = ""

        # Split by double newlines first (paragraphs)
        paragraphs = re.split(r"\n\s*\n", text)

        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue

            # If adding this paragraph exceeds chunk size, save current and start new
            if (
                len(current_chunk) + len(paragraph) + 1 > self._chunk_size
                and current_chunk
            ):
                # Try to break at sentence boundary
                split_at = self._find_split_point(current_chunk, self._chunk_size)
                if split_at > 0:
                    chunks.append(current_chunk[:split_at].strip())
                    # Keep overlap text for next chunk
                    overlap_start = max(0, split_at - self._chunk_overlap)
                    current_chunk = current_chunk[overlap_start:] + " " + paragraph
                else:
                    chunks.append(current_chunk.strip())
                    current_chunk = paragraph
            else:
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph

        # Add final chunk
        if current_chunk.strip():
            # If final chunk is too long, split it
            while len(current_chunk) > self._chunk_size:
                split_at = self._find_split_point(current_chunk, self._chunk_size)
                if split_at > 0:
                    chunks.append(current_chunk[:split_at].strip())
                    overlap_start = max(0, split_at - self._chunk_overlap)
                    current_chunk = current_chunk[overlap_start:]
                else:
                    chunks.append(current_chunk[: self._chunk_size].strip())
                    current_chunk = current_chunk[self._chunk_size :]

            if current_chunk.strip():
                chunks.append(current_chunk.strip())

        # Filter out any empty chunks
        chunks = [c for c in chunks if c and len(c) > 10]

        logger.info(
            f"Text chunked into {len(chunks)} chunks "
            f"(chunk_size={self._chunk_size}, overlap={self._chunk_overlap})"
        )
        return chunks

    @staticmethod
    def _find_split_point(text: str, target_size: int) -> int:
        """Find a good split point near *target_size*.

        Prefers sentence boundaries (。！？.!?), then paragraph breaks.
        """
        if len(text) <= target_size:
            return len(text)

        # Search for Chinese/English sentence boundaries near target_size
        search_start = max(target_size - 100, 0)
        search_end = min(target_size + 100, len(text))
        search_region = text[search_start:search_end]

        # Priority 1: Sentence-ending punctuation (Chinese and English)
        for sep in ["。", "！", "？", "\n", ". ", "! ", "? "]:
            pos = search_region.rfind(sep, 0, len(search_region))
            if pos > 0:
                return search_start + pos + len(sep)

        # Priority 2: Comma or other punctuation
        for sep in ["，", "；", ", ", "; "]:
            pos = search_region.rfind(sep, 0, len(search_region))
            if pos > 0:
                return search_start + pos + len(sep)

        # Priority 3: Just split at target_size
        return target_size