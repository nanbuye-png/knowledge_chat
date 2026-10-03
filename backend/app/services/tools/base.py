"""工具抽象层 —— 生产可用的工具契约（审计 §4）。

审计 §4「Agent / Workflow / Tools」原文：

    状态：MISSING（后端） + DOC_ONLY（前端与 README）
    测试：test_sprint31 的 TestToolCalling / TestWorkflow / TestAgent
         **在测试文件内部自定义了 Tool / ToolRegistry / Workflow / Agent 玩具类**，
         与生产代码无任何关系；test_tool_validation 只断言本地 dict
    改进建议：若实现，只做一个真实场景（KB 检索 + Calculator），必须有
         Tool 选择逻辑、Tool 超时、最大执行次数、失败处理

本模块是该建议的落点：**先做工具这一层**（Agent 的规划/执行在
``app/services/agent``、Workflow 的编排在 ``app/services/workflow``，都以薄层复用
本注册表）。四条硬要求与代码的对应关系：

====================  ========================================================
Tool 选择逻辑         :meth:`BaseTool.describe` 输出 JSON Schema，
                     ``GET /api/tools`` 直接交给调用方（前端渲染 / 将来的
                     LLM function-calling）
Tool 超时             :meth:`ToolRegistry.invoke` 用 ``asyncio.wait_for`` 包住
                     工具（上限 ``settings.TOOL_TIMEOUT_SECONDS``）→ ToolTimeout
最大执行次数           :meth:`ToolRegistry.run_plan` 受
                     ``settings.TOOL_MAX_CALLS_PER_REQUEST`` 约束 → 400
失败处理              参数非法 → ToolInvalidArguments（400）；
                     越权/无此资源 → ToolPermissionDenied（403）；
                     未注册 → ToolNotFound（404）；
                     工具内部异常 → ToolExecutionError（502）；
                     超时 → ToolTimeout（504）
====================  ========================================================

所有异常都继承 :class:`~app.core.exceptions.AppError`，因此响应体天然是统一错误
契约 ``{"code", "message", "request_id"}``（审计 §5.5），且错误信息里**不含**
原始异常文本。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ...core.exceptions import AppError

# 支持的参数类型 → 校验用的 Python 类型（只做"能拦住误用"的轻量校验，不引入新依赖）
_TYPE_CHECKS: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list, tuple),
    "object": (dict,),
}


class ToolError(AppError):
    """工具层异常基类：code 供前端/监控按码处理，message 是给用户看的话。"""

    def __init__(self, code: str, message: str, status_code: int = 500):
        super().__init__(code=code, message=message, status_code=status_code)


class ToolNotFound(ToolError):
    def __init__(self, name: str):
        super().__init__(
            code="TOOL_NOT_FOUND", message=f"工具不存在: {name}", status_code=404
        )


class ToolInvalidArguments(ToolError):
    def __init__(self, message: str):
        super().__init__(
            code="TOOL_INVALID_ARGUMENTS", message=message, status_code=400
        )


class ToolPermissionDenied(ToolError):
    def __init__(self, message: str = "无权访问该资源"):
        super().__init__(
            code="TOOL_PERMISSION_DENIED", message=message, status_code=403
        )


class ToolExecutionError(ToolError):
    def __init__(self, message: str = "工具执行失败"):
        super().__init__(
            code="TOOL_EXECUTION_FAILED", message=message, status_code=502
        )


class ToolTimeout(ToolError):
    def __init__(self, name: str, timeout: float):
        super().__init__(
            code="TOOL_TIMEOUT",
            message=f"工具 {name} 执行超时（超过 {timeout:g} 秒）",
            status_code=504,
        )


@dataclass
class ToolContext:
    """一次工具执行的上下文：谁在执行、用哪个数据库会话。

    Attributes:
        user: 当前登录用户（``app.models.user.User``）；``kb_search`` 用它做归属校验。
        db: ``AsyncSession``，由 API 层注入（工具读写与请求同一事务边界）。
        metadata: 预留的调用链信息（如 conversation_id），工具只读。
    """

    user: Any = None
    db: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """一次成功的工具调用结果。"""

    tool: str
    output: dict[str, Any]
    elapsed_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "ok": True,
            "output": self.output,
            "elapsed_ms": self.elapsed_ms,
        }


class BaseTool(ABC):
    """工具基类。

    子类必须声明 ``name`` / ``description`` / ``parameters`` 并实现 :meth:`run`。
    ``parameters`` 用**贴近 JSON Schema 的简化写法**（见 :meth:`json_schema`）：

    .. code-block:: python

        parameters = {
            "query": {"type": "string", "required": True, "description": "检索问题"},
            "top_k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
        }
    """

    name: str = ""
    description: str = ""
    parameters: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # 供「选择逻辑」使用的自描述
    # ------------------------------------------------------------------

    def required_parameters(self) -> list[str]:
        return [k for k, spec in self.parameters.items() if spec.get("required")]

    def json_schema(self) -> dict[str, Any]:
        """把简化写法翻译成标准 JSON Schema（可直接喂给 LLM function-calling）。"""
        properties: dict[str, Any] = {}
        for key, spec in self.parameters.items():
            prop: dict[str, Any] = {"type": spec.get("type", "string")}
            for field_name in ("description", "default", "minimum", "maximum", "enum"):
                if field_name in spec:
                    prop[field_name] = spec[field_name]
            if spec.get("type") == "array" and "items" in spec:
                prop["items"] = spec["items"]
            if spec.get("type") == "string" and "maxLength" in spec:
                prop["maxLength"] = spec["maxLength"]
            properties[key] = prop

        schema: dict[str, Any] = {"type": "object", "properties": properties}
        required = self.required_parameters()
        if required:
            schema["required"] = required
        return schema

    def describe(self) -> dict[str, Any]:
        """工具清单项：``GET /api/tools`` 的元素。"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.json_schema(),
            "required": self.required_parameters(),
        }

    # ------------------------------------------------------------------
    # 参数校验（失败处理的第一道闸门）
    # ------------------------------------------------------------------

    def validate_arguments(self, arguments: dict[str, Any] | None) -> dict[str, Any]:
        """校验并规范化参数；非法即抛 :class:`ToolInvalidArguments`。

        顺序：未知参数拒绝（避免"以为传了却被静默忽略"）→ 必填缺失拒绝 →
        类型不符拒绝 → 数值区间 / 长度 / 枚举拒绝 → 补默认值。
        """
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise ToolInvalidArguments("arguments 必须是对象")

        unknown = sorted(set(arguments) - set(self.parameters))
        if unknown:
            raise ToolInvalidArguments(
                f"工具 {self.name} 不接受参数: {', '.join(unknown)}"
                f"（可用参数: {', '.join(sorted(self.parameters)) or '无'}）"
            )

        cleaned: dict[str, Any] = {}
        for key, spec in self.parameters.items():
            if key not in arguments:
                if spec.get("required"):
                    raise ToolInvalidArguments(f"工具 {self.name} 缺少必填参数: {key}")
                if "default" in spec:
                    cleaned[key] = spec["default"]
                continue

            value = arguments[key]
            expected = spec.get("type", "string")
            allowed = _TYPE_CHECKS.get(expected, (object,))
            # bool 是 int 的子类：integer / number 参数不接受 True / False
            if expected in ("integer", "number") and isinstance(value, bool):
                raise ToolInvalidArguments(f"参数 {key} 必须是 {expected}")
            if not isinstance(value, allowed):
                raise ToolInvalidArguments(
                    f"参数 {key} 类型应为 {expected}，实际 {type(value).__name__}"
                )
            if isinstance(value, (int, float)):
                if "minimum" in spec and value < spec["minimum"]:
                    raise ToolInvalidArguments(f"参数 {key} 不能小于 {spec['minimum']}")
                if "maximum" in spec and value > spec["maximum"]:
                    raise ToolInvalidArguments(f"参数 {key} 不能大于 {spec['maximum']}")
            if isinstance(value, str):
                max_length = spec.get("maxLength")
                if max_length and len(value) > max_length:
                    raise ToolInvalidArguments(
                        f"参数 {key} 长度不能超过 {max_length} 字符"
                    )
                if spec.get("required") and not value.strip():
                    raise ToolInvalidArguments(f"参数 {key} 不能为空白")
            if "enum" in spec and value not in spec["enum"]:
                raise ToolInvalidArguments(
                    f"参数 {key} 只能是: {', '.join(map(str, spec['enum']))}"
                )
            cleaned[key] = value

        return cleaned

    @abstractmethod
    async def run(self, context: ToolContext, **kwargs: Any) -> dict[str, Any]:
        """执行工具本体。

        ``kwargs`` 已经过 :meth:`validate_arguments`（类型 / 区间 / 默认值均已就绪），
        实现里只关心业务语义；抛出的原始异常会被 :class:`ToolRegistry` 包装成
        :class:`ToolExecutionError`（不泄漏原文）。
        """

        return {
            "tool": self.tool,
            "ok": True,
            "output": self.output,
            "elapsed_ms": self.elapsed_ms,
        }
