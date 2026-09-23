# Provider 系统

## 概览

所有外部服务通过 Provider 抽象层接入，支持热插拔。

## LLM Provider

| Provider | 文件 | 配置 | 常用模型 |
|----------|------|------|----------|
| DeepSeek | `services/llm/deepseek_provider.py` | `DEEPSEEK_API_KEY`, `DEEPSEEK_API_BASE` | `deepseek-chat` |
| Agens | `services/llm/agens_provider.py` | `AGENS_API_KEY`, `AGENS_API_BASE` | `agnes-2.5-flash`（默认）、`agnes-2.5-pro`、`agnes-3.0-flash`、`agnes-2.0-flash` |

Provider 与模型名通过 `.env` 配置：

```bash
LLM_PROVIDER=agens                       # deepseek | agens
LLM_MODEL=agnes-2.5-flash                # 必须与 LLM_PROVIDER 匹配
AGENS_API_KEY=sk-xxx
AGENS_API_BASE=https://apihub.agnes-ai.com/v1
```

已知模型清单维护在 `app/core/config.py` 的 `KNOWN_MODELS`；
`Settings.check_llm_config()` 会在启动时校验 Provider / 模型名前缀 / API Key 是否匹配并输出告警。

> 注：Agens 的 `agnes-2.5-flash` 属于推理型模型，会先返回 `reasoning_content` 再返回正文，
> 且推理 token 计入 `max_tokens`。`AgensProvider` 已忽略 reasoning 增量并去除正文首部前导换行。

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