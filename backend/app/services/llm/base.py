"""Unified LLM Provider abstract interface.

All concrete LLM providers (DeepSeek, OpenAI, Gemini, etc.) MUST inherit
from :class:`LLMProvider` and implement :meth:`chat`.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional, Union

import httpx


@dataclass
class LLMUsageInfo:
    """一次 LLM 调用的用量与延迟（Phase 3 §5.6 / 审计 §3.4）。

    Attributes:
        model: 实际使用的模型名。
        prompt_tokens: 输入 token 数。
        completion_tokens: 输出 token 数。
        latency_ms: 调用耗时（毫秒）。
        estimated: ``True`` 表示 token 数为**启发式估算**（provider 未回报，
            流式调用常见），前端/报表必须能区分"实测值"与"估算值"。
    """

    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    estimated: bool = False

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数（中文约 1 token ≈ 1 字，英文约 1 token ≈ 4 字符）。

    审计 §3.4 指出 usage 端到端缺失；在 provider 不回报 usage 的场景
    （流式 / 兼容接口）下，宁可给出**标注为估算**的数字，也不要让
    llm_usages 表永远是空的。
    """
    if not text:
        return 0
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    wide_chars = len(text) - ascii_chars
    return int(wide_chars + ascii_chars / 4) + 1


async def call_with_usage(
    provider: Any,
    messages: list[dict[str, Any]],
    **kwargs: Any,
) -> tuple[Any, LLMUsageInfo]:
    """调用 provider 的非流式接口，返回 ``(response, usage)``。

    Provider 未实现 :meth:`LLMProvider.chat_with_usage`（测试替身或第三方实现）
    时回退到 :meth:`chat` + 启发式估算 —— "拿不到 usage" 不应该让问答失败。
    """
    import time

    impl = getattr(provider, "chat_with_usage", None)
    if callable(impl):
        return await impl(messages=messages, **kwargs)

    start = time.perf_counter()
    response = await provider.chat(messages=messages, stream=False, **kwargs)
    prompt_text = "\n".join(
        m.get("content", "") for m in messages if isinstance(m.get("content"), str)
    )
    usage = LLMUsageInfo(
        model=str(kwargs.get("model") or ""),
        prompt_tokens=estimate_tokens(prompt_text),
        completion_tokens=estimate_tokens(response if isinstance(response, str) else ""),
        latency_ms=(time.perf_counter() - start) * 1000,
        estimated=True,
    )
    return response, usage


def build_llm_http_client(
    disable_proxy: bool = False,
    timeout: float | None = None,
    connect_timeout: float | None = None,
) -> httpx.AsyncClient:
    """Build a shared ``httpx.AsyncClient`` for LLM providers.

    Centralises proxy and timeout handling so that LLM API calls do not
    silently depend on the ambient system/environment proxy (e.g. Clash on
    ``127.0.0.1:7897``) unless explicitly allowed via ``disable_proxy=False``.

    Args:
        disable_proxy: When ``True``, set ``trust_env=False`` to bypass any
            proxy configured at the OS/environment level.
        timeout: Read/write timeout in seconds (default 120).  Applies to the
            time between successive chunks of a streaming response.
        connect_timeout: Connect/pool timeout in seconds (default 10).

    Returns:
        A configured :class:`httpx.AsyncClient` ready to be passed as the
        ``http_client`` of an ``AsyncOpenAI`` instance.
    """
    return httpx.AsyncClient(
        trust_env=not disable_proxy,
        timeout=httpx.Timeout(
            connect=connect_timeout if connect_timeout is not None else 10.0,
            read=timeout if timeout is not None else 120.0,
            write=timeout if timeout is not None else 120.0,
            pool=connect_timeout if connect_timeout is not None else 10.0,
        ),
    )


class LLMProvider(ABC):
    """Abstract base class for LLM chat providers.

    Defines a single async entry-point ``chat`` that every provider
    must implement.  Extra provider‑specific parameters (temperature,
    top_p, max_tokens, tools, response_format, …) are passed through
    ``**kwargs`` for forward compatibility.
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        stream: bool = False,
        **kwargs: Any,
    ) -> Union[str, AsyncIterator[str]]:
        """Send a conversation to the LLM and return the response.

        Args:
            messages: A list of message dicts (e.g.
                ``{"role": "user", "content": "Hello"}``).
            stream: If ``True``, return an async iterator that yields
                response chunks rather than the full response at once.
            **kwargs: Provider‑specific parameters such as
                ``temperature``, ``top_p``, ``max_tokens``,
                ``tools``, ``response_format``, etc.

        Returns:
            When ``stream=False``: the complete response as a ``str``.
            When ``stream=True``: an ``AsyncIterator[str]`` yielding
            response chunks.
        """
        ...

    async def chat_with_usage(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> tuple[Any, LLMUsageInfo]:
        """非流式调用并返回 ``(response, usage)``（审计 §3.4 Token Usage）。

        默认实现回退到 :meth:`chat`，token 数用 :func:`estimate_tokens` 估算并
        置 ``estimated=True``；能从响应里读到真实 usage 的 Provider 应覆写本方法。
        """
        import time

        start = time.perf_counter()
        response = await self.chat(messages=messages, stream=False, **kwargs)
        latency_ms = (time.perf_counter() - start) * 1000

        prompt_text = "\n".join(
            m.get("content", "") for m in messages if isinstance(m.get("content"), str)
        )
        usage = LLMUsageInfo(
            model=str(kwargs.get("model") or ""),
            prompt_tokens=estimate_tokens(prompt_text),
            completion_tokens=estimate_tokens(
                response if isinstance(response, str) else ""
            ),
            latency_ms=latency_ms,
            estimated=True,
        )
        return response, usage
