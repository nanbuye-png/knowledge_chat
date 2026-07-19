"""Document parser package — extracts text from uploaded files."""

from .factory import ParserFactory
from .base import DocumentParser

__all__ = ["DocumentParser", "ParserFactory"]