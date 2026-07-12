# Provider 系统

## 概览

所有外部服务通过 Provider 抽象层接入，支持热插拔。

## LLM Provider

| Provider | 文件 | 配置 |
|----------|------|------|
| DeepSeek | `services/llm/deepseek_provider.py` | `DEEPSEEK_API_KEY`, `DEEPSEEK_API_BASE` |
| Agens | `services/llm/agens_provider.py` | `AGENS_API_KEY`, `AGENS_API_BASE` |

### 接口
```python
class LLMProvider(ABC):
    async def chat(messages: list[dict], stream: bool = False, **kwargs) -> str | AsyncIterator[str]
```

### 扩展
1. 创建 `services/llm/openai_provider.py`，实现 `LLMProvider`
2. 在 `factory.py` 中注册：`_PROVIDERS["openai"] = OpenAIProvider`
3. 设置 `.env`: `LLM_PROVIDER=openai`

## Embedding Provider

| Provider | 文件 | 配置 |
|----------|------|------|
| Default (BGE) | `services/embedding/providers/default.py` | `EMBEDDING_MODEL` |

### 接口
```python
class EmbeddingProvider(ABC):
    async def embed_text(text) -> list[float]
    async def embed_query(text) -> list[float]
    async def embed_documents(texts) -> list[list[float]]
```

### 扩展
1. 创建 `services/embedding/providers/openai.py`
2. 在 factory 中注册
3. 设置 `.env`: `EMBEDDING_PROVIDER=openai`