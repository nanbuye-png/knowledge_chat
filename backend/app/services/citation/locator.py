"""Citation locator — 从 chunk 文本中定位 page / section（Phase 1 §5.5）。

为什么需要它
------------
引用要能追溯到 ``page`` / ``section``，但解析器目前只把页号写进了正文
（PDF 解析器输出 ``"[第N页]"``），切分后 page 信息不在 chunk metadata 里。
这里提供**启发式**定位：不改动切分算法，直接从 chunk 文本中识别标记。

* ``page``：识别 ``[第N页]`` 标记；没有标记时由调用方沿用上一个 chunk 的页码
  （文档顺序遍历，见 :func:`resolve_pages`）。
* ``section``：识别 Markdown 标题（``# ...``）与中文「第X章/节/部分」行。

定位是启发式的，因此结果允许为 ``None``；引用展示会优雅降级。
"""

from __future__ import annotations

import re
from typing import Optional

#: PDF 解析器写入正文的页号标记
_PAGE_PATTERN = re.compile(r"\[第\s*(\d+)\s*页\]")

#: Markdown 标题
_MARKDOWN_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(?P<title>.+?)\s*$", re.MULTILINE)

#: 中文「第X章 / 第X节 / 第X部分」
_CN_HEADING = re.compile(
    r"^\s*(?P<title>第[〇零一二三四五六七八九十百千0-9]+[章节篇部]\s*[^\n]{0,40})\s*$",
    re.MULTILINE,
)

#: 展示用标题长度上限
MAX_SECTION_LENGTH = 60


def extract_page(text: str) -> Optional[int]:
    """Return the first ``[第N页]`` marker found in *text*, else ``None``."""
    match = _PAGE_PATTERN.search(text or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:  # pragma: no cover - 正则已保证是数字
        return None


def extract_section(text: str) -> Optional[str]:
    """Return the nearest heading found in *text*, else ``None``.

    优先级：Markdown 标题 → 中文「第X章/节/部分」。
    """
    if not text:
        return None

    match = _MARKDOWN_HEADING.search(text) or _CN_HEADING.search(text)
    if not match:
        return None

    title = match.group("title").strip().strip("#").strip()
    if not title:
        return None
    return title[:MAX_SECTION_LENGTH]


def resolve_pages(chunks: list[str]) -> list[Optional[int]]:
    """Resolve ``page`` for every chunk, inheriting the last seen page.

    文档按顺序切分，因此"本 chunk 没有页号标记"通常意味着它延续了
    上一页的内容 —— 沿用上一个页码比返回 ``None`` 更贴近事实。
    """
    pages: list[Optional[int]] = []
    last_page: Optional[int] = None
    for chunk in chunks:
        page = extract_page(chunk)
        if page is None:
            page = last_page
        else:
            last_page = page
        pages.append(page)
    return pages


def resolve_sections(chunks: list[str]) -> list[Optional[str]]:
    """Resolve ``section`` for every chunk, inheriting the last seen heading."""
    sections: list[Optional[str]] = []
    last_section: Optional[str] = None
    for chunk in chunks:
        section = extract_section(chunk)
        if section is None:
            section = last_section
        else:
            last_section = section
        sections.append(section)
    return sections
