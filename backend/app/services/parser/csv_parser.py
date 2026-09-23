"""CSV parser — extracts rows using the standard-library ``csv`` module.

Cells within a row are joined with `` | `` to preserve table structure.
Encoding is detected by trying UTF-8 (with BOM) then GB18030, which covers
the common Simplified-Chinese CSV files exported from Excel/WPS.
"""

from loguru import logger

from .base import DocumentParser


class CsvParser(DocumentParser):
    """Parse .csv files, preserving row/column structure."""

    _ENCODINGS = ("utf-8-sig", "gb18030")

    def parse(self, file_path: str) -> dict:
        content = self._read(file_path)

        digit_count = sum(c.isdigit() for c in content)

        metadata = {
            "type": "csv",
            "pages": 0,
            "tables": 1,
        }

        logger.debug("Document Parser Debug:")
        logger.debug(f"  filename: {file_path}")
        logger.debug(f"  type: csv")
        logger.debug(f"  text_length: {len(content)}")
        logger.debug(f"  digit_count: {digit_count}")
        logger.debug(f"  preview: {repr(content[:200])}")

        return {
            "filename": file_path.split("\\")[-1].split("/")[-1],
            "content": content,
            "metadata": metadata,
        }

    def _read(self, file_path: str) -> str:
        import csv

        for encoding in self._ENCODINGS:
            try:
                with open(
                    file_path, "r", encoding=encoding, newline=""
                ) as f:
                    rows = list(csv.reader(f))
                return self._join_rows(rows)
            except (UnicodeDecodeError, UnicodeError):
                continue

        # Last resort — decode with replacement to avoid total failure.
        with open(
            file_path, "r", encoding="utf-8", errors="replace", newline=""
        ) as f:
            rows = list(csv.reader(f))
        return self._join_rows(rows)

    @staticmethod
    def _join_rows(rows) -> str:
        lines = [" | ".join(cell.strip() for cell in row) for row in rows]
        # Drop fully-empty lines.
        lines = [line for line in lines if line.replace(" | ", "").strip()]
        return "\n".join(lines)
