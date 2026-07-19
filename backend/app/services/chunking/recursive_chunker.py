"""Recursive Chunker — paragraph‑aware chunking with overlap.

Migrated from :mod:`app.utils.text_chunker`.  Algorithm is unchanged.
"""

import re

from loguru import logger

from .base import BaseChunker

# ── Time / Date / Number pattern placeholders ─────────────────────
# Protect these patterns from regex/normalize corruption:
#   08:00-12:00   (time range with hyphen)
#   08 : 00       (time with spaces)
#   08:00         (time)
#   08：00        (full-width colon)
#   8点到12点     (Chinese time range)
#   2026-01-01    (date)
#   100元         (currency)
#   50%           (percentage)
#   :–:           (en-dash time representations)
_TIME_PATTERN = re.compile(
    r"\d{1,2}\s*[:：]\s*\d{2}(?:\s*[-–—]\s*\d{1,2}\s*[:：]\s*\d{2})?"  # 08:00 or 08:00-12:00, with optional spaces
    r"|\d{1,2}点\s*到\s*\d{1,2}点"                                     # 8点到12点 (Chinese time range)
    r"|\d{4}[-/]\d{1,2}[-/]\d{1,2}"                                     # 2026-01-01
    r"|\d+(?:\.\d+)?[元$€£¥]"                                           # 100元 99.9元
    r"|\d+(?:\.\d+)?%"                                                  # 50% 99.9%
    r"|:\s*[–—-]\s*:"                                                    # :–: time placeholder
)


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
    # Internal
    # ------------------------------------------------------------------

    def _chunk_text(self, text: str) -> list[str]:
        if not text or not text.strip():
            return []

        # ── Step 1: Protect time/date/number patterns with placeholders ──
        placeholders: dict[str, str] = {}

        def _protect(m: re.Match) -> str:
            ph = f"__TKN_{len(placeholders)}__"
            placeholders[ph] = m.group(0)
            return ph

        text = _TIME_PATTERN.sub(_protect, text)

        # ── Step 2: Normalize whitespace ────────────────────────────────
        # Only collapse spaces/tabs, preserve \n for paragraph split
        text = re.sub(r"[ \t]+", " ", text).strip()

        chunks = self._do_chunk(text)

        # ── Step 3: Restore placeholders ────────────────────────────────
        restored = []
        for c in chunks:
            for ph, original in placeholders.items():
                c = c.replace(ph, original)
            restored.append(c)

        # Debug logging
        logger.info(
            f"Text chunked into {len(restored)} chunks "
            f"(chunk_size={self._chunk_size}, overlap={self._chunk_overlap}, "
            f"{len(placeholders)} patterns protected)"
        )
        for i, chunk in enumerate(restored):
            logger.debug(f"  Chunk {i + 1}: {chunk[:100]}")

        return restored

    @staticmethod
    def _find_split_point(text: str, target_size: int) -> int:
        """Find a good split point near *target_size*.

        Prefers sentence boundaries (。！？.!?), then paragraph breaks.

        WARNING: Do NOT include ": " (colon-space) as a split boundary —
        it would destroy time formats like "08:00-12:00".
        """
        if len(text) <= target_size:
            return len(text)

        search_start = max(target_size - 100, 0)
        search_end = min(target_size + 100, len(text))
        search_region = text[search_start:search_end]

        # Priority 1: Sentence-ending punctuation
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

    # ── Chunking logic (extracted for placeholder compatibility) ───

    def _do_chunk(self, text: str) -> list[str]:
        """Core chunking algorithm. Operates on placeholder-protected text."""
        chunks: list[str] = []
        current_chunk = ""

        # Split by double newlines first (paragraphs)
        paragraphs = re.split(r"\n\s*\n", text)

        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue

            if (
                len(current_chunk) + len(paragraph) + 1 > self._chunk_size
                and current_chunk
            ):
                split_at = self._find_split_point(current_chunk, self._chunk_size)
                if split_at > 0:
                    chunks.append(current_chunk[:split_at].strip())
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

        # Final chunk
        if current_chunk.strip():
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

        return [c for c in chunks if c and len(c) > 10]