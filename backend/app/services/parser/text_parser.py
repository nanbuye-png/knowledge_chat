"""Plain text (.txt) parser — preserves whitespace, numbers, times, dates."""

from loguru import logger

from .base import DocumentParser


class TextParser(DocumentParser):
    """Parse .txt files with full content preservation.

    Rules:
        - Preserve newlines exactly as in source.
        - Preserve all whitespace (no collapsing).
        - Preserve numbers, times (08:00-12:00), dates (2026-07-19).
        - Preserve currency (100元) and percentages (50%).
        - No regex-based whitespace normalization.
    """

    def parse(self, file_path: str) -> dict:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        # Count digits for debug output
        digit_count = sum(c.isdigit() for c in content)

        metadata = {
            "type": "txt",
            "pages": 0,
            "tables": 0,
        }

        logger.debug(f"Document Parser Debug:")
        logger.debug(f"  filename: {file_path}")
        logger.debug(f"  type: txt")
        logger.debug(f"  paragraph_count: {content.count(chr(10)) + 1}")
        logger.debug(f"  table_count: 0")
        logger.debug(f"  text_length: {len(content)}")
        logger.debug(f"  digit_count: {digit_count}")
        logger.debug(f"  preview: {repr(content[:200])}")

        return {
            "filename": file_path.split("\\")[-1].split("/")[-1],
            "content": content,
            "metadata": metadata,
        }