"""Provider capability descriptors.

Each field describes a feature that an LLM provider/model may or may not
support.  These descriptors allow callers (services, API layers, etc.) to
discover what a concrete provider can do without coupling to the provider
implementation.
"""

from dataclasses import dataclass


@dataclass
class ModelCapability:
    """Describes the capabilities of a specific LLM provider/model.

    All fields default to ``False`` — each provider declares exactly what it
    supports.
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