"""ParserFactory — creates the appropriate parser for a given file extension."""

import os

from loguru import logger

from .base import DocumentParser
from .text_parser import TextParser
from .markdown_parser import MarkdownParser
from .docx_parser import DocxParser
from .doc_parser import DocParser
from .pdf_parser import PdfParser
from .xlsx_parser import XlsxParser
from .csv_parser import CsvParser


class ParserFactory:
    """Factory for creating document parsers by file extension."""

    _parsers: dict[str, type[DocumentParser]] = {
        ".txt": TextParser,
        ".md": MarkdownParser,
        ".docx": DocxParser,
        ".doc": DocParser,
        ".pdf": PdfParser,
        ".xlsx": XlsxParser,
        ".csv": CsvParser,
    }

    @classmethod
    def get_parser(cls, file_path: str) -> DocumentParser:
        """Get the appropriate parser for a file.

        Args:
            file_path: Path to the document file.

        Returns:
            A :class:`DocumentParser` instance.

        Raises:
            ValueError: If the file extension is not supported.
        """
        ext = os.path.splitext(file_path)[1].lower()
        parser_cls = cls._parsers.get(ext)
        if parser_cls is None:
            raise ValueError(f"Unsupported file type: {ext}")
        logger.debug(f"ParserFactory: selecting {parser_cls.__name__} for {ext}")
        return parser_cls()