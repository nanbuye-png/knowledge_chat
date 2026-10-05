"""Workflow 服务层公开入口（审计 §4）。

组成：

==================  ==========================================================
``templating``      状态传递（``{{input}}`` / ``{{steps.<id>.output.*}}``）+ 条件分支
``runner``          顺序执行：复用 ``ToolRegistry`` 的超时/参数校验/失败包装
``errors``          Workflow 层异常（同一套错误契约，不含内部原文）
==================  ==========================================================

与 Agent 的分工（README / ``docs/architecture.md`` 同一口径）：

* **Agent** = 动态规划 + 工具选择 + 循环（``app/services/agent``）；
* **Workflow** = 用户**显式声明**的有序步骤 + 条件分支 + 状态传递 + 失败处理
  （本包）。两者共用同一份 ``app/services/tools`` 注册表，没有第二套工具执行。

数学意图（``when: input_is_math``）与 calculator 步骤的参数补齐都复用
``app/services/math_intent.py`` 这一份规则，不另起口径。
"""

from .errors import (
    WorkflowDisabled,
    WorkflowInvalidStep,
    WorkflowNotFound,
    WorkflowNotConfigured,
)
from .runner import (
    INPUT_FILLED_ARGUMENTS,
    TEMPLATE_ERROR_CODE,
    WorkflowRunner,
    apply_argument_defaults,
)
from .templating import (
    ON_ERROR_CHOICES,
    WHEN_ALWAYS,
    WHEN_CHOICES,
    WHEN_INPUT_IS_MATH,
    WHEN_PREVIOUS_FAILED,
    WHEN_PREVIOUS_SUCCEEDED,
    TemplateError,
    evaluate_condition,
    iter_references,
    known_step_references,
    resolve_value,
)

__all__ = [
    "INPUT_FILLED_ARGUMENTS",
    "ON_ERROR_CHOICES",
    "TEMPLATE_ERROR_CODE",
    "TemplateError",
    "WHEN_ALWAYS",
    "WHEN_CHOICES",
    "WHEN_INPUT_IS_MATH",
    "WHEN_PREVIOUS_FAILED",
    "WHEN_PREVIOUS_SUCCEEDED",
    "WorkflowDisabled",
    "WorkflowInvalidStep",
    "WorkflowNotFound",
    "WorkflowNotConfigured",
    "WorkflowRunner",
    "apply_argument_defaults",
    "evaluate_condition",
    "iter_references",
    "known_step_references",
    "resolve_value",
]
