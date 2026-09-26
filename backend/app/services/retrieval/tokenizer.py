"""Tokenizer — 零依赖的中文/英文混合分词（Phase 1 §5.2）。

为什么需要它
------------
原 ``bm25.py`` 用 ``str.lower().split()`` 分词，**对中文等于不分词**
（整段中文会变成一个 term），关键词检索形同虚设（审计 §2.3）。

策略（零新增依赖）
------------------
* 中日韩汉字（CJK）连续段 → **字符 bi-gram**（``门诊时间`` → 门诊/诊时/时间）；
  单字段退化为单字本身。
* 拉丁字母 / 数字 / 下划线连续段 → 整词（小写）。
* 其余字符（标点、空白、emoji）为分隔符，直接丢弃。

> bi-gram 的取舍：不需要 jieba 等新依赖、对未登录词稳健，代价是索引膨胀
> （词项数约为中文字符数的 2 倍）。需要更好切分时可在同一接口下替换实现。
"""

from __future__ import annotations

import re

#: 连续拉丁/数字词 或 连续 CJK 汉字
_TOKEN_PATTERN = re.compile(r"[0-9a-zA-Z_]+|[\u3400-\u4dbf\u4e00-\u9fff]+")


def _cjk_grams(run: str) -> list[str]:
    """把连续汉字段切成 bi-gram（单字段原样返回）。"""
    if len(run) == 1:
        return [run]
    return [run[i : i + 2] for i in range(len(run) - 1)]


def tokenize(text: str) -> list[str]:
    """Tokenize *text* for sparse retrieval.

    Args:
        text: 任意文本（可中英混排）。

    Returns:
        词项列表（**保留重复**，重复次数即词频 tf）。
    """
    if not text:
        return []

    tokens: list[str] = []
    for match in _TOKEN_PATTERN.finditer(text.lower()):
        piece = match.group(0)
        if piece[0].isascii():
            tokens.append(piece)
        else:
            tokens.extend(_cjk_grams(piece))
    return tokens
