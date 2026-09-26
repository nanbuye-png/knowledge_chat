"""Citation 测试（Phase 1 §5.5 / P0-3）。

对应计划要求：
* 引用可追溯到 document_id / chunk_id / source / page / section
* 最终回答能形成 ``Sources: - xxx.pdf - Page 12 - Section xxx``
* Citation 必须来自真实 Retrieval Context
* 禁止模型自行生成不存在的引用
* Citation 与最终 Context 必须一致
* 文档删除后 Citation 不应指向不存在的数据
"""
import asyncio
import os
import sys

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend_dir)

from app.services.citation.builder import CitationBuilder  # noqa: E402
from app.services.citation.locator import (  # noqa: E402
    extract_page,
    extract_section,
    resolve_pages,
    resolve_sections,
)
from app.services.citation.models import Citation  # noqa: E402
from app.services.citation.validator import (  # noqa: E402
    documents_exist,
    extract_reference_indices,
    filter_live_citations,
    validate_citations,
)


def _chunk(
    document_id: str,
    chunk_index: int,
    score: float = 0.8,
    page=None,
    section=None,
    text: str = "内容",
) -> dict:
    return {
        "id": f"{document_id}_{chunk_index}",
        "document_id": document_id,
        "filename": f"{document_id}.pdf",
        "chunk_index": chunk_index,
        "text": text,
        "score": score,
        "page": page,
        "section": section,
    }


# ---------------------------------------------------------------------------
# 1: page / section 定位
# ---------------------------------------------------------------------------


class TestLocator:
    def test_extract_page(self):
        assert extract_page("[第3页]\n门诊时间") == 3
        assert extract_page("[第 12 页] xxx") == 12
        assert extract_page("没有页号") is None

    def test_resolve_pages_inherits_previous(self):
        """跨页 chunk 没有页号标记时沿用上一页（比返回 None 更贴近事实）。"""
        chunks = ["[第1页]引言", "内容继续", "[第2页]第二节", "又一段"]
        assert resolve_pages(chunks) == [1, 1, 2, 2]

    def test_extract_section_markdown_and_chinese(self):
        assert extract_section("## 门诊安排\n内容") == "门诊安排"
        assert extract_section("第三章 就诊流程\n正文") == "第三章 就诊流程"
        assert extract_section("没有任何标题的段落") is None

    def test_resolve_sections_inherits_previous(self):
        chunks = ["# 门诊安排", "上午八点", "# 住院须知", "押金说明"]
        assert resolve_sections(chunks) == ["门诊安排", "门诊安排", "住院须知", "住院须知"]


# ---------------------------------------------------------------------------
# 2: Citation 模型与构建
# ---------------------------------------------------------------------------


class TestCitationModel:
    def test_display_and_locator(self):
        citation = Citation(
            document_id="doc1",
            filename="手册.pdf",
            chunk_id=7,
            score=0.9,
            page=12,
            section="门诊安排",
        )
        assert citation.source == "手册.pdf"
        assert citation.display == "手册.pdf · 第12页 · 门诊安排"
        assert citation.locator == {
            "document_id": "doc1",
            "chunk_id": 7,
            "source": "手册.pdf",
            "page": 12,
            "section": "门诊安排",
        }
        print(f"[PASS] 引用展示: {citation.display}")

    def test_display_degrades_without_page_section(self):
        citation = Citation("doc1", "制度.docx", 0, 0.5)
        assert citation.display == "制度.docx"
        assert citation.page is None
        print("[PASS] 缺少定位信息时优雅降级")


class TestCitationBuilder:
    def test_builds_sorted_with_locators(self):
        chunks = [
            _chunk("doc1", 0, 0.5, page=1, section="引言"),
            _chunk("doc2", 3, 0.9, page=12, section="门诊安排"),
        ]
        citations = CitationBuilder().build(chunks)

        assert [c.document_id for c in citations] == ["doc2", "doc1"], "按分数降序"
        assert citations[0].page == 12 and citations[0].section == "门诊安排"
        assert citations[0].chunk_id == 3
        print("[PASS] 引用构建含 page/section 且按分数排序")

    def test_sources_block_format(self):
        citations = CitationBuilder().build(
            [
                _chunk("doc1", 0, page=12, section="门诊安排", text="x"),
                _chunk("doc2", 1, text="y"),
            ]
        )
        block = CitationBuilder.format_sources(citations)
        lines = block.splitlines()
        assert lines[0] == "Sources:"
        assert lines[1].startswith("- doc1.pdf · 第12页 · 门诊安排")
        assert len(lines) == 3
        print(f"[PASS] Sources 块格式:\n{block}")

    def test_format_sources_empty(self):
        assert CitationBuilder.format_sources([]) == ""


# ---------------------------------------------------------------------------
# 3: 一致性校验（禁止自造引用）
# ---------------------------------------------------------------------------


class TestCitationValidation:
    def test_valid_citations_pass(self):
        chunks = [_chunk("doc1", 0), _chunk("doc1", 1)]
        citations = CitationBuilder().build(chunks)

        result = validate_citations(citations, chunks, answer="答案见 [来源1]。")

        assert result.is_consistent
        assert len(result.valid) == 2
        assert result.invalid == []
        assert result.referenced_indices == [1]
        assert result.missing_reference is False
        print("[PASS] 一致引用通过校验")

    def test_citation_not_in_context_is_invalid(self):
        """引用必须来自本次真实检索到的 chunk。"""
        chunks = [_chunk("doc1", 0)]
        fabricated = CitationBuilder().build([_chunk("doc9", 5)])

        result = validate_citations(fabricated, chunks)

        assert result.is_consistent is False
        assert len(result.invalid) == 1
        assert result.invalid[0].document_id == "doc9"
        print("[PASS] 不在上下文中的引用被判为无效")

    def test_out_of_range_reference_detected(self):
        """答案引用了不存在的来源编号（模型自造引用）。"""
        chunks = [_chunk("doc1", 0)]
        citations = CitationBuilder().build(chunks)

        result = validate_citations(citations, chunks, answer="见 [来源3] 与 [来源1]。")

        assert result.invalid_reference_indices == [3]
        assert result.has_fabricated_references is True
        assert result.referenced_indices == [1, 3]
        print("[PASS] 越界引用被识别")

    def test_missing_reference_flagged(self):
        chunks = [_chunk("doc1", 0)]
        citations = CitationBuilder().build(chunks)
        result = validate_citations(citations, chunks, answer="没有引用标记的答案")
        assert result.missing_reference is True
        assert result.is_consistent is True
        print("[PASS] 缺少引用标记会被标记")

    def test_extract_reference_indices_variants(self):
        assert extract_reference_indices("[来源1] 和 [来源2] 和 [来源1]") == [1, 2]
        assert extract_reference_indices("［来源12］") == [12]
        assert extract_reference_indices("无引用") == []

    def test_debug_payload(self):
        chunks = [_chunk("doc1", 0)]
        result = validate_citations(
            CitationBuilder().build(chunks), chunks, answer="[来源9]"
        )
        payload = result.to_dict()
        assert payload["invalid_reference_indices"] == [9]
        assert payload["is_consistent"] is False
        print(f"[PASS] 校验 Debug 输出: {payload['invalid_reference_indices']}")


# ---------------------------------------------------------------------------
# 4: 文档删除后引用不应指向不存在的数据
# ---------------------------------------------------------------------------


class TestDeletionSafety:
    def test_documents_exist_and_filter(self, temp_db):
        from app.models.document import Document, DocumentStatus

        citation = CitationBuilder().build([_chunk("doc-live", 0)])[0]
        dead_citation = CitationBuilder().build([_chunk("doc-deleted", 0)])[0]

        async def scenario():
            async with temp_db.session() as db:
                db.add(
                    Document(
                        id="doc-live",
                        filename="live.pdf",
                        file_size=10,
                        file_type=".pdf",
                        status=DocumentStatus.COMPLETED.value,
                        knowledge_base_id=1,
                    )
                )
                await db.commit()

                alive = await documents_exist(db, ["doc-live", "doc-deleted"])
                live = await filter_live_citations(db, [citation, dead_citation])

                # 删除文档后，其引用也应失效
                from sqlalchemy import delete as sa_delete

                await db.execute(sa_delete(Document).where(Document.id == "doc-live"))
                await db.commit()
                after_delete = await documents_exist(db, ["doc-live"])
                remaining = await filter_live_citations(db, [citation])
                return alive, live, after_delete, remaining

        alive, live, after_delete, remaining = asyncio.run(scenario())

        assert alive == {"doc-live"}, "只应返回仍然存在的文档"
        assert [c.document_id for c in live] == ["doc-live"]
        assert after_delete == set()
        assert remaining == [], "文档删除后其引用不应继续展示"
        print("[PASS] 文档删除后引用被过滤")


# ---------------------------------------------------------------------------
# 5: 检索链路透传 page / section
# ---------------------------------------------------------------------------


class TestLocatorPropagation:
    def test_sparse_index_returns_locators(self, tmp_path):
        """入库写入的 page/section 必须能从稀疏检索结果取回。"""
        from app.services.retrieval.sparse_index import SparseIndex

        index = SparseIndex(path=(tmp_path / "sparse.db").as_posix())

        async def scenario():
            await index.add_document_chunks(
                document_id="doc-1",
                filename="手册.pdf",
                chunks=["[第12页]门诊时间为上午八点", "[第13页]下午两点开始"],
                knowledge_base_id=1,
                user_id=1,
                pages=[12, 13],
                sections=["门诊安排", "门诊安排"],
            )
            return await index.search("门诊时间", knowledge_base_id=1, top_k=5)

        results = asyncio.run(scenario())
        assert results[0]["page"] == 12
        assert results[0]["section"] == "门诊安排"
        print(f"[PASS] 稀疏检索透传定位信息: page={results[0]['page']}")

    def test_pipeline_sources_carry_locators(self, monkeypatch):
        """最终 sources / citations 必须带 page/section（供前端与 SSE 使用）。"""
        import app.services.retrieval_pipeline as pipeline_module
        from app.services.retrieval_pipeline import RetrievalPipeline
        from app.services.query.models import QueryRewriteResult, RewriteStatus

        async def fake_embed(text):
            return [0.1]

        monkeypatch.setattr(
            pipeline_module.embedding_service, "embed_query", fake_embed
        )

        class _Rewriter:
            async def rewrite(self, query, history=None):
                return QueryRewriteResult(
                    original_query=query,
                    rewritten_query=query,
                    rewrite_status=RewriteStatus.SKIPPED.value,
                )

        class _Retriever:
            async def retrieve(self, embedding, knowledge_base_id, top_k=5, query=None):
                return [_chunk("doc-1", 3, 0.9, page=12, section="门诊安排")]

        class _Reranker:
            enabled = False

            async def rerank(self, query, results, top_k=None):
                from app.services.retrieval.reranker import RerankOutcome, RerankStatus

                return RerankOutcome(
                    results=results,
                    candidates_in=len(results),
                    candidates_out=len(results),
                    status=RerankStatus.DISABLED.value,
                )

        pipeline = RetrievalPipeline()
        pipeline._rewriter = _Rewriter()
        pipeline._retriever = _Retriever()
        pipeline._reranker = _Reranker()

        result = asyncio.run(pipeline.retrieve("门诊", knowledge_base_id=1, top_k=3))

        assert result.sources[0]["page"] == 12
        assert result.sources[0]["section"] == "门诊安排"
        assert result.citations[0].page == 12
        assert result.citations[0].display == "doc-1.pdf · 第12页 · 门诊安排"
        print(f"[PASS] 链路透传定位信息: {result.citations[0].display}")


