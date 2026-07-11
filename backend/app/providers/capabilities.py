"""Provider capability descriptors.

Each field describes a feature that an LLM provider/model may or may not
support.  These descriptors allow callers (services, API layers, etc.) to
discover what a concrete provider can do **without coupling to the provider
implementation**.

Usage example::

    provider = get_llm_provider("deepseek")
    if provider.capabilities.supports_stream:
        async for token in provider.stream_chat(messages):
            ...

See Also:
    :mod:`.capability_checker` — runtime capability validation helpers.
"""

from dataclasses import dataclass


@dataclass
class ModelCapability:
    """Describes the capabilities of a specific LLM provider/model.

    All fields default to ``False`` — each provider declares exactly what
    it supports by enabling the relevant flags in its ``__init__`` method.

    Attributes:
        supports_stream (bool): Whether the provider supports streaming
            (SSE) responses.
        supports_tools (bool): Whether the provider supports tool/function
            calling.
        supports_vision (bool): Whether the provider supports image/vision
            inputs.
        supports_json (bool): Whether the provider supports JSON mode /
            structured output.
        supports_embeddings (bool): Whether the provider can generate
            embeddings.
    """

    supports_stream: bool = False
    """Whether the provider supports streaming (SSE) responses."""

    supports_tools: bool = False
    """Whether the provider supports tool/function calling."""

    supports_vision: bool = False
    """Whether the provider supports image / vision inputs."""

    supports_json: bool = False
    """Whether the provider supports JSON mode / structured output."""

    supports_embeddings: bool = False
    """Whether the provider can generate embeddings."""