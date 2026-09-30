"""工具注册表 —— 选择逻辑 + 超时 + 最大执行次数 + 失败处理（审计 §4）。

它替代了审计点名的那种"测试文件里的玩具 Registry"：
``test_sprint31_ai_enhancement.py::TestToolCalling`` 以前在测试内部自定义
``Tool`` / ``ToolRegistry`` 并只断言本地 dict，测试绿与生产无关。现在测试直接打
这一份注册表（见 ``tests/test_tools.py``）。

职责边界：
- **本模块不做编排**：Workflow 仍未实现；Agent 的规划/执行在
  ``app/services/agent``（``AgentRunner``），它调用本模块的 :meth:`ToolRegistry.run_plan`
  作为受限执行器（顺序、次数上限、逐步超时、失败即停），没有第二套执行实现。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger

from ...core.config import settings
from .base import (
    BaseTool,
    ToolContext,
    ToolError,
    ToolExecutionError,
    ToolInvalidArguments,
    ToolNotFound,
    ToolResult,
    ToolTimeout,
)


class ToolRegistry:
    """工具注册表：注册 / 查询 / 执行。"""

    def __init__(self, timeout: float | None = None) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._timeout = timeout

    # ------------------------------------------------------------------
    # 注册与查询
    # ------------------------------------------------------------------

    def register(self, tool: BaseTool) -> None:
        """注册工具；重名或未声明 name 属于开发期错误，直接抛 ValueError。"""
        if not tool.name:
            raise ValueError(f"工具缺少 name: {type(tool).__name__}")
        if tool.name in self._tools:
            raise ValueError(f"工具重复注册: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFound(name)
        return tool

    def names(self) -> list[str]:
        return sorted(self._tools)

    def list_tools(self) -> list[dict[str, Any]]:
        """工具清单（供调用方做选择）：按名称排序，包含 JSON Schema 参数描述。"""
        return [self._tools[name].describe() for name in self.names()]

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------

    def _resolve_timeout(self, timeout: float | None) -> float:
        if timeout is not None:
            return timeout
        if self._timeout is not None:
            return self._timeout
        return float(settings.TOOL_TIMEOUT_SECONDS)

    async def invoke(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        context: ToolContext | None = None,
        timeout: float | None = None,
    ) -> ToolResult:
        """执行一次工具调用。

        Raises:
            ToolNotFound: 未注册的工具（404）。
            ToolInvalidArguments: 参数非法（400）。
            ToolError: 工具自身抛出的业务异常（如 403、502）。
            ToolTimeout: 超过 ``timeout`` 秒仍未返回（504）。
        """
        tool = self.get(name)
        # 参数校验放在超时之外：非法参数是请求问题，不该占用执行预算
        cleaned = tool.validate_arguments(arguments)
        limit = self._resolve_timeout(timeout)
        context = context or ToolContext()

        started = time.monotonic()
        try:
            output = await asyncio.wait_for(
                tool.run(context, **cleaned), timeout=limit
            )
        except asyncio.TimeoutError:
            logger.warning(f"工具执行超时: tool={name} timeout={limit:g}s")
            raise ToolTimeout(name, limit)
        except ToolError:
            raise
        except Exception:
            # 原始异常只落日志（带堆栈），对外统一文案 —— 与审计 §5.5 的错误契约一致
            logger.exception(f"工具执行失败: tool={name}")
            raise ToolExecutionError(f"工具 {name} 执行失败")
        elapsed_ms = int((time.monotonic() - started) * 1000)

        if not isinstance(output, dict):
            logger.error(f"工具返回值必须是 dict: tool={name} type={type(output).__name__}")
            raise ToolExecutionError(f"工具 {name} 返回值格式非法")

        return ToolResult(tool=name, output=output, elapsed_ms=elapsed_ms)

    async def run_plan(
        self,
        calls: list[dict[str, Any]],
        context: ToolContext | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """按顺序执行一组工具调用（受最大次数约束，失败即停并保留已完成结果）。

        Args:
            calls: ``[{"tool": "calculator", "arguments": {...}}, ...]``。
            context: 执行上下文（用户 / DB 会话）。
            timeout: 单次调用的超时覆盖值。

        Returns:
            ``{"results": [...], "completed": n, "aborted": bool, "max_calls": N}``；
            ``results`` 里每一步都是 ``{"tool", "ok", "output"|"error", "elapsed_ms"}``。

        Raises:
            ToolInvalidArguments: 调用列表格式非法或超过
                ``settings.TOOL_MAX_CALLS_PER_REQUEST``（400）。
        """
        max_calls = int(settings.TOOL_MAX_CALLS_PER_REQUEST)
        if not isinstance(calls, list) or not calls:
            raise ToolInvalidArguments("calls 必须是非空数组")
        if len(calls) > max_calls:
            raise ToolInvalidArguments(f"一次最多执行 {max_calls} 次工具调用")

        results: list[dict[str, Any]] = []
        aborted = False
        for step in calls:
            if not isinstance(step, dict) or not isinstance(step.get("tool"), str):
                raise ToolInvalidArguments(
                    "calls 的每一项必须是 {'tool': str, 'arguments': object}"
                )
            name = step["tool"]
            started = time.monotonic()
            try:
                result = await self.invoke(
                    name, step.get("arguments"), context, timeout=timeout
                )
                results.append(result.to_dict())
            except ToolError as exc:
                results.append(
                    {
                        "tool": name,
                        "ok": False,
                        "error": {"code": exc.code, "message": exc.message},
                        "elapsed_ms": int((time.monotonic() - started) * 1000),
                    }
                )
                aborted = True
                break

        return {
            "results": results,
            "completed": sum(1 for r in results if r["ok"]),
            "aborted": aborted,
            "max_calls": max_calls,
        }
