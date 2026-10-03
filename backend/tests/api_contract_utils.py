"""前后端接口契约的公共工具（Phase A 新增）。

背景
----
审计反复出现同一类"静默失败"：前端调用的路径在后端**根本不存在**
（``/admin/api-keys``、``/auth/change-password``、
``/prompt-templates/{id}/compile``、``/admin/system/config``），
而两边各自的测试都是绿的 —— 因为没有任何测试**同时知道两边**。
本模块把两侧的权威事实取出来做交集，供 ``test_api_key_contract.py``
（局部）与 ``test_api_contract.py``（全量）复用，避免各写一套扫描逻辑。

后端侧：``app.openapi()["paths"]``
----------------------------------
**不能**用 ``app.routes``：实测本仓库的 FastAPI 0.139.0 会把
``include_router`` 包装成 ``_IncludedRouter`` 对象放进 ``app.routes``，
真实路径一条都不在里面（实测 ``len(app.routes) == 27`` 且 22 条是包装器，
``len(app.openapi()["paths"]) == 55``）。任何"遍历 app.routes 断言路径"
的测试都会**静默地什么都扫不到**却依然通过 —— 这正是本工具存在的意义。

前端侧：``apiClient.<method>('...')`` 字面量
-------------------------------------------
``frontend/src/api/client.ts`` 的 ``baseURL`` 已是 ``/api``，因此约定：
字面量**不得**以 ``/api`` 开头（``/api/api-keys`` 会请求到
``/api/api/api-keys``）。这条约定在这里被显式判定为违规，
而不是靠人肉回忆。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: 前端 api 调用字面量：apiClient.get('/x') / apiClient.patch(`/x/${id}/revoke`)
FRONTEND_CALL_RE = re.compile(
    r"""apiClient\s*\.\s*(get|post|put|patch|delete)\s*\(\s*(['"`])([^'"`]*)\2"""
)

_METHODS = ("get", "post", "put", "patch", "delete")

#: 路径参数：OpenAPI 的 ``{key_id}`` 与前端模板串的 ``${keyId}`` 等价为 ``{}``
_PARAM_RE = re.compile(r"\{[^}]*\}")
_TEMPLATE_RE = re.compile(r"\$\{[^}]*\}")


def normalize_path(path: str) -> str:
    """把 ``/api/api-keys/{key_id}`` 与 ``/api/api-keys/${id}`` 都归一为 ``/api/api-keys/{}``。"""
    normalized = _TEMPLATE_RE.sub("{}", path)
    normalized = _PARAM_RE.sub("{}", normalized)
    if len(normalized) > 1:
        normalized = normalized.rstrip("/")
    return normalized or "/"


@dataclass(frozen=True)
class FrontendCall:
    """前端源码里的一处 ``apiClient`` 调用。"""

    file: str
    line: int
    method: str
    raw_path: str

    @property
    def problem(self) -> str | None:
        """字面量本身的写法问题（与后端是否存在无关）。"""
        if not self.raw_path.startswith("/"):
            return f"路径必须以 / 开头：{self.raw_path!r}"
        if self.raw_path.startswith("/api/") or self.raw_path == "/api":
            return f"重复 /api 前缀（baseURL 已含 /api）：{self.raw_path!r}"
        return None

    @property
    def expected_route(self) -> str:
        """按 baseURL 约定还原出的后端真实路径。"""
        if self.raw_path.startswith("/api/"):
            return normalize_path(self.raw_path)
        return normalize_path("/api" + self.raw_path)

    def describe(self) -> str:
        return f"{self.file}:{self.line} {self.method} {self.raw_path}"


def repo_root() -> Path:
    """仓库根目录（``backend/tests/`` 上溯两级）。"""
    return Path(__file__).resolve().parents[2]


def frontend_src_root() -> Path:
    """``frontend/src``；不存在时返回该路径，由调用方决定是否 fail（不静默跳过）。"""
    return repo_root() / "frontend" / "src"


def iter_frontend_calls(src_root: Path | None = None) -> list[FrontendCall]:
    """扫描 ``frontend/src`` 下所有 ``.ts`` / ``.tsx`` 里的 apiClient 调用。"""
    root = src_root or frontend_src_root()
    calls: list[FrontendCall] = []
    for path in sorted(root.rglob("*")):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        if "node_modules" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:  # pragma: no cover - 源码不应是非 UTF-8
            continue
        relative = path.relative_to(root.parent.parent).as_posix()
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in FRONTEND_CALL_RE.finditer(line):
                calls.append(
                    FrontendCall(
                        file=relative,
                        line=lineno,
                        method=match.group(1).upper(),
                        raw_path=match.group(3),
                    )
                )
    return calls


def iter_calls_in_file(relative_path: str, src_root: Path | None = None) -> list[FrontendCall]:
    """只取某个前端文件里的调用（传给 ``relative_path`` 用仓库相对路径，如
    ``frontend/src/pages/account/ApiKeysPage.tsx``）。"""
    return [call for call in iter_frontend_calls(src_root) if call.file == relative_path]


def real_routes() -> set[tuple[str, str]]:
    """后端真实可路由集合：``{(\"GET\", \"/api/api-keys\"), ...}``。

    Raises:
        AssertionError: 若 ``app.openapi()`` 里一条路径都没有 —— 那说明
            路由根本没注册上，此时的"契约测试全绿"毫无意义。
    """
    from app.main import app

    paths = app.openapi().get("paths", {})
    assert paths, "app.openapi() 没有任何路径：路由注册已被破坏"
    routes: set[tuple[str, str]] = set()
    for path, operations in paths.items():
        for method in _METHODS:
            if method in operations:
                routes.add((method.upper(), normalize_path(path)))
    return routes


def contract_violations(
    calls: list[FrontendCall], routes: set[tuple[str, str]] | None = None
) -> list[str]:
    """返回「前端调用 → 后端不存在（或字面量写法违规）」的说明列表。"""
    available = routes if routes is not None else real_routes()
    problems: list[str] = []
    for call in calls:
        if call.problem:
            problems.append(f"{call.describe()} → {call.problem}")
            continue
        if (call.method, call.expected_route) not in available:
            problems.append(
                f"{call.describe()} → 后端不存在 {call.method} {call.expected_route}"
            )
    return problems
