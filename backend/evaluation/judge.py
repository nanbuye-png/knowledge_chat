"""LLM 裁判 —— 用真实模型评估生成质量（正确性 / 忠实度 / 幻觉）。

三条纪律
--------
1. **裁判只加不要减**：裁判模型给出 0/1 判断，是"下限证据"而不是绝对真值，
   报告里必须标注裁判模型名与"未做人工双标注"。
2. **解析失败不是 0 分**：JSON 解析失败记为 ``judge_error``，从分母中剔除并单独
   统计，绝不用 0 分伪装成"模型答错"。
3. **忠实度只看上下文**：``faithful`` 判断的是"回答是否被本次检索到的上下文支撑"，
   与"参考答案是否包含该事实"是两件事（后者属于 ``correct``）。

注意：Agens 的 ``agnes-2.5-flash`` 属于推理型模型，会先消耗 token 输出
``reasoning_content``，因此 ``max_tokens`` 必须留足（默认 800），否则正文为空。
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Optional

from loguru import logger

#: 上下文注入裁判时的截断长度（控制 token 成本）
MAX_CONTEXT_CHARS = 6000

#: 判定为\"瞬时\"错误的特征串（限流 / 网关 / 超时 / 连接）。
#: 免费额度下 Agens 会返回 429 ``You've reached the API rate limit for free
#: users``——实测 71 题里有 20 题因此丢掉判分，所以必须重试，
#: 但**只对瞬时错误重试**：参数错误、鉴权失败重试再多次也不会成功。
#:
#: Phase 3 §5.2：线上链路引入统一重试后，判定收敛到
#: :func:`app.core.retry.is_retryable`；这里保留同一份特征串，仅用于评测
#: 脱离 ``app`` 包单独运行时的兜底。
TRANSIENT_ERROR_MARKERS = (
    "429",
    "too many requests",
    "rate limit",
    "rate_limit",
    "rate-limit",
    "overloaded",
    "temporarily",
    "timeout",
    "timed out",
    "connection error",
    "apiconnection",
    "502",
    "503",
    "504",
)


def is_transient_error(exc: BaseException) -> bool:
    """Return ``True`` when retrying the same request may succeed.

    Phase 3 §5.2：判定委托给 :func:`app.core.retry.is_retryable` —— 评测与
    线上必须共用同一套"可重试 / 不可重试"标准，否则会出现"评测靠重试救回来
    的题，线上照样失败"。``app`` 包不可导入时回退到本模块的特征串。
    """
    try:
        from app.core.retry import is_retryable
    except ImportError:  # pragma: no cover - 评测可脱离 app 包单独运行
        text = f"{type(exc).__name__}: {exc}".lower()
        return any(marker in text for marker in TRANSIENT_ERROR_MARKERS)

    return is_retryable(exc)

JUDGE_SYSTEM_PROMPT = "你是一个严格的 RAG 评测裁判，只输出 JSON，不输出任何解释性文字。"

JUDGE_TEMPLATE = """【任务】判断检索增强问答系统的回答质量。

【用户问题】
{question}

【标准参考答案】
{reference_answer}

【系统检索到的上下文】
{context}

【系统回答】
{answer}

【评判规则】
1. correct：回答是否包含标准参考答案中的关键事实，且没有与参考答案矛盾。
   注意：若【标准参考答案】为空，说明该问题在语料中并不存在答案，
   此时只有回答明确表示"知识库中没有足够信息/无法回答"才判 true；
   若回答给出了具体事实或结论则判 false。
2. faithful：回答中的每个事实性陈述是否都能在【系统检索到的上下文】里找到依据。
   只要出现上下文中没有的数字、名称或结论，就判 false。
3. hallucination：回答是否在没有上下文依据的情况下给出了具体事实或结论。
4. reason：一句话说明理由（30 字以内）。

只输出 JSON，不要输出 markdown 代码块：
{{"correct": true, "faithful": true, "hallucination": false, "reason": "..."}}"""

_TRUE_STRINGS = {"true", "1", "yes", "y", "是", "正确", "对"}


@dataclass
class Judgement:
    """裁判结果。``judge_error`` 非空表示本次裁判无效（不参与比率计算）。"""

    item_id: str = ""
    correct: bool = False
    faithful: bool = False
    hallucination: bool = False
    reason: str = ""
    judge_error: str = ""
    attempts: int = 1
    raw: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in _TRUE_STRINGS
    return False


def parse_judgement(raw: str) -> Optional[dict[str, Any]]:
    """Tolerantly parse the judge's JSON reply.

    Handles markdown fences, leading/trailing prose, and nested JSON.
    Returns ``None`` when no JSON object can be recovered.
    """
    if not raw:
        return None

    text = raw.strip()
    # 去掉 markdown 代码块围栏
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    candidates = [text]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def build_judge_prompt(
    question: str,
    reference_answer: str,
    answer: str,
    context: str,
) -> str:
    """Render the judge prompt (single user message)."""
    return JUDGE_TEMPLATE.format(
        question=question,
        reference_answer=reference_answer.strip() or "（无，该问题在语料中没有答案）",
        context=(context or "（无上下文）")[:MAX_CONTEXT_CHARS],
        answer=(answer or "（空回答）")[:MAX_CONTEXT_CHARS],
    )


class LLMJudge:
    """Wrap an :class:`LLMProvider` into a judge with strict JSON parsing.

    两类失败都会重试（最多 ``retry`` 次），但动机不同：

    * **瞬时服务错误**（429 限流 / 5xx / 超时 / 连接失败）：指数退避重试，
      免费额度下这是常态（实测 71 题里 20 题被 429 打掉）。
    * **不可用的输出**（空正文 / 非 JSON）：固定短延迟后重试——推理型模型
      偶尔把 token 全花在 reasoning 上导致正文为空，重试通常即可恢复。

    重试次数写进 :class:`Judgement.attempts`，供报告区分"一次成功"与"重试恢复"。
    """

    def __init__(
        self,
        provider: Any,
        max_tokens: int = 800,
        temperature: float = 0.0,
        retry: int = 4,
        retry_base_delay: float = 3.0,
        retry_max_delay: float = 30.0,
        output_retry_delay: float = 1.0,
        sleep: Optional[Any] = None,
    ) -> None:
        self._provider = provider
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._retry = max(1, int(retry))
        self._retry_base_delay = max(0.0, float(retry_base_delay))
        self._retry_max_delay = max(0.0, float(retry_max_delay))
        self._output_retry_delay = max(0.0, float(output_retry_delay))
        self._sleep = sleep or asyncio.sleep

    @property
    def model(self) -> str:
        return getattr(self._provider, "_model", "unknown")

    @property
    def retry(self) -> int:
        return self._retry

    def _backoff(self, attempt: int) -> float:
        """指数退避（attempt 从 1 开始），上限 ``retry_max_delay``。"""
        delay = self._retry_base_delay * (2 ** (attempt - 1))
        return min(delay, self._retry_max_delay)

    async def _call_once(self, messages: list[dict[str, str]]) -> str:
        """单次调用裁判模型（不含重试）。"""
        return await self._provider.chat(
            messages=messages,
            stream=False,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )

    async def judge(
        self,
        item_id: str,
        question: str,
        reference_answer: str,
        answer: str,
        context: str,
    ) -> Judgement:
        """Judge one answer; never raises — failures become ``judge_error``."""
        messages = [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_judge_prompt(
                    question=question,
                    reference_answer=reference_answer,
                    answer=answer,
                    context=context,
                ),
            },
        ]

        for attempt in range(1, self._retry + 1):
            try:
                raw = await self._call_once(messages)
            except Exception as exc:  # noqa: BLE001 - 裁判失败不能中断评测
                transient = is_transient_error(exc)
                if transient and attempt < self._retry:
                    delay = self._backoff(attempt)
                    logger.warning(
                        f"裁判瞬时失败 item={item_id} attempt={attempt}/{self._retry}: "
                        f"{exc} → {delay:.1f}s 后重试"
                    )
                    if delay:
                        await self._sleep(delay)
                    continue
                logger.warning(
                    f"裁判调用失败 item={item_id}（尝试 {attempt} 次，"
                    f"transient={transient}）: {exc}"
                )
                return Judgement(
                    item_id=item_id,
                    judge_error=f"llm_error: {exc}",
                    attempts=attempt,
                )

            if not isinstance(raw, str) or not raw.strip():
                if attempt < self._retry:
                    logger.warning(
                        f"裁判返回空内容 item={item_id} attempt={attempt}/{self._retry} → 重试"
                    )
                    await self._sleep(self._output_retry_delay)
                    continue
                return Judgement(
                    item_id=item_id,
                    judge_error="empty_judge_response",
                    attempts=attempt,
                    raw=str(raw),
                )

            parsed = parse_judgement(raw)
            if parsed is None:
                if attempt < self._retry:
                    logger.warning(
                        f"裁判输出无法解析 item={item_id} attempt={attempt}/{self._retry}: "
                        f"{raw[:80]!r} → 重试"
                    )
                    await self._sleep(self._output_retry_delay)
                    continue
                logger.warning(f"裁判输出无法解析 item={item_id}: {raw[:120]!r}")
                return Judgement(
                    item_id=item_id,
                    judge_error="parse_error",
                    attempts=attempt,
                    raw=raw[:500],
                )

            return Judgement(
                item_id=item_id,
                correct=_coerce_bool(parsed.get("correct")),
                faithful=_coerce_bool(parsed.get("faithful")),
                hallucination=_coerce_bool(parsed.get("hallucination")),
                reason=str(parsed.get("reason", ""))[:200],
                attempts=attempt,
                raw=raw[:500],
            )

        # 理论不可达：循环内每个分支都会 return
        raise AssertionError("unreachable judge state")


def create_judge(
    settings_obj: Any = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    retry: Optional[int] = None,
    retry_base_delay: Optional[float] = None,
) -> LLMJudge:
    """Build a judge from the configured LLM provider.

    Reuses :class:`LLMProviderFactory` so the judge runs on the **same provider
    and model as production** unless ``EVAL_JUDGE_MAX_TOKENS`` /
    ``EVAL_JUDGE_TEMPERATURE`` override it.  ``EVAL_JUDGE_RETRY`` /
    ``EVAL_JUDGE_RETRY_DELAY`` control the 429/5xx backoff.
    """
    # 注意：必须用绝对导入。`evaluation` 与 `app` 是并列的顶层包，
    # `from ..core.config import ...` 会越出顶层包并抛
    # "attempted relative import beyond top-level package"。
    from app.core.config import settings as app_settings
    from app.services.llm.factory import LLMProviderFactory

    conf = settings_obj or app_settings
    provider = LLMProviderFactory.create(conf)
    return LLMJudge(
        provider=provider,
        max_tokens=int(
            max_tokens
            if max_tokens is not None
            else getattr(conf, "EVAL_JUDGE_MAX_TOKENS", 800)
        ),
        temperature=float(
            temperature
            if temperature is not None
            else getattr(conf, "EVAL_JUDGE_TEMPERATURE", 0.0)
        ),
        retry=int(
            retry if retry is not None else getattr(conf, "EVAL_JUDGE_RETRY", 4)
        ),
        retry_base_delay=float(
            retry_base_delay
            if retry_base_delay is not None
            else getattr(conf, "EVAL_JUDGE_RETRY_DELAY", 3.0)
        ),
        output_retry_delay=float(
            getattr(conf, "EVAL_JUDGE_OUTPUT_RETRY_DELAY", 1.0)
        ),
    )

