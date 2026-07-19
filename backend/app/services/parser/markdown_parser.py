"""Markdown (.md) parser — preserves structure, numbers, times, dates."""

from loguru import logger

from .base import DocumentParser


class MarkdownParser(DocumentParser):
    """Parse .md files with full content preservation.

    Reads raw content — no markdown-to-text conversion to avoid
    losing table syntax, code blocks, or inline formatting.
    """

    def parse(self, file_path: str) -> dict:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        digit_count = sum(c.isdigit() for c in content)

        metadata = {
            "type": "md",
            "pages": 0,
            "tables": 0,
        }

        logger.debug(f"Document Parser Debug:")
        logger.debug(f"  filename: {file_path}")
        logger.debug(f"  type: md")
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