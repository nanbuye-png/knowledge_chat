"""Agent 执行器 —— 真实调用工具层，可选 LLM 汇总（审计 §4）。

执行链路（每一步都能在响应体里看到）：

1. 启用校验 → 未启用直接 409（不返回空结果假装"没有答案"）；
2. :func:`~app.services.agent.planner.build_plan` 做工具选择（确定性规则）；
3. :meth:`ToolRegistry.run_plan` 真实执行：**超时**、**最大次数**、**失败即停**
   全部由工具层兜底（本模块不重复实现，也不绕过）；
4. 汇总回答：
   * 绑定了 ``model_id`` → 调真实 LLM Provider（``LLMProviderFactory``），
     ``answer_mode="llm"``；调用失败 → 502 ``AGENT_GENERATION_FAILED``（原文只落日志）；
   * 未绑定模型 → 由工具结果**直接汇总**，``answer_mode="tools_only"``，
     并在 ``warnings`` 里如实说明"这不是模型生成的回答"。

刻意不做的事：不内置任何"假装有思考过程"的伪 CoT；工具失败不会静默变成空数组，
而是出现在 ``steps[].error`` 与 ``warnings`` 里。
"""

from __future__ import annotations

import time
from typing import Any

from loguru import logger
from sqlalchemy import select

from ...core.config import settings
from ...models.llm_model import LLMModel
from ..tools import ToolContext
from ..tools import tool_registry as default_tool_registry
from .errors import (
    AgentDisabled,
    AgentGenerationFailed,
    AgentNotConfigured,
)
from .planner import build_plan, effective_max_tool_calls

_DEFAULT_SYSTEM_PROMPT = (
    "你是一个企业知识库助手。只根据给定的工具结果回答用户问题；"
    "结果不足以回答时请明确说明不知道，不要编造。"
)


def _build_provider(model: LLMModel, settings_obj: Any):
    """构造 LLM Provider（测试注入点：替换本函数即可避免真实网络调用）。"""
    from ..llm.factory import LLMProviderFactory

    return LLMProviderFactory.create_from_model(model, settings_obj)


class AgentRunner:
    """Agent 执行器（无状态，可安全复用）。"""

    def __init__(self, registry: Any = None) -> None:
        self._registry = registry or default_tool_registry

    async def run(
        self,
        agent: Any,
        query: str,
        context: ToolContext,
        top_k: int | None = None,
    ) -> dict[str, Any]:
        """执行一次 Agent 调用并返回完整的「回答 + 执行轨迹」。"""
        started = time.monotonic()
        if not agent.enabled:
            logger.warning(f"Agent 已禁用，拒绝执行: agent_id={agent.id}")
            raise AgentDisabled(getattr(agent, "name", ""))

        calls, warnings, _ = build_plan(agent, query, self._registry, top_k)
        llm_model = await self._resolve_model(agent, context)

        if not calls and llm_model is None:
            raise AgentNotConfigured(
                "Agent 未配置可执行能力：请绑定知识库/工具，或绑定一个 LLM 模型"
            )

        if calls:
            plan_result = await self._registry.run_plan(calls, context)
        else:
            plan_result = {
                "results": [],
                "completed": 0,
                "aborted": False,
                "max_calls": int(settings.TOOL_MAX_CALLS_PER_REQUEST),
            }

        for step in plan_result["results"]:
            if not step.get("ok"):
                error = step.get("error") or {}
                warnings.append(
                    f"工具 {step['tool']} 失败（{error.get('code', 'TOOL_ERROR')}）："
                    f"{error.get('message', '')}"
                )

        snippets, citations, knowledge_base_name = _collect_kb_output(
            plan_result["results"]
        )
        calculation = _collect_calculation(plan_result["results"])

        if llm_model is not None:
            answer = await self._generate(
                agent, query, snippets, calculation, knowledge_base_name, llm_model
            )
            answer_mode = "llm"
            model_label: str | None = llm_model.model_name
        else:
            answer = _compose_tools_answer(
                snippets, calculation, knowledge_base_name, warnings
            )
            answer_mode = "tools_only"
            model_label = None
            warnings.append(
                "未绑定 LLM 模型：本次回答由工具结果直接汇总（answer_mode=tools_only），"
                "不是模型生成的内容。"
            )

        elapsed_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            f"Agent 执行完成: agent_id={agent.id} mode={answer_mode} "
            f"tools={[step['tool'] for step in plan_result['results']]} "
            f"aborted={plan_result['aborted']} elapsed_ms={elapsed_ms}"
        )

        return {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "query": query,
            "answer": answer,
            "answer_mode": answer_mode,
            "model": model_label,
            "plan": [call["tool"] for call in calls],
            "steps": plan_result["results"],
            "completed": plan_result["completed"],
            "aborted": plan_result["aborted"],
            "max_tool_calls": effective_max_tool_calls(agent),
            "citations": citations,
            "snippets": snippets,
            "warnings": warnings,
            "elapsed_ms": elapsed_ms,
        }

    async def _resolve_model(self, agent: Any, context: ToolContext):
        """解析绑定的 LLMModel；未绑定返回 ``None``，绑定但不可用则报错。

        "绑定却查不到/被禁用"不能静默降级成 tools_only —— 那正是审计点名的
        "看起来正常、其实没生效"。
        """
        model_id = getattr(agent, "model_id", None)
        if not model_id:
            return None
        if context.db is None:
            raise AgentNotConfigured("Agent 执行缺少数据库上下文，无法解析模型")
        result = await context.db.execute(
            select(LLMModel).where(
                LLMModel.id == int(model_id),
                LLMModel.enabled.is_(True),
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise AgentNotConfigured(
                f"绑定的 LLM 模型不存在或已禁用: model_id={model_id}"
            )
        return model

    async def _generate(
        self,
        agent: Any,
        query: str,
        snippets: list[dict[str, Any]],
        calculation: dict[str, Any] | None,
        knowledge_base_name: str,
        llm_model: LLMModel,
    ) -> str:
        """调用真实 LLM Provider 生成回答（失败 → 502，不降级、不静默）。"""
        system_prompt = (getattr(agent, "system_prompt", None) or "").strip()
        messages = [
            {"role": "system", "content": system_prompt or _DEFAULT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _build_user_prompt(
                    query, snippets, calculation, knowledge_base_name
                ),
            },
        ]

        try:
            provider = _build_provider(llm_model, settings)
            response = await provider.chat(messages=messages, stream=False)
        except Exception:
            logger.exception(
                f"Agent LLM 生成失败: agent_id={agent.id} model_id={llm_model.id}"
            )
            raise AgentGenerationFailed()

        if not isinstance(response, str) or not response.strip():
            logger.error(
                f"Agent LLM 返回空内容: agent_id={agent.id} model_id={llm_model.id}"
            )
            raise AgentGenerationFailed()
        return response.strip()

def _collect_kb_output(
    steps: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """从逐步结果里取出 kb_search 的片段 / 引用 / 知识库名。"""
    snippets: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    knowledge_base_name = ""
    for step in steps:
        if step.get("tool") != "kb_search" or not step.get("ok"):
            continue
        output = step.get("output") or {}
        snippets = list(output.get("snippets") or [])
        citations = list(output.get("citations") or [])
        knowledge_base_name = output.get("knowledge_base_name") or ""
    return snippets, citations, knowledge_base_name


def _collect_calculation(steps: list[dict[str, Any]]) -> dict[str, Any] | None:
    """从逐步结果里取出最后一次成功的 calculator 输出。"""
    calculation: dict[str, Any] | None = None
    for step in steps:
        if step.get("tool") == "calculator" and step.get("ok"):
            calculation = step.get("output") or None
    return calculation


def _compose_tools_answer(
    snippets: list[dict[str, Any]],
    calculation: dict[str, Any] | None,
    knowledge_base_name: str,
    warnings: list[str],
) -> str:
    """tools_only 模式的确定性回答（只复述工具真实返回值）。"""
    lines: list[str] = []
    if snippets:
        lines.append(
            f"根据知识库{knowledge_base_name or ''}检索到 {len(snippets)} 个相关片段："
        )
        for snippet in snippets[: settings.AGENT_ANSWER_MAX_SNIPPETS]:
            content = str(snippet.get("content") or "")[
                : settings.AGENT_ANSWER_SNIPPET_CHARS
            ]
            name = snippet.get("document_name") or (
                f"文档{snippet.get('document_id', '')}"
            )
            lines.append(f"{snippet.get('index', '-')}. 《{name}》：{content}")
    if calculation:
        lines.append(
            f"计算结果：{calculation.get('expression', '')} = "
            f"{calculation.get('formatted', '')}"
        )
    if not lines:
        lines.append("本次执行没有获得可用的工具结果，无法回答该问题。")
    return "\n".join(lines)


def _build_user_prompt(
    query: str,
    snippets: list[dict[str, Any]],
    calculation: dict[str, Any] | None,
    knowledge_base_name: str,
) -> str:
    """把工具输出整理成 prompt（片段已由工具截断，这里再按 Agent 预算收口）。"""
    blocks: list[str] = []
    if snippets:
        for snippet in snippets[: settings.AGENT_ANSWER_MAX_SNIPPETS]:
            content = str(snippet.get("content") or "")[
                : settings.AGENT_ANSWER_SNIPPET_CHARS
            ]
            name = snippet.get("document_name") or snippet.get("document_id", "")
            blocks.append(
                f"[片段 {snippet.get('index', '-')}] 来源《{name}》：{content}"
            )
        blocks.insert(0, f"知识库{knowledge_base_name or ''}检索结果")
    else:
        blocks.append("知识库检索结果：无（未配置知识库或无命中）")

    if calculation:
        blocks.append(
            f"[计算器] {calculation.get('expression', '')} = "
            f"{calculation.get('formatted', '')}"
        )

    return (
        f"问题：{query}\n\n"
        "工具结果：\n" + "\n".join(blocks) + "\n\n"
        "请只依据上面的工具结果回答；结果不足时明确说明「无法从知识库中确认」。"
    )

