"""Agent 层异常 —— 与工具层同一套错误契约（审计 §5.5 / §4）。

全部继承 :class:`~app.core.exceptions.AppError`，因此响应体天然是
``{"code", "message", "request_id"}``；500 以上由全局处理器补 ``request_id``，
**内部异常原文只落日志**（``logger.exception``），不拼进 message。
"""

from ...core.exceptions import AppError


class AgentNotFound(AppError):
    """Agent 不存在或不属于当前用户（对外统一 404，不区分"别人的"）。"""

    def __init__(self, agent_id: int | None = None):
        super().__init__(
            code="AGENT_NOT_FOUND",
            message="Agent 不存在" + (f": {agent_id}" if agent_id is not None else ""),
            status_code=404,
        )


class AgentDisabled(AppError):
    """Agent 已禁用：执行被拒绝（不是"空结果"）。"""

    def __init__(self, name: str = ""):
        super().__init__(
            code="AGENT_DISABLED",
            message=f"Agent 已禁用，无法执行{': ' + name if name else ''}",
            status_code=409,
        )


class AgentNotConfigured(AppError):
    """没有任何可执行能力（既没有可用工具，也没有可用的 LLM 模型）。"""

    def __init__(self, message: str = "Agent 未配置可执行能力（工具或模型）"):
        super().__init__(
            code="AGENT_NOT_CONFIGURED", message=message, status_code=400
        )


class AgentGenerationFailed(AppError):
    """LLM 生成失败：对外固定文案，原始异常只落日志。"""

    def __init__(self, message: str = "Agent 生成回答失败，请稍后重试"):
        super().__init__(
            code="AGENT_GENERATION_FAILED", message=message, status_code=502
        )
