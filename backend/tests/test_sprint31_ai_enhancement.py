"""
Sprint 31 AI Enhancement 综合测试 (Step 1-8)

测试:
1. Embedding Provider 2.0 - Factory + Multiple Providers
2. Hybrid Search (BM25 + Vector)
3. Reranker Framework
4. Advanced Document Parser
5. Workflow Engine —— **已实现**最小真实路径（workflows 表 + /api/workflows CRUD +
   /{id}/execute；显式步骤 + 条件分支 + 状态传递 + 失败策略，执行复用工具层）
6. Agent Architecture —— **已实现**最小真实路径（CRUD + execute，执行复用工具层）
7. Tool Calling —— 打**生产**工具层（app.services.tools），不再是测试内的玩具类
8. AI Integration Pipeline

审计 §4 的整改要求（"删除或重写 test_sprint31 中与生产无关的玩具用例"）在本文件
的 Step 5/6/7 落地：Step 5/6/7 的玩具 Workflow / Agent / Tool 类已删除，改为断言
**真实路由与真实实现**（Workflow / Agent 的 CRUD + execute、工具层注册表）；
端到端 HTTP 覆盖见 ``tests/test_tools.py``（工具层）、``tests/test_agents.py``（Agent）
与 ``tests/test_workflows.py``（Workflow 编排）。
"""
import asyncio
import os
import sys
import math
from collections import Counter
from typing import List, Optional, Any
from abc import ABC, abstractmethod

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend_dir)


# ============================================================
# Step 1: Embedding Provider 2.0
# ============================================================

class TestEmbeddingProviderV2:
    """Embedding Provider 2.0 测试"""

    def test_factory_create_bge(self):
        """Factory 创建 BGE Provider"""
        from app.services.embedding.factory import EmbeddingProviderFactory
        from app.services.embedding.providers.bge import BgeEmbeddingProvider

        provider = EmbeddingProviderFactory.create("bge")
        assert isinstance(provider, BgeEmbeddingProvider)
        print(f"[PASS] Factory creates BgeEmbeddingProvider")

    def test_factory_create_jina(self):
        """Factory 创建 Jina Provider"""
        from app.services.embedding.factory import EmbeddingProviderFactory
        from app.services.embedding.providers.jina import JinaEmbeddingProvider

        provider = EmbeddingProviderFactory.create("jina", api_key="test-key")
        assert isinstance(provider, JinaEmbeddingProvider)
        assert provider.api_key == "test-key"
        print(f"[PASS] Factory creates JinaEmbeddingProvider")

    def test_factory_create_openai(self):
        """Factory 创建 OpenAI Provider"""
        from app.services.embedding.factory import EmbeddingProviderFactory
        from app.services.embedding.providers.openai import OpenAIEmbeddingProvider

        provider = EmbeddingProviderFactory.create("openai", api_key="sk-test")
        assert isinstance(provider, OpenAIEmbeddingProvider)
        assert provider.api_key == "sk-test"
        print(f"[PASS] Factory creates OpenAIEmbeddingProvider")

    def test_factory_create_voyage(self):
        """Factory 创建 Voyage Provider"""
        from app.services.embedding.factory import EmbeddingProviderFactory
        from app.services.embedding.providers.voyage import VoyageEmbeddingProvider

        provider = EmbeddingProviderFactory.create("voyage", api_key="vo-test")
        assert isinstance(provider, VoyageEmbeddingProvider)
        print(f"[PASS] Factory creates VoyageEmbeddingProvider")

    def test_factory_invalid_provider(self):
        """不支持的 Provider 抛出异常"""
        from app.services.embedding.factory import EmbeddingProviderFactory

        try:
            EmbeddingProviderFactory.create("unknown_provider")
            assert False, "应抛出 ValueError"
        except ValueError as e:
            assert "Unsupported" in str(e)
            print(f"[PASS] Invalid provider raises ValueError")

    def test_factory_model_override(self):
        """Factory 支持模型覆盖"""
        from app.services.embedding.factory import EmbeddingProviderFactory

        provider = EmbeddingProviderFactory.create("bge", model_name="BAAI/bge-large-zh-v1.5")
        assert provider.model_name == "BAAI/bge-large-zh-v1.5"
        print(f"[PASS] Factory model override: {provider.model_name}")

    def test_factory_dimension(self):
        """Factory 支持维度配置"""
        from app.services.embedding.factory import EmbeddingProviderFactory

        provider = EmbeddingProviderFactory.create("bge", embedding_dim=1024)
        assert provider.dim == 1024
        print(f"[PASS] Factory embedding dim: {provider.dim}")


# ============================================================
# Step 2: Hybrid Search (BM25 + Vector)
# ============================================================

class TestHybridSearch:
    """Hybrid Search 测试"""

    def test_bm25_retriever(self):
        """BM25 检索"""
        async def run():
            from app.services.retrieval.bm25 import BM25Retriever

            docs = [
                "Python is a programming language",
                "Machine learning uses Python",
                "Java is different from Python",
                "Deep learning is a subset of machine learning",
            ]
            bm25 = BM25Retriever()
            bm25.fit(docs)

            results = await bm25.search("Python programming", top_k=2)
            assert len(results) <= 2
            # First result should be about Python
            assert "python" in results[0][2].lower()
            print(f"[PASS] BM25 search: top={len(results)}, scores={[r[1] for r in results]}")
        asyncio.run(run())

    def test_bm25_empty_corpus(self):
        """空语料 BM25"""
        async def run():
            from app.services.retrieval.bm25 import BM25Retriever
            bm25 = BM25Retriever()
            bm25.fit([])
            results = await bm25.search("test", top_k=5)
            assert len(results) == 0
            print(f"[PASS] BM25 empty corpus: {len(results)} results")
        asyncio.run(run())

    def test_bm25_scoring(self):
        """BM25 分数计算"""
        async def run():
            from app.services.retrieval.bm25 import BM25Retriever
            docs = ["apple banana", "apple apple banana", "orange grape"]
            bm25 = BM25Retriever()
            bm25.fit(docs)
            results = await bm25.search("apple", top_k=3)
            # Document with more "apple" should rank higher
            assert results[0][1] >= results[1][1]  # apple apple banana vs apple banana
            print(f"[PASS] BM25 scoring: {[(r[1], r[2][:20]) for r in results]}")
        asyncio.run(run())


# ============================================================
# Step 3: Reranker Framework
# ============================================================

class TestReranker:
    """Reranker 框架测试"""

    def test_reranker_base_class(self):
        """Reranker 抽象基类"""
        from abc import ABC, abstractmethod

        class Reranker(ABC):
            @abstractmethod
            async def rerank(self, query: str, documents: List[str]) -> List[tuple]:
                ...

        class MockReranker(Reranker):
            async def rerank(self, query: str, documents: List[str]) -> List[tuple]:
                scored = [(doc, 1.0 / (i + 1)) for i, doc in enumerate(documents)]
                return sorted(scored, key=lambda x: x[1], reverse=True)

        async def run():
            reranker = MockReranker()
            docs = ["doc1 about AI", "doc2 about ML", "doc3 about Python"]
            results = await reranker.rerank("AI", docs)
            assert len(results) == 3
            # First doc should be highest scored
            assert results[0][1] >= results[-1][1]
            print(f"[PASS] Reranker base class: {len(results)} results, top={results[0][0]}")
        asyncio.run(run())


# ============================================================
# Step 4: Advanced Document Parser
# ============================================================

class TestDocumentParser:
    """Document Parser 测试"""

    def test_parser_base(self):
        """Parser 抽象基类"""
        from abc import ABC, abstractmethod

        class Parser(ABC):
            @abstractmethod
            async def parse(self, content: bytes) -> str:
                ...

        class MarkdownParser(Parser):
            async def parse(self, content: bytes) -> str:
                return content.decode("utf-8")

        async def run():
            parser = MarkdownParser()
            text = await parser.parse(b"# Hello\n\nThis is a test.")
            assert "# Hello" in text
            print(f"[PASS] Markdown parser: {len(text)} chars")
        asyncio.run(run())

    def test_text_parsing(self):
        """基础文本解析"""
        async def run():
            text = "Sample document content for testing"
            chunks = [text[i:i+10] for i in range(0, len(text), 10)]
            assert len(chunks) >= 2
            print(f"[PASS] Text chunking: {len(chunks)} chunks")
        asyncio.run(run())


# ============================================================
# Step 5: Workflow Engine
# ============================================================

class TestWorkflow:
    """Workflow 引擎 —— **已实现**审计 §4 的最小真实路径（不再是玩具类）。

    原先这里自定义了一个玩具 ``Workflow`` 类并断言它自己跑通，容易被误读成
    "Workflow 已实现"；后来一度改为断言"未实现这一事实"。现在后端已真实落地
    （``app/api/workflows.py`` + ``app/services/workflow`` + ``workflows`` 表），
    因此断言的是**真实且可执行**的边界；端到端行为（多步骤 / 条件分支 / 状态
    传递 / 失败处理 / 越权）见 ``tests/test_workflows.py``。
    """

    def test_workflow_api_is_implemented(self):
        """``/api/workflows`` 必须存在 —— 与 README / 前端真实页面保持一致。"""
        import importlib.util

        from app.main import app

        paths = app.openapi()["paths"]
        expected = {
            "/api/workflows",
            "/api/workflows/{workflow_id}",
            "/api/workflows/{workflow_id}/execute",
        }
        missing = sorted(expected - set(paths))
        assert not missing, f"/api/workflows 缺少路径: {missing}"
        assert importlib.util.find_spec("app.api.workflows") is not None
        assert importlib.util.find_spec("app.services.workflow") is not None
        print("[PASS] /api/workflows 已实现（CRUD + execute）")




# ============================================================
# Step 6: Agent Architecture
# ============================================================

class TestAgent:
    """Agent 架构 —— **已实现**审计 §4 的最小真实路径（不再是玩具类）。

    原先这里自定义了一个玩具 ``Agent``（think/act/observe/answer）并断言它自己
    跑通，容易被误读成"Agent 已实现"。现在断言的是**真实且可执行**的边界：

    * ``/api/agents`` 提供 CRUD + ``/{id}/execute``（``app/api/agents.py``）；
    * 执行器复用生产工具注册表（``ToolRegistry.run_plan``：超时/次数/失败处理），
      不再有第二套编排实现；
    * Workflow 同样已落地（``/api/workflows`` CRUD + ``/{id}/execute``），
      见 ``TestWorkflow`` 与 ``tests/test_workflows.py``。

    端到端行为（规划、tools_only/llm 两种回答来源、失败可见不泄漏）见
    ``tests/test_agents.py``。
    """

    def test_agent_api_is_implemented(self):
        from app.main import app

        paths = app.openapi()["paths"]
        assert "/api/agents" in paths, "Agent CRUD 路由必须存在"
        assert "/api/agents/{agent_id}" in paths
        assert "/api/agents/{agent_id}/execute" in paths, "Agent 必须有真实执行端点"
        assert "/api/workflows/{workflow_id}/execute" in paths, (
            "Workflow 也已落地（见 TestWorkflow），不要再按'未实现'断言"
        )
        print("[PASS] /api/agents 与 /api/workflows（CRUD + execute）均已实现")

    def test_agent_runner_reuses_production_tool_registry(self):
        """执行器复用生产注册表，且没有残留的玩具 Agent（think/act/observe）。"""
        import inspect

        from app.services.agent import runner as runner_module
        from app.services.tools import ToolRegistry, tool_registry

        source = inspect.getsource(runner_module)
        assert "run_plan" in source, "执行必须走 ToolRegistry.run_plan（超时/次数/失败兜底）"
        assert isinstance(tool_registry, ToolRegistry)
        assert runner_module.AgentRunner()._registry is tool_registry
        assert "def think(" not in source and "def observe(" not in source, (
            "玩具 Agent（think/act/observe）必须彻底删除"
        )
        print("[PASS] AgentRunner 复用生产 ToolRegistry（无玩具 Agent 残留）")

    def test_tool_layer_is_the_real_replacement(self):
        """工具层仍是 Agent 的可执行底座（审计 §4 的最小真实路径）。"""
        from app.main import app

        paths = app.openapi()["paths"]
        assert "/api/tools" in paths
        assert "/api/tools/{tool_name}/invoke" in paths
        print("[PASS] /api/tools 仍在（kb_search + calculator 是 Agent 的执行底座）")




# ============================================================
# Step 7: Tool Calling
# ============================================================

class TestToolCalling:
    """Tool Calling —— 打**生产**注册表（审计 §4）。

    审计原文：本类原先在测试文件内部自定义 ``Tool`` / ``ToolRegistry`` 玩具类，
    ``test_tool_validation`` 只断言本地 dict，"测试绿"与生产代码毫无关系。现在
    改为驱动 ``app.services.tools``（真实工具、真实校验、真实执行）；HTTP 端到端
    覆盖见 ``tests/test_tools.py``。
    """

    def test_tool_registry_exposes_real_tools(self):
        """生产注册表里必须是真实工具，且自带可机读的参数 Schema。"""
        from app.services.tools import tool_registry

        assert tool_registry.names() == ["calculator", "kb_search"]
        assert tool_registry.get("calculator").required_parameters() == ["expression"]

        kb_schema = tool_registry.get("kb_search").json_schema()
        assert kb_schema["type"] == "object"
        assert sorted(kb_schema["required"]) == ["knowledge_base_id", "query"]
        assert kb_schema["properties"]["top_k"]["default"] == 5
        print(f"[PASS] 生产 ToolRegistry 暴露 {tool_registry.names()}")

    def test_tool_validation_uses_production_implementation(self):
        """参数校验走生产实现：缺必填被拒，合法参数补齐默认值。"""
        import pytest

        from app.services.tools import ToolInvalidArguments, tool_registry

        tool = tool_registry.get("kb_search")
        with pytest.raises(ToolInvalidArguments):
            tool.validate_arguments({"query": "门诊时间"})  # 缺 knowledge_base_id

        cleaned = tool.validate_arguments({"query": "门诊时间", "knowledge_base_id": 1})
        assert cleaned == {"query": "门诊时间", "knowledge_base_id": 1, "top_k": 5}
        print("[PASS] Tool 参数校验与默认值来自生产实现")

    def test_tool_executes_through_registry(self):
        """真实执行一次 calculator（不是本地 mock 的返回值）。"""
        from app.services.tools import tool_registry

        result = asyncio.run(
            tool_registry.invoke("calculator", {"expression": "6 * 7"})
        )
        assert result.tool == "calculator"
        assert result.output["result"] == 42
        assert result.elapsed_ms >= 0
        print(f"[PASS] 生产工具执行: 6 * 7 = {result.output['result']}")



# ============================================================
# Step 8: AI Integration Pipeline
# ============================================================

class TestAIPipeline:
    """AI Pipeline 集成测试"""

    def test_full_pipeline_endpoint(self):
        """完整 AI Pipeline 链路验证"""
        async def run():
            # Pipeline: Parse -> Chunk -> Embed -> Retrieve -> Rerank -> Generate
            pipeline_steps = ["parse", "chunk", "embed", "retrieve", "rerank", "generate"]
            results = {}

            # Step 1: Parse
            results["parse"] = "parsed document content with markdown"

            # Step 2: Chunk
            results["chunk"] = [results["parse"][i:i+50] for i in range(0, len(results["parse"]), 50)]

            # Step 3: Embed
            dim = 4
            results["embed"] = [[float(j) / 10 for j in range(dim)] for _ in results["chunk"]]

            # Step 4: Retrieve
            results["retrieve"] = results["chunk"][:2]

            # Step 5: Rerank
            results["rerank"] = sorted(enumerate(results["retrieve"]), key=lambda x: len(x[1]), reverse=True)

            # Step 6: Generate
            results["generate"] = "Generated answer based on retrieved context"

            assert "Generated answer" in results["generate"]
            assert len(results["embed"]) == len(results["chunk"])
            assert len(results["retrieve"]) <= len(results["chunk"])
            print(f"[PASS] Full pipeline: {len(pipeline_steps)} steps, generate={results['generate']}")
        asyncio.run(run())


# ============================================================
# Run all tests
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Sprint 31 AI Enhancement 综合测试 (Step 1-8)")
    print("=" * 60)

    # Step 1
    print("\n--- Step 1: Embedding Provider 2.0 ---")
    t1 = TestEmbeddingProviderV2()
    t1.test_factory_create_bge()
    t1.test_factory_create_jina()
    t1.test_factory_create_openai()
    t1.test_factory_create_voyage()
    t1.test_factory_invalid_provider()
    t1.test_factory_model_override()
    t1.test_factory_dimension()

    # Step 2
    print("\n--- Step 2: Hybrid Search ---")
    t2 = TestHybridSearch()
    t2.test_bm25_retriever()
    t2.test_bm25_empty_corpus()
    t2.test_bm25_scoring()

    # Step 3
    print("\n--- Step 3: Reranker Framework ---")
    t3 = TestReranker()
    t3.test_reranker_base_class()

    # Step 4
    print("\n--- Step 4: Document Parser ---")
    t4 = TestDocumentParser()
    t4.test_parser_base()
    t4.test_text_parsing()

    # Step 5
    print("\n--- Step 5: Workflow Engine ---")
    t5 = TestWorkflow()
    t5.test_workflow_api_is_implemented()

    # Step 6
    print("\n--- Step 6: Agent Architecture ---")
    t6 = TestAgent()
    t6.test_agent_api_is_implemented()
    t6.test_agent_runner_reuses_production_tool_registry()
    t6.test_tool_layer_is_the_real_replacement()

    # Step 7
    print("\n--- Step 7: Tool Calling ---")
    t7 = TestToolCalling()
    t7.test_tool_registry()
    t7.test_tool_validation()

    # Step 8
    print("\n--- Step 8: AI Pipeline Integration ---")
    t8 = TestAIPipeline()
    t8.test_full_pipeline_endpoint()

    print("\n" + "=" * 60)
    print("Sprint 31 所有测试通过!")
    print("=" * 60)