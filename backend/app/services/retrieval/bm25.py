"""BM25 retriever for hybrid search."""
from typing import List
import math
from collections import Counter


class BM25Retriever:
    """Simple BM25 implementation for text retrieval."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._documents: List[str] = []
        self._doc_freq: Counter = Counter()
        self._avg_doc_len: float = 0
        self._total_docs: int = 0

    def fit(self, documents: List[str]):
        self._documents = documents
        self._total_docs = len(documents)
        total_len = 0
        doc_freq = Counter()

        for doc in documents:
            words = doc.lower().split()
            total_len += len(words)
            doc_freq.update(set(words))

        self._doc_freq = doc_freq
        self._avg_doc_len = total_len / max(self._total_docs, 1)

    async def search(self, query: str, top_k: int = 5) -> List[tuple]:
        query_words = query.lower().split()
        scores = []

        for i, doc in enumerate(self._documents):
            score = self._compute_score(query_words, doc)
            scores.append((i, score, doc))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def _compute_score(self, query_words: List[str], document: str) -> float:
        doc_words = document.lower().split()
        doc_len = len(doc_words)
        doc_counter = Counter(doc_words)
        score = 0.0
        N = self._total_docs

        for word in query_words:
            if word not in doc_counter:
                continue
            tf = doc_counter[word]
            df = self._doc_freq.get(word, 1)
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1)
            tf_norm = tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * doc_len / self._avg_doc_len))
            score += idf * tf_norm

        return score