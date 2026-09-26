"""BM25 retriever (in-memory) for hybrid search.

分词统一委托给 :mod:`app.services.retrieval.tokenizer`：中文按字符 bi-gram
切分（``门诊时间`` → 门诊/诊时/时间），解决了原先
``str.lower().split()`` 把整段中文当成一个 term、关键词检索形同虚设的问题
（审计 §2.3）。

本类保持 **纯内存** 语义（``fit`` + ``search``），适合小语料与单元测试；
生产检索走持久化倒排索引 :class:`~app.services.retrieval.sparse_index.SparseIndex`。
"""

import math
from collections import Counter
from typing import List

from .tokenizer import tokenize


class BM25Retriever:
    """Simple BM25 implementation for text retrieval."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._documents: List[str] = []
        self._doc_tokens: List[List[str]] = []
        self._doc_lengths: List[int] = []
        self._doc_freq: Counter = Counter()
        self._avg_doc_len: float = 0.0
        self._total_docs: int = 0

    def fit(self, documents: List[str]):
        """Index *documents*（重复调用会整体重建索引）。"""
        self._documents = list(documents)
        self._total_docs = len(self._documents)
        self._doc_tokens = [tokenize(doc) for doc in self._documents]
        self._doc_lengths = [len(tokens) for tokens in self._doc_tokens]

        total_len = sum(self._doc_lengths)
        doc_freq = Counter()
        for tokens in self._doc_tokens:
            doc_freq.update(set(tokens))

        self._doc_freq = doc_freq
        self._avg_doc_len = total_len / max(self._total_docs, 1)

    async def search(self, query: str, top_k: int = 5) -> List[tuple]:
        """Return ``[(doc_index, score, document), …]`` sorted by score desc."""
        query_words = tokenize(query)
        scores = []

        for i, tokens in enumerate(self._doc_tokens):
            score = self._compute_score(
                query_words, tokens, self._doc_lengths[i]
            )
            scores.append((i, score, self._documents[i]))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def _compute_score(
        self, query_words: List[str], doc_tokens: List[str], doc_len: int
    ) -> float:
        doc_counter = Counter(doc_tokens)
        score = 0.0
        N = self._total_docs
        avg_len = self._avg_doc_len or 1.0

        for word in query_words:
            if word not in doc_counter:
                continue
            tf = doc_counter[word]
            df = self._doc_freq.get(word, 1)
            idf = math.log(1 + (N - df + 0.5) / (df + 0.5))
            norm_len = doc_len / avg_len
            tf_norm = tf * (self.k1 + 1) / (
                tf + self.k1 * (1 - self.b + self.b * norm_len)
            )
            score += idf * tf_norm

        return score
