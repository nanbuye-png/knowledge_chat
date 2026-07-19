"""PDF parser — page-level text extraction with PyMuPDF (fitz).

Preserves:
    - Page structure
    - Numbers, times, dates
    - Newlines
    - Table layout (as close as possible)
"""

from loguru import logger

from .base import DocumentParser


class PdfParser(DocumentParser):
    """Parse PDF files using PyMuPDF (fitz).

    Each page is extracted with ``page.get_text()`` which preserves
    natural reading order including tables.

    Retains digit characters, newlines, and whitespace.
    No regex-based whitespace collapsing is applied.
    """

    def parse(self, file_path: str) -> dict:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError(
                "PyMuPDF is required. Install with: pip install PyMuPDF"
            )

        doc = fitz.open(file_path)
        page_texts: list[str] = []
        total_chars = 0
        total_digits = 0
        page_count = len(doc)

        for page_num, page in enumerate(doc):
            text = page.get_text()
            if text.strip():
                page_texts.append(f"[第{page_num + 1}页]\n{text.rstrip()}")
                total_chars += len(text)
                total_digits += sum(c.isdigit() for c in text)

        doc.close()

        content = "\n\n".join(page_texts)

        metadata = {
            "type": "pdf",
            "pages": page_count,
            "tables": 0,  # PyMuPDF doesn't extract table metadata directly
        }

        logger.debug(f"Document Parser Debug:")
        logger.debug(f"  filename: {file_path}")
        logger.debug(f"  type: pdf")
        logger.debug(f"  PDF pages: {page_count}")
        if page_count > 0:
            first_page_text = doc[0].get_text() if hasattr(doc, '__getitem__') and page_count > 0 else page_texts[0] if page_texts else ""
            logger.debug(f"  page1 chars: {len(first_page_text)}")
            logger.debug(f"  page1 preview: {repr(first_page_text[:200])}")
        logger.debug(f"  paragraph_count: {content.count(chr(10)) + 1}")
        logger.debug(f"  table_count: 0")
        logger.debug(f"  text_length: {total_chars}")
        logger.debug(f"  digit_count: {total_digits}")
        logger.debug(f"  preview: {repr(content[:200])}")

        return {
            "filename": file_path.split("\\")[-1].split("/")[-1],
            "content": content,
            "metadata": metadata,
        }