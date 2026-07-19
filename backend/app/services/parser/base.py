"""Base document parser interface."""

from abc import ABC, abstractmethod


class DocumentParser(ABC):
    """Abstract base for all document parsers."""

    @abstractmethod
    def parse(self, file_path: str) -> dict:
        """Parse a document file and return structured content.

        Returns:
            dict with keys:
                filename (str): Original filename.
                content (str): Extracted text content.
                metadata (dict): Parser-specific metadata (type, pages, tables, etc.).
        """
        ...