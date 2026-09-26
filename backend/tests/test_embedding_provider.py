"""
嵌入 Provider 测试（P0-2）

背景
----
1. ``EMBEDDING_DIM`` 默认 768，但 ``bge-small-zh-v1.5`` 实际输出 512 维。
2. ``providers/default.py`` 在模型加载/编码失败时返回**随机向量**，
   让"上传成功但检索全是噪声"的故障静默化。
3. 运行时路径 ``BgeEmbeddingProvider`` 缺少 ``initialized`` 属性，
   导致 ``embedding_service._initialized`` 恒抛 AttributeError
   → ``/api/health`` 的 ``embedding_model`` 永远为 false。
4. 每处理一个文档都会重新加载一次嵌入模型（未做进程内缓存）。

测试:
1. 默认维度 = 512（config / factory / provider 三处一致）
2. query 加检索指令前缀，document 不加
3. 模型按名字进程内缓存（不重复加载）
4. 加载失败 → EmbeddingError（不是随机向量）
5. 编码失败 → EmbeddingError
6. DefaultEmbeddingProvider 已无随机兜底
7. initialized 属性真实反映模型状态（修复 health 静默降级）
"""
import asyncio
import os
import sys
import types

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend_dir)

from app.core.config import settings  # noqa: E402
from app.services.embedding import providers as providers_pkg  # noqa: E402
from app.services.embedding.base import EmbeddingError  # noqa: E402
from app.services.embedding.factory import EmbeddingProviderFactory  # noqa: E402
from app.services.embedding.providers import bge as bge_module  # noqa: E402
from app.services.embedding.providers.bge import (  # noqa: E402
    BGE_SMALL_ZH_DIM,
    BGE_ZH_QUERY_INSTRUCTION,
    BgeEmbeddingProvider,
)
from app.services.embedding.providers.default import (  # noqa: E402
    DefaultEmbeddingProvider,
)


# ---------------------------------------------------------------------------
# 测试替身
# ---------------------------------------------------------------------------


class _Vec:
    """模拟 numpy 数组（只需 tolist）。"""

    def __init__(self, data):
        self._data = data

    def tolist(self):
        return self._data


class _FakeModel:
    """模拟 SentenceTransformer 实例。"""

    def __init__(self, name: str, encode_error: Exception | None = None):
        self.name = name
        self.encode_error = encode_error
        self.encode_calls: list[tuple] = []

    def encode(self, texts, **kwargs):
        self.encode_calls.append((texts, kwargs))
        if self.encode_error is not None:
            raise self.encode_error
        if isinstance(texts, str):
            return _Vec([0.1, 0.2, 0.3])
        return _Vec([[0.1, 0.2, 0.3] for _ in texts])


class _FakeSentenceTransformerModule:
    """伪造 sentence_transformers 模块，记录实例化次数。"""

    def __init__(self, error: Exception | None = None):
        self.instances: list[_FakeModel] = []
        self._error = error
        self._module = types.ModuleType("sentence_transformers")

        outer = self

        class _ST:
            def __new__(cls, name):
                if outer._error is not None:
                    raise outer._error
                model = _FakeModel(name)
                outer.instances.append(model)
                return model

        self._module.SentenceTransformer = _ST

    @property
    def module(self):
        return self._module


def _install_fake_model(monkeypatch, error: Exception | None = None):
    """安装伪 sentence_transformers 并清空 bge 模型缓存。"""
    fake = _FakeSentenceTransformerModule(error=error)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake.module)
    monkeypatch.setattr(bge_module, "_MODEL_CACHE", {})
    return fake



# ---------------------------------------------------------------------------
# 1: 维度一致性
# ---------------------------------------------------------------------------


class TestEmbeddingDimension:
    def test_config_dim_is_512(self):
        """回归：EMBEDDING_DIM 必须与 bge-small-zh-v1.5 一致（512）。"""
        assert BGE_SMALL_ZH_DIM == 512
        assert settings.EMBEDDING_DIM == 512, (
            f"EMBEDDING_DIM={settings.EMBEDDING_DIM} 与该模型实际维度不符"
        )
        print(f"[PASS] EMBEDDING_DIM={settings.EMBEDDING_DIM}")

    def test_factory_and_provider_defaults(self):
        """factory / provider 的默认维度也必须是 512。"""
        provider = EmbeddingProviderFactory.create("bge")
        assert provider.dim == 512, f"provider.dim={provider.dim}"
        assert BgeEmbeddingProvider().dim == 512
        print(f"[PASS] provider.dim={provider.dim}")


# ---------------------------------------------------------------------------
# 2-3: 指令前缀 + 模型缓存
# ---------------------------------------------------------------------------


class TestBgeProviderBehaviour:
    def test_query_prefix_only_on_query(self, monkeypatch):
        """query 侧加检索指令前缀；document 侧不加。"""
        _install_fake_model(monkeypatch)
        provider = BgeEmbeddingProvider()

        async def run():
            await provider.embed_query("知识库是什么")
            await provider.embed_documents(["文档内容 A", "文档内容 B"])

        asyncio.run(run())

        model = provider._model
        query_call, docs_call = model.encode_calls
        assert query_call[0] == BGE_ZH_QUERY_INSTRUCTION + "知识库是什么", (
            "query 必须带检索指令前缀"
        )
        assert docs_call[0] == ["文档内容 A", "文档内容 B"], (
            "document 不得带检索指令前缀"
        )
        assert query_call[1].get("normalize_embeddings") is True
        print("[PASS] query 带前缀 / document 不带前缀")

    def test_model_cached_across_providers(self, monkeypatch):
        """同一模型的 provider 复用同一模型实例（不重复加载）。"""
        fake = _install_fake_model(monkeypatch)

        async def run():
            p1 = BgeEmbeddingProvider("BAAI/bge-small-zh-v1.5")
            p2 = BgeEmbeddingProvider("BAAI/bge-small-zh-v1.5")
            await p1.initialize()
            await p2.initialize()
            return p1, p2

        p1, p2 = asyncio.run(run())
        assert len(fake.instances) == 1, "同一模型名只应加载一次"
        assert p1._model is p2._model
        print("[PASS] 模型进程内缓存生效")

    def test_empty_documents_short_circuit(self, monkeypatch):
        """空文档列表不应触发模型加载。"""
        fake = _install_fake_model(monkeypatch)
        provider = BgeEmbeddingProvider()
        assert asyncio.run(provider.embed_documents([])) == []
        assert fake.instances == []
        print("[PASS] 空输入短路，未加载模型")

    def test_initialized_reflects_model_state(self, monkeypatch):
        """initialized 属性必须真实反映模型状态（修复 health 静默降级）。"""
        _install_fake_model(monkeypatch)
        provider = BgeEmbeddingProvider()
        assert provider.initialized is False
        asyncio.run(provider.initialize())
        assert provider.initialized is True
        print("[PASS] initialized 属性正确")

    def test_embedding_service_health_flag(self):
        """embedding_service._initialized 不再抛 AttributeError。"""
        from app.services.embedding_service import embedding_service

        assert hasattr(embedding_service, "_initialized"), (
            "health 检查依赖该属性，缺失会导致 embedding_model 恒为 false"
        )
        assert isinstance(embedding_service._initialized, bool)
        print(f"[PASS] embedding_service._initialized={embedding_service._initialized}")


# ---------------------------------------------------------------------------
# 4-6: 显式失败（禁止随机向量兜底）
# ---------------------------------------------------------------------------


class TestExplicitFailure:
    def test_load_failure_raises(self, monkeypatch):
        """模型加载失败 → EmbeddingError（不是随机向量）。"""
        _install_fake_model(monkeypatch, error=RuntimeError("download failed"))
        provider = BgeEmbeddingProvider()

        try:
            asyncio.run(provider.initialize())
            raise AssertionError("加载失败应抛出 EmbeddingError")
        except AssertionError:
            raise
        except EmbeddingError as exc:
            assert "加载嵌入模型失败" in str(exc)
            print(f"[PASS] 加载失败抛 EmbeddingError: {str(exc)[:40]}…")

    def test_missing_dependency_raises(self, monkeypatch):
        """依赖缺失 → EmbeddingError 且提示安装方式。"""
        monkeypatch.setattr(bge_module, "_MODEL_CACHE", {})
        # 让 import sentence_transformers 失败
        monkeypatch.setitem(sys.modules, "sentence_transformers", None)
        provider = BgeEmbeddingProvider()

        try:
            asyncio.run(provider.initialize())
            raise AssertionError("依赖缺失应抛出 EmbeddingError")
        except AssertionError:
            raise
        except (EmbeddingError, ImportError) as exc:
            print(f"[PASS] 依赖缺失显式失败: {type(exc).__name__}")

    def test_encode_failure_raises(self, monkeypatch):
        """编码失败 → EmbeddingError。"""
        _install_fake_model(monkeypatch)
        provider = BgeEmbeddingProvider()
        model = _FakeModel("fake", encode_error=RuntimeError("cuda oom"))
        provider._model = model

        try:
            asyncio.run(provider.embed_query("问题"))
            raise AssertionError("编码失败应抛出 EmbeddingError")
        except AssertionError:
            raise
        except EmbeddingError as exc:
            assert "生成查询向量失败" in str(exc)
            print(f"[PASS] 编码失败抛 EmbeddingError: {str(exc)[:40]}…")

    def test_default_provider_has_no_random_fallback(self, monkeypatch):
        """DefaultEmbeddingProvider 不再存在随机向量兜底。"""
        provider = DefaultEmbeddingProvider("fake-model", 512)
        assert not hasattr(provider, "_fallback_embeddings"), (
            "随机向量兜底必须被移除（会静默污染向量库）"
        )

        try:
            asyncio.run(provider.embed_documents(["内容"]))
            raise AssertionError("模型未就绪时应显式失败")
        except AssertionError:
            raise
        except EmbeddingError as exc:
            assert "未就绪" in str(exc)
            print(f"[PASS] 未就绪时显式失败: {str(exc)[:40]}…")

    def test_default_provider_load_failure_raises(self, monkeypatch):
        """DefaultEmbeddingProvider 加载失败必须抛出，而不是返回随机向量。"""
        fake = _FakeSentenceTransformerModule(error=RuntimeError("no network"))
        monkeypatch.setitem(sys.modules, "sentence_transformers", fake.module)
        monkeypatch.setitem(sys.modules, "transformers", None)

        provider = DefaultEmbeddingProvider("fake-model", 512)
        try:
            asyncio.run(provider.initialize())
            raise AssertionError("加载失败应抛出 EmbeddingError")
        except AssertionError:
            raise
        except (EmbeddingError, ImportError) as exc:
            print(f"[PASS] 加载失败显式抛出: {type(exc).__name__}")
        assert provider._initialized is False, "失败时不得把 initialized 设为 True"


if __name__ == "__main__":
    print("=" * 50)
    print("嵌入 Provider 测试 (P0-2) — 请使用 pytest 运行")
    print("=" * 50)

