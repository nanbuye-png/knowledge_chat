"""DOCX parser — extracts paragraphs and tables with full content preservation."""

from loguru import logger

from .base import DocumentParser


class DocxParser(DocumentParser):
    """Parse .docx files including tables.

    Features:
        - Extract all paragraph text.
        - Extract table content row by row, cells joined with `` | ``.
        - Preserve numbers, times, dates.
        - No whitespace collapsing.
    """

    def parse(self, file_path: str) -> dict:
        try:
            from docx import Document
        except ImportError:
            raise ImportError(
                "python-docx is required. Install with: pip install python-docx"
            )

        doc = Document(file_path)
        text_parts: list[str] = []
        table_count = 0
        paragraph_count = 0

        # Helper to check if text has meaningful content
        def _has_content(t: str) -> bool:
            return bool(t and t.strip())

        # Extract paragraphs
        for para in doc.paragraphs:
            t = para.text
            if _has_content(t):
                text_parts.append(t.strip())
                paragraph_count += 1

        # Extract tables — preserve row structure
        for table in doc.tables:
            table_count += 1
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                row_text = " | ".join(cells)
                if _has_content(row_text):
                    text_parts.append(row_text)

        content = "\n\n".join(text_parts)
        digit_count = sum(c.isdigit() for c in content)

        metadata = {
            "type": "docx",
            "pages": 0,
            "tables": table_count,
        }

        logger.debug(f"Document Parser Debug:")
        logger.debug(f"  filename: {file_path}")
        logger.debug(f"  type: docx")
        logger.debug(f"  paragraph_count: {paragraph_count}")
        logger.debug(f"  table_count: {table_count}")
        logger.debug(f"  text_length: {len(content)}")
        logger.debug(f"  digit_count: {digit_count}")
        logger.debug(f"  preview: {repr(content[:200])}")

        return {
            "filename": file_path.split("\\")[-1].split("/")[-1],
            "content": content,
            "metadata": metadata,
        }