"""Hybrid Retrieval 测试（Phase 1 §5.2）。

覆盖计划要求：
1. 保留现有 Vector Retrieval（通道未被替换，可单独测试）
2. 新增 BM25 / Sparse Retrieval（中文可真正分词）
3. 两种 Retrieval 可独立测试
4. 融合权重可配置，默认合理
5. 不要过度设计（简单加权融合即可）
6. 稀疏通道失败必须可降级，不得拖垮问答
"""
import asyncio
import os
import sys

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend_dir)

from app.services.retrieval.bm25 import BM25Retriever  # noqa: E402
from app.services.retrieval.hybrid_retriever import (  # noqa: E402
    HybridRetriever,
    weighted_fusion,
)
from app.services.retrieval.sparse_index import SparseIndex  # noqa: E402
from app.services.retrieval.tokenizer import tokenize  # noqa: E402


def _index(tmp_path, name="sparse.db", **kwargs) -> SparseIndex:
    return SparseIndex(path=(tmp_path / name).as_posix(), **kwargs)


# ---------------------------------------------------------------------------
# 1: Tokenizer（中文必须真正分词）
# ---------------------------------------------------------------------------


class TestTokenizer:
    def test_chinese_bigrams(self):
        """回归：原先 str.split() 对中文等于不分词。"""
        tokens = tokenize("门诊时间")
        assert tokens == ["门诊", "诊时", "时间"], tokens
        assert "门诊时间" not in tokens, "整段中文不应成为单个 term"
        print(f"[PASS] 中文 bi-gram: {tokens}")

    def test_single_cjk_char(self):
        assert tokenize("医") == ["医"]

    def test_mixed_language(self):
        tokens = tokenize("BGE 模型 embedding 效果")
        assert "bge" in tokens
        assert "embedding" in tokens
        assert "模型" in tokens
        print(f"[PASS] 中英混排: {tokens}")

    def test_punctuation_and_empty(self):
        assert tokenize("") == []
        assert tokenize("，。！  ") == []
        assert tokenize("08:00-12:00") == ["08", "00", "12", "00"]


# ---------------------------------------------------------------------------
# 2: BM25（内存版，独立可测）
# ---------------------------------------------------------------------------


class TestBM25Retriever:
    def test_chinese_ranking(self):
        """中文关键词检索必须能命中（原实现做不到）。"""

        async def run():
            bm25 = BM25Retriever()
            bm25.fit(
                [
                    "门诊时间为上午八点到十二点",
                    "挂号需要携带身份证",
                    "住院部在另一栋楼",
                ]
            )
            return await bm25.search("门诊时间", top_k=3)

        results = asyncio.run(run())
        assert results, "中文查询必须能召回"
        assert "门诊时间" in results[0][2]
        print(f"[PASS] BM25 中文召回: {[(round(r[1], 3), r[2][:12]) for r in results]}")

    def test_contract_unchanged(self):
        """保持既有契约：[(index, score, document)]，空语料返回 []。"""

        async def run():
            bm25 = BM25Retriever()
            bm25.fit([])
            empty = await bm25.search("test", top_k=5)
            bm25.fit(["apple banana", "apple apple banana", "orange grape"])
            scored = await bm25.search("apple", top_k=3)
            return empty, scored

        empty, scored = asyncio.run(run())
        assert empty == []
        assert len(scored[0]) == 3
        assert scored[0][1] >= scored[1][1], "词频高的文档应排更前"
        print("[PASS] BM25 契约保持不变")


# ---------------------------------------------------------------------------
# 3: 持久化稀疏索引
# ---------------------------------------------------------------------------


class TestSparseIndex:
    def test_add_and_search(self, tmp_path):
        index = _index(tmp_path)

        async def run():
            await index.add_document_chunks(
                document_id="doc-1",
                filename="门诊指南.md",
                chunks=["门诊时间为上午八点到十二点", "下午两点到五点半"],
                knowledge_base_id=1,
                user_id=1,
            )
            return await index.search("门诊时间", knowledge_base_id=1, top_k=5)

        results = asyncio.run(run())
        assert results, "应命中关键词"
        assert results[0]["document_id"] == "doc-1"
        assert results[0]["id"] == "doc-1_0"
        assert results[0]["score"] > 0
        print(f"[PASS] 稀疏索引命中: {results[0]['filename']}#{results[0]['chunk_index']}")

    def test_knowledge_base_isolation(self, tmp_path):
        index = _index(tmp_path)

        async def run():
            await index.add_document_chunks("doc-a", "a.md", ["门诊时间上午"], 1, 1)
            await index.add_document_chunks("doc-b", "b.md", ["门诊时间下午"], 2, 1)
            kb1 = await index.search("门诊时间", knowledge_base_id=1, top_k=5)
            kb2 = await index.search("门诊时间", knowledge_base_id=2, top_k=5)
            return kb1, kb2

        kb1, kb2 = asyncio.run(run())
        assert [r["document_id"] for r in kb1] == ["doc-a"]
        assert [r["document_id"] for r in kb2] == ["doc-b"]
        print("[PASS] 知识库隔离正确")

    def test_reindex_is_idempotent(self, tmp_path):
        """重复入库同一文档不应产生重复计分。"""
        index = _index(tmp_path)

        async def run():
            await index.add_document_chunks("doc-1", "a.md", ["门诊时间门诊时间"], 1, 1)
            await index.add_document_chunks("doc-1", "a.md", ["门诊时间门诊时间"], 1, 1)
            count = await index.count()
            results = await index.search("门诊时间", knowledge_base_id=1, top_k=5)
            return count, results

        count, results = asyncio.run(run())
        assert count == 1, f"重复写入应覆盖而非追加，实际 {count}"
        assert len(results) == 1
        print("[PASS] 重复入库幂等")

    def test_delete_document_and_kb(self, tmp_path):
        index = _index(tmp_path)

        async def run():
            await index.add_document_chunks("doc-1", "a.md", ["门诊时间"], 1, 1)
            await index.add_document_chunks("doc-2", "b.md", ["门诊时间"], 1, 1)
            await index.add_document_chunks("doc-3", "c.md", ["门诊时间"], 2, 1)

            await index.delete_document("doc-1")
            after_doc = await index.search("门诊时间", knowledge_base_id=1, top_k=5)

            await index.delete_knowledge_base(1)
            after_kb = await index.search("门诊时间", knowledge_base_id=1, top_k=5)
            other_kb = await index.search("门诊时间", knowledge_base_id=2, top_k=5)
            return after_doc, after_kb, other_kb

        after_doc, after_kb, other_kb = asyncio.run(run())
        assert [r["document_id"] for r in after_doc] == ["doc-2"]
        assert after_kb == []
        assert [r["document_id"] for r in other_kb] == ["doc-3"], "不应影响其它 KB"
        print("[PASS] 删除文档 / 知识库后不再召回")

    def test_empty_query_and_empty_index(self, tmp_path):
        index = _index(tmp_path)

        async def run():
            empty_index = await index.search("门诊时间", knowledge_base_id=1, top_k=5)
            await index.add_document_chunks("doc-1", "a.md", ["门诊时间"], 1, 1)
            empty_query = await index.search("   ", knowledge_base_id=1, top_k=5)
            return empty_index, empty_query

        empty_index, empty_query = asyncio.run(run())
        assert empty_index == []
        assert empty_query == []
        print("[PASS] 空索引 / 空查询安全返回 []")


# ---------------------------------------------------------------------------
# 4: 融合（权重可配置、结果去重）
# ---------------------------------------------------------------------------


def _result(chunk_id: str, score: float, text: str = "") -> dict:
    return {
        "id": chunk_id,
        "document_id": chunk_id.split("_")[0],
        "filename": f"{chunk_id}.md",
        "chunk_index": 0,
        "text": text or f"内容 {chunk_id}",
        "score": score,
    }


class TestWeightedFusion:
    def test_merges_and_deduplicates(self):
        vector = [_result("a_0", 0.9), _result("b_0", 0.5), _result("d_0", 0.1)]
        sparse = [_result("b_0", 12.0), _result("c_0", 6.0)]

        fused = weighted_fusion(vector, sparse, 0.5, 0.5, top_k=10)

        assert len(fused) == 4, "同一 chunk 在两个通道命中应合并而非重复"
        by_id = {r["id"]: r for r in fused}
        assert by_id["b_0"]["vector_score"] > 0 and by_id["b_0"]["bm25_score"] > 0
        assert by_id["a_0"]["bm25_score"] == 0.0
        assert by_id["c_0"]["vector_score"] == 0.0
        # b_0 两个通道都命中 → 融合分最高
        assert fused[0]["id"] == "b_0"
        print(f"[PASS] 融合去重: {[r['id'] for r in fused]}")

    def test_weights_are_configurable(self):
        vector = [_result("a_0", 0.9)]
        sparse = [_result("b_0", 12.0)]

        vector_only = weighted_fusion(vector, sparse, 1.0, 0.0, top_k=5)
        sparse_only = weighted_fusion(vector, sparse, 0.0, 1.0, top_k=5)

        assert vector_only[0]["id"] == "a_0"
        assert sparse_only[0]["id"] == "b_0"
        print("[PASS] 权重可配置且影响排序")

    def test_top_k_truncation_and_scores(self):
        fused = weighted_fusion(
            [_result("a_0", 0.9), _result("b_0", 0.1)], [], 0.5, 0.5, top_k=1
        )
        assert len(fused) == 1
        assert fused[0]["score"] == 0.5, "单通道时归一化最高分为 1.0 × 权重"
        print("[PASS] top_k 截断与归一化分数正确")

    def test_empty_inputs(self):
        assert weighted_fusion([], [], 0.5, 0.5, top_k=5) == []
        assert len(weighted_fusion([_result("a_0", 1.0)], [], 0.5, 0.5, 5)) == 1


# ---------------------------------------------------------------------------
# 5: HybridRetriever（两条通道 + 降级）
# ---------------------------------------------------------------------------


class _StubVectorLeg:
    def __init__(self, results=None, error=None):
        self.results = results or []
        self.error = error
        self.calls: list[dict] = []

    async def retrieve(self, embedding, knowledge_base_id, top_k=5, query=None):
        self.calls.append(
            {
                "embedding": embedding,
                "knowledge_base_id": knowledge_base_id,
                "top_k": top_k,
                "query": query,
            }
        )
        if self.error is not None:
            raise self.error
        return list(self.results)


class _StubSparseIndex:
    def __init__(self, results=None, error=None):
        self.results = results or []
        self.error = error
        self.calls: list[dict] = []

    async def initialize(self):
        return None

    async def search(self, query, knowledge_base_id=None, top_k=5):
        self.calls.append({"query": query, "kb": knowledge_base_id, "top_k": top_k})
        if self.error is not None:
            raise self.error
        return list(self.results)


class TestHybridRetriever:
    def test_both_legs_merged(self):
        vector = _StubVectorLeg([_result("a_0", 0.8)])
        sparse = _StubSparseIndex([_result("b_0", 9.0)])
        retriever = HybridRetriever(vector, sparse, recall_k=7)

        results = asyncio.run(
            retriever.retrieve([0.1], knowledge_base_id=1, top_k=5, query="门诊时间")
        )

        assert {r["id"] for r in results} == {"a_0", "b_0"}
        assert vector.calls[0]["top_k"] == 7, "向量腿应取 recall_k"
        assert sparse.calls[0]["top_k"] == 7
        assert sparse.calls[0]["query"] == "门诊时间"
        print("[PASS] 两条通道均被调用并融合")

    def test_legs_are_independently_callable(self):
        vector = _StubVectorLeg([_result("a_0", 0.8)])
        sparse = _StubSparseIndex([_result("b_0", 9.0)])
        retriever = HybridRetriever(vector, sparse)

        async def run():
            return (
                await retriever.vector_leg([0.1], 1, 3),
                await retriever.sparse_leg("门诊", 1, 3),
            )

        vector_results, sparse_results = asyncio.run(run())
        assert vector_results[0]["id"] == "a_0"
        assert sparse_results[0]["id"] == "b_0"
        print("[PASS] 向量腿 / 稀疏腿可独立测试")

    def test_sparse_failure_degrades_to_vector(self):
        vector = _StubVectorLeg([_result("a_0", 0.8)])
        sparse = _StubSparseIndex(error=RuntimeError("index corrupted"))
        retriever = HybridRetriever(vector, sparse, sparse_fallback=True)

        results = asyncio.run(
            retriever.retrieve([0.1], knowledge_base_id=1, top_k=5, query="门诊时间")
        )

        assert [r["id"] for r in results] == ["a_0"], "稀疏失败时必须返回向量结果"
        print("[PASS] 稀疏通道失败 → 降级为纯向量检索")

    def test_sparse_failure_raises_when_fallback_disabled(self):
        vector = _StubVectorLeg([_result("a_0", 0.8)])
        sparse = _StubSparseIndex(error=RuntimeError("boom"))
        retriever = HybridRetriever(vector, sparse, sparse_fallback=False)

        try:
            asyncio.run(
                retriever.retrieve([0.1], knowledge_base_id=1, top_k=5, query="门诊")
            )
            raise AssertionError("关闭降级时应抛出异常")
        except AssertionError:
            raise
        except RuntimeError:
            print("[PASS] 关闭降级时显式失败")

    def test_without_query_uses_vector_only(self):
        vector = _StubVectorLeg([_result("a_0", 0.8)])
        sparse = _StubSparseIndex([_result("b_0", 9.0)])
        retriever = HybridRetriever(vector, sparse)

        results = asyncio.run(
            retriever.retrieve([0.1], knowledge_base_id=1, top_k=5, query=None)
        )

        assert [r["id"] for r in results] == ["a_0"]
        assert sparse.calls == [], "无查询文本时不应触碰稀疏索引"
        print("[PASS] 无 query 时只走向量通道")


# ---------------------------------------------------------------------------
# 6: 配置驱动（Baseline 可切换）
# ---------------------------------------------------------------------------


class TestRetrieverFactory:
    def test_vector_mode_for_baseline(self):
        from app.services.retrieval.factory import RetrieverFactory
        from app.services.retrieval.vector_retriever import VectorRetriever

        retriever = RetrieverFactory.create(mode="vector")
        assert isinstance(retriever, VectorRetriever)
        print("[PASS] RETRIEVAL_MODE=vector → 纯向量（Baseline）")

    def test_hybrid_mode_uses_configured_weights(self, monkeypatch):
        from app.services.retrieval import factory as factory_module
        from app.services.retrieval.factory import RetrieverFactory

        # 注意：直接 patch 工厂模块内实际读取的 settings 对象，
        # 避免其它测试 reload config 后出现"新旧 settings 对象"不一致。
        conf = factory_module.settings
        monkeypatch.setattr(conf, "RETRIEVAL_MODE", "hybrid")
        monkeypatch.setattr(conf, "HYBRID_VECTOR_WEIGHT", 0.7)
        monkeypatch.setattr(conf, "HYBRID_BM25_WEIGHT", 0.3)
        monkeypatch.setattr(conf, "HYBRID_RECALL_K", 20)

        retriever = RetrieverFactory.create()
        assert isinstance(retriever, HybridRetriever)
        assert retriever._vector_weight == 0.7
        assert retriever._bm25_weight == 0.3
        assert retriever._recall_k == 20
        print("[PASS] 默认混合检索且权重来自配置")

    def test_vector_mode_via_settings(self, monkeypatch):
        """RETRIEVAL_MODE=vector 时工厂应返回纯向量检索器（Baseline）。"""
        from app.services.retrieval import factory as factory_module
        from app.services.retrieval.factory import RetrieverFactory
        from app.services.retrieval.vector_retriever import VectorRetriever

        monkeypatch.setattr(factory_module.settings, "RETRIEVAL_MODE", "vector")
        retriever = RetrieverFactory.create()
        assert isinstance(retriever, VectorRetriever)
        print("[PASS] 配置切换 Baseline 生效")



