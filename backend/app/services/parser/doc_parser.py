"""Legacy .doc (Word 97-2003) parser — pure Python via olefile.

``python-docx`` only understands ``.docx`` (Office Open XML, a ZIP container).
Legacy ``.doc`` files are OLE2 Compound Files (``D0 CF 11 E0 ...`` magic), so
feeding one to ``python-docx`` raises ``Package not found at '<path>'``.

This parser reads the ``WordDocument`` stream directly with ``olefile`` and
extracts the body text using the FIB (File Information Block) offsets:

- ``fcMin``  (FIB offset 0x18) — byte offset of the first body character
- ``fcMac``  (FIB offset 0x1C) — byte offset just past the last body character

Encoding is selected from the FIB ``flags`` field (offset 0x0A):

- ``fExtChar`` (bit 12, 0x1000) set → text is UTF-16LE (Unicode)
- otherwise → single-byte codepage (GB18030 for Simplified Chinese)

If precise extraction yields nothing usable, a heuristic fallback decodes the
whole stream and keeps printable CJK/ASCII runs.
"""

import re
import struct

from loguru import logger

from .base import DocumentParser


class DocParser(DocumentParser):
    """Parse legacy binary ``.doc`` files (Word 97-2003)."""

    # FIB flags (offset 0x0A) bit mask
    _FEXTCHAR = 0x1000  # bit 12 — extended (Unicode) characters present

    def parse(self, file_path: str) -> dict:
        try:
            import olefile
        except ImportError:
            raise ImportError(
                "olefile is required to parse legacy .doc files. "
                "Install with: pip install olefile"
            )

        content = self._extract(olefile, file_path)

        digit_count = sum(c.isdigit() for c in content)
        metadata = {
            "type": "doc",
            "pages": 0,
            "tables": 0,
        }

        logger.debug("Document Parser Debug:")
        logger.debug(f"  filename: {file_path}")
        logger.debug(f"  type: doc")
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

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def _extract(self, olefile_module, file_path: str) -> str:
        """Extract body text from an OLE2 Word document."""
        ole = olefile_module.OleFileIO(file_path)
        try:
            if not ole.exists("WordDocument"):
                raise ValueError("不是有效的 Word 文档（缺少 WordDocument 流）")
            word_stream = ole.openstream("WordDocument").read()
        finally:
            ole.close()

        return self._extract_body(word_stream)

    def _extract_body(self, word_stream: bytes) -> str:
        """Extract body text from a raw ``WordDocument`` stream."""
        if len(word_stream) < 0x20:
            raise ValueError("Word 文档 FIB 头损坏，无法解析")

        w_ident = struct.unpack_from("<H", word_stream, 0)[0]
        if w_ident != 0xA5EC:
            raise ValueError(
                "不是有效的 Word .doc 文件（无效的文件标识，请尝试另存为 .docx）"
            )

        flags = struct.unpack_from("<H", word_stream, 0x0A)[0]
        fc_min = struct.unpack_from("<I", word_stream, 0x18)[0]
        fc_mac = struct.unpack_from("<I", word_stream, 0x1C)[0]
        is_unicode = bool(flags & self._FEXTCHAR)

        # ── Primary path: precise body range from FIB ──────────────────
        if fc_min < fc_mac <= len(word_stream):
            raw = word_stream[fc_min:fc_mac]
            if is_unicode:
                text = raw.decode("utf-16-le", errors="replace")
            else:
                text = self._decode_single_byte(raw)
            text = self._clean_text(text)
            if text.strip():
                return text

        # ── Fallback path: whole-stream heuristic ──────────────────────
        logger.warning(
            "Precise FIB extraction produced no text; falling back to heuristic"
        )
        return self._extract_heuristic(word_stream, is_unicode)

    def _extract_heuristic(self, word_stream: bytes, is_unicode: bool) -> str:
        """Decode the entire stream and keep printable CJK/ASCII runs."""
        if is_unicode:
            text = word_stream.decode("utf-16-le", errors="replace")
        else:
            text = self._decode_single_byte(word_stream)

        runs = re.findall(
            r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef"
            r"A-Za-z0-9\u0020-\u007e\u00a0-\u00ff]{2,}",
            text,
        )
        parts = [run for run in runs if self._looks_like_text(run)]
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _looks_like_text(run: str) -> bool:
        """Keep runs that contain CJK or mostly printable ASCII."""
        run = run.strip()
        if len(run) < 2:
            return False
        if re.search(r"[\u4e00-\u9fff]", run):
            return True
        printable = sum(1 for ch in run if ch.isprintable() or ch in " \t")
        return printable / max(len(run), 1) > 0.8

    @staticmethod
    def _decode_single_byte(raw: bytes) -> str:
        """Decode single-byte Word text, preferring CJK codepages.

        Simplified-Chinese ``.doc`` files store text as GBK/GB2312.  Western
        documents use CP1252.  Choose the encoding that yields the most CJK
        characters, tie-breaking on the number of printable characters.  This
        avoids ``latin-1`` winning simply because it maps every byte 1:1.
        """
        candidates = ("gb18030", "gbk", "cp1252", "latin-1")
        best_text = ""
        best_cjk = -1
        best_printable = -1
        for enc in candidates:
            try:
                decoded = raw.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
            cjk = sum(1 for ch in decoded if "\u4e00" <= ch <= "\u9fff")
            printable = sum(1 for ch in decoded if ch.isprintable() or ch in " \t\n")
            if cjk > best_cjk or (cjk == best_cjk and printable > best_printable):
                best_cjk = cjk
                best_printable = printable
                best_text = decoded
        return best_text

    @staticmethod
    def _clean_text(text: str) -> str:
        """Normalise Word control characters to plain text."""
        text = text.replace("\r", "\n")       # paragraph mark
        text = text.replace("\x0b", "\n")     # line break
        text = text.replace("\x0c", "\n")     # page break
        text = text.replace("\x07", " | ")    # table cell separator
        text = text.replace("\x13", "")       # field character
        text = text.replace("\x14", "")       # field begin
        text = text.replace("\x15", "")       # field end
        text = text.replace("\x00", "")       # stray nulls
        return text
