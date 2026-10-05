"""工具层测试 —— 审计 §4（Agent / Workflow / Tools）。

审计点名的问题（原文）：

    test_sprint31_ai_enhancement.py 的 TestToolCalling / TestWorkflow / TestAgent
    **在测试文件内部自定义了 Tool / ToolRegistry / Workflow / Agent 玩具类**，
    与生产代码无任何关系；test_tool_validation 只断言本地 dict
    改进建议：只做一个真实场景（KB 检索 + Calculator），必须有 Tool 选择逻辑、
    Tool 超时、最大执行次数、失败处理

本文件打的是**生产代码**（``app.services.tools`` + ``/api/tools/*`` 真实路由、
真实 SQLite），逐条覆盖审计要求的四条硬约束：

1. Tool 选择逻辑 → ``GET /api/tools`` 暴露 JSON Schema；
2. Tool 超时 → 慢工具返回 504 ``TOOL_TIMEOUT``（含 ``request_id``）；
3. 最大执行次数 → ``POST /api/tools/run`` 超过上限返回 400；
4. 失败处理 → 参数非法 400 / 越权 403 / 未注册 404 / 内部异常 502，
   且响应体**不含**原始异常文本（审计 §5.5 错误契约）。
"""

import asyncio
from pathlib import Path

import pytest

from app.services.tools import BaseTool, ToolRegistry

pytestmark = pytest.mark.usefixtures("no_rate_limits")

PASSWORD = "Str0ng!Passw0rd123"
SECRET_LEAK = "BOOM /var/lib/postgresql/dsn=postgresql://root:hunter2@db"


def _register_and_login(client, username: str) -> dict:
    reg = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": PASSWORD,
        },
    )
    assert reg.status_code in (200, 201), reg.text
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _create_kb(client, headers: dict, name: str) -> int:
    resp = client.post("/api/knowledge-bases", json={"name": name}, headers=headers)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


class _FakeCitation:
    def to_dict(self) -> dict:
        return {"document_id": "doc-1", "filename": "手册.pdf", "chunk_id": 0, "score": 0.9}


class _FakeRetrieval:
    """检索链路替身（只替检索，不替工具本身）。"""

    def __init__(self, sources=None, has_results=True):
        self.sources = sources if sources is not None else [
            {"document_id": "doc-1", "filename": "手册.pdf", "chunk_index": 0,
             "score": 0.91, "text": "门诊时间：周一至周五 8:00-17:00"},
            {"document_id": "doc-2", "filename": "制度.docx", "chunk_index": 3,
             "score": 0.72, "text": "x" * 900, "page": 12, "section": "预约"},
        ]
        self.results = list(self.sources)
        self.has_results = has_results
        self.search_query = "门诊时间"
        self.rewrite_status = "skipped"
        self.citations = [_FakeCitation()]


class _FakePipeline:
    def __init__(self, result=None, error: Exception | None = None):
        self._result = result or _FakeRetrieval()
        self._error = error
        self.calls: list[dict] = []

    async def retrieve(self, question, knowledge_base_id, top_k=None, **kwargs):
        self.calls.append({"question": question, "kb": knowledge_base_id, "top_k": top_k})
        if self._error is not None:
            raise self._error
        return self._result


def _patch_kb_search_pipeline(monkeypatch, pipeline) -> None:
    """把检索替身注入生产工具实例（工具本身、注册表、路由都不替换）。"""
    from app.services.tools import tool_registry

    tool = tool_registry.get("kb_search")
    monkeypatch.setattr(tool, "_pipeline", pipeline)


class TestToolListContract:
    """1. Tool 选择逻辑：清单必须自带可机读的参数 Schema。"""

    def test_requires_authentication(self, client):
        resp = client.get("/api/tools")
        assert resp.status_code in (401, 403), resp.text
        print(f"[PASS] GET /api/tools 未登录 → {resp.status_code}")

    def test_lists_real_tools_with_schema(self, client):
        headers = _register_and_login(client, "tools_list")
        resp = client.get("/api/tools", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()

        names = [t["name"] for t in body["tools"]]
        assert names == ["calculator", "kb_search"], body
        assert body["max_calls_per_request"] > 0
        assert body["timeout_seconds"] > 0

        calculator = next(t for t in body["tools"] if t["name"] == "calculator")
        assert calculator["required"] == ["expression"]
        schema = calculator["parameters"]
        assert schema["type"] == "object"
        assert schema["properties"]["expression"]["type"] == "string"

        kb_search = next(t for t in body["tools"] if t["name"] == "kb_search")
        assert sorted(kb_search["required"]) == ["knowledge_base_id", "query"]
        assert kb_search["parameters"]["properties"]["top_k"]["default"] == 5
        print(f"[PASS] /api/tools 暴露 {names} 的 JSON Schema")


class TestCalculatorTool:
    """calculator：真实求值 + 参数/表达式失败的边界。"""

    def test_evaluates_expression(self, client):
        headers = _register_and_login(client, "tools_calc")
        resp = client.post(
            "/api/tools/calculator/invoke",
            json={"arguments": {"expression": "(1 + 2) * 3 - 4 // 2"}},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        assert body["output"]["result"] == 7
        assert body["output"]["result_type"] == "int"
        assert body["elapsed_ms"] >= 0
        print(f"[PASS] calculator: {(1 + 2) * 3 - 4 // 2} = {body['output']['result']}")

    def test_short_form_endpoint_accepts_bare_arguments(self, client):
        """``POST /api/tools/calculator`` 的 body 直接就是工具参数。"""
        headers = _register_and_login(client, "tools_calc_short")
        resp = client.post(
            "/api/tools/calculator",
            json={"expression": "sqrt(16) + pi"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["output"]["result"] == pytest.approx(7.14159265, abs=1e-6)
        print("[PASS] 简写端点 /api/tools/calculator 可用")

    def test_accepts_natural_language_question(self, client):
        """``1+2是多少`` 这类问句：按与 Agent 同一套规则先取出表达式，再求值。"""
        headers = _register_and_login(client, "tools_calc_nl")
        resp = client.post(
            "/api/tools/calculator/invoke",
            json={"arguments": {"expression": "1+2是多少"}},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        output = resp.json()["output"]
        assert output["result"] == 3
        assert output["expression"] == "1+2", "expression 应是实际参与求值的表达式"
        assert output["input_expression"] == "1+2是多少", "原始入参必须如实回显"
        print("[PASS] calculator 接受「1+2是多少」→ 3（同一套识别规则先取出表达式）")


    @pytest.mark.parametrize(
        "payload, expected_fragment",
        [
            ({}, "缺少必填参数"),
            ({"expression": "1/0"}, "除数不能为零"),
            ({"expression": "__import__('os')"}, "不支持的函数"),
            ({"expression": "__import__('os').system('id')"}, "只允许调用白名单函数"),
            ({"expression": "[1, 2][0]"}, "不支持的语法"),
            ({"expression": "1+1", "extra": 1}, "不接受参数"),
            ({"expression": "2 ** 5000"}, "幂指数"),
            ({"expression": "x + 1"}, "不支持的变量"),
            ({"expression": "math.pi"}, "不支持的语法"),
            ({"expression": 3}, "类型应为 string"),
            # 取不出表达式的自然语言问句 / 残缺表达式：仍然是 400（宽容只到"能取出表达式"为止）
            ({"expression": "门诊时间是什么时候"}, "不支持的变量"),
            ({"expression": "1 +"}, "表达式语法错误"),
        ],
    )
    def test_rejects_unsafe_or_invalid_input(self, client, payload, expected_fragment):
        """非法表达式/参数一律 400，且**不会**执行到求值（没有 eval 后门）。"""
        headers = _register_and_login(client, "tools_calc_bad")
        resp = client.post(
            "/api/tools/calculator/invoke",
            json={"arguments": payload},
            headers=headers,
        )
        assert resp.status_code == 400, resp.text
        body = resp.json()
        assert body["code"] == "TOOL_INVALID_ARGUMENTS", body
        assert expected_fragment in body["message"], body
        print(f"[PASS] calculator 拒绝 {payload!r} → {body['message']}")


class TestKnowledgeBaseSearchTool:
    """kb_search：真实归属校验 + 输出裁剪 + 失败不泄漏。"""

    def test_searches_owned_knowledge_base(self, client, monkeypatch):
        from app.core.config import settings

        headers = _register_and_login(client, "tools_kb_owner")
        kb_id = _create_kb(client, headers, "工具库")
        pipeline = _FakePipeline()
        _patch_kb_search_pipeline(monkeypatch, pipeline)

        resp = client.post(
            "/api/tools/kb_search/invoke",
            json={
                "arguments": {
                    "query": "门诊时间",
                    "knowledge_base_id": kb_id,
                    "top_k": 2,
                }
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        output = resp.json()["output"]
        assert output["knowledge_base_id"] == kb_id
        assert output["knowledge_base_name"] == "工具库"
        assert output["has_results"] is True
        assert output["snippet_count"] == 2
        assert pipeline.calls == [
            {"question": "门诊时间", "kb": kb_id, "top_k": 2}
        ]
        first, second = output["snippets"]
        assert first["document_name"] == "手册.pdf"
        assert first["content"].startswith("门诊时间")
        assert second["truncated"] is True
        assert len(second["content"]) == settings.TOOL_KB_SEARCH_SNIPPET_CHARS
        assert second["page"] == 12 and second["section"] == "预约"
        assert output["citations"][0]["filename"] == "手册.pdf"
        print(f"[PASS] kb_search 返回 {output['snippet_count']} 个裁剪后的片段")

    def test_rejects_other_users_knowledge_base(self, client, monkeypatch):
        """审计 §6.2：工具端点不能成为绕过归属校验的越权读入口。"""
        owner = _register_and_login(client, "tools_kb_owner2")
        kb_id = _create_kb(client, owner, "别人的库")
        intruder = _register_and_login(client, "tools_kb_intruder")
        pipeline = _FakePipeline()
        _patch_kb_search_pipeline(monkeypatch, pipeline)

        resp = client.post(
            "/api/tools/kb_search/invoke",
            json={"arguments": {"query": "门诊时间", "knowledge_base_id": kb_id}},
            headers=intruder,
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["code"] == "TOOL_PERMISSION_DENIED"
        assert pipeline.calls == [], "越权请求不应该到达检索层"
        print("[PASS] kb_search 拒绝他人知识库（403 且未触发检索）")

    def test_internal_failure_is_opaque(self, client, monkeypatch):
        headers = _register_and_login(client, "tools_kb_fail")
        kb_id = _create_kb(client, headers, "故障库")
        _patch_kb_search_pipeline(
            monkeypatch, _FakePipeline(error=RuntimeError(SECRET_LEAK))
        )

        resp = client.post(
            "/api/tools/kb_search/invoke",
            json={"arguments": {"query": "任意", "knowledge_base_id": kb_id}},
            headers=headers,
        )
        assert resp.status_code == 502, resp.text
        assert SECRET_LEAK not in resp.text, f"响应泄漏了内部细节：{resp.text}"
        body = resp.json()
        assert body["code"] == "TOOL_EXECUTION_FAILED"
        assert body["message"] == "知识库检索失败，请稍后重试"
        assert body.get("request_id"), "工具内部错误必须带 request_id"
        print(f"[PASS] kb_search 内部异常 → {body['code']}（无细节泄漏）")

    def test_unknown_tool_returns_404(self, client):
        headers = _register_and_login(client, "tools_unknown")
        resp = client.post(
            "/api/tools/not_a_tool/invoke", json={"arguments": {}}, headers=headers
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["code"] == "TOOL_NOT_FOUND"
        print("[PASS] 未注册工具 → 404 TOOL_NOT_FOUND")


class _SlowTool(BaseTool):
    """测试用慢工具（证明超时是执行器兜底的，而不是靠工具自觉）。"""

    name = "slow_probe"
    description = "测试替身：睡够指定秒数"
    parameters = {"seconds": {"type": "number", "default": 5.0}}

    async def run(self, context, seconds: float = 5.0, **kwargs):
        await asyncio.sleep(seconds)
        return {"slept": seconds}


class _BoomTool(BaseTool):
    name = "boom_probe"
    description = "测试替身：抛内部异常"
    parameters = {}

    async def run(self, context, **kwargs):
        raise RuntimeError(SECRET_LEAK)


class TestToolRegistryContract:
    """注册表自身的硬约束（不经过 HTTP，直接打生产类）。"""

    def test_duplicate_and_nameless_registration_rejected(self):
        registry = ToolRegistry()
        registry.register(_BoomTool())
        with pytest.raises(ValueError, match="重复注册"):
            registry.register(_BoomTool())

        class _NoName(BaseTool):
            description = "no name"

            async def run(self, context, **kwargs):
                return {}

        with pytest.raises(ValueError, match="缺少 name"):
            registry.register(_NoName())
        print("[PASS] 重名 / 无 name 的注册被拒绝")

    def test_unexpected_exception_is_wrapped_without_leaking(self):
        from app.services.tools import ToolExecutionError

        registry = ToolRegistry()
        registry.register(_BoomTool())
        with pytest.raises(ToolExecutionError) as exc:
            asyncio.run(registry.invoke("boom_probe"))
        assert exc.value.status_code == 502
        assert SECRET_LEAK not in exc.value.message
        print(f"[PASS] 内部异常被包装为 {exc.value.code}（message 不含原文）")

    def test_timeout_is_enforced_by_registry(self):
        from app.services.tools import ToolTimeout

        registry = ToolRegistry(timeout=0.05)
        registry.register(_SlowTool())
        with pytest.raises(ToolTimeout) as exc:
            asyncio.run(registry.invoke("slow_probe", {"seconds": 5}))
        assert exc.value.status_code == 504
        print(f"[PASS] 超时由执行器兜底 → {exc.value.code}")

    def test_argument_validation(self):
        from app.services.tools import ToolInvalidArguments, ToolNotFound

        registry = ToolRegistry()
        with pytest.raises(ToolNotFound) as exc:
            asyncio.run(registry.invoke("nope"))
        assert exc.value.status_code == 404

        registry.register(_SlowTool())
        with pytest.raises(ToolInvalidArguments) as exc:
            asyncio.run(registry.invoke("slow_probe", {"seconds": "很快"}))
        assert exc.value.status_code == 400
        print("[PASS] 未注册 404 / 参数类型不符 400")

    def test_run_plan_enforces_max_calls(self, monkeypatch):
        from app.services.tools import ToolInvalidArguments, registry as registry_module

        monkeypatch.setattr(registry_module.settings, "TOOL_MAX_CALLS_PER_REQUEST", 1)
        registry = ToolRegistry()
        registry.register(_SlowTool())
        calls = [
            {"tool": "slow_probe", "arguments": {"seconds": 0}},
            {"tool": "slow_probe", "arguments": {"seconds": 0}},
        ]
        with pytest.raises(ToolInvalidArguments) as exc:
            asyncio.run(registry.run_plan(calls))
        assert "一次最多执行 1 次" in exc.value.message
        print(f"[PASS] 最大执行次数生效 → {exc.value.message}")



class TestToolRunEndpoint:
    """POST /api/tools/run：顺序执行 + 失败即停 + 次数上限。"""

    def test_runs_plan_in_order(self, client):
        headers = _register_and_login(client, "tools_plan")
        resp = client.post(
            "/api/tools/run",
            json={
                "calls": [
                    {"tool": "calculator", "arguments": {"expression": "2+2"}},
                    {"tool": "calculator", "arguments": {"expression": "10/4"}},
                ]
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["completed"] == 2
        assert body["aborted"] is False
        assert body["max_calls"] > 0
        assert [r["output"]["result"] for r in body["results"]] == [4, 2.5]
        print(f"[PASS] /api/tools/run 顺序执行 {body['completed']} 步")

    def test_plan_aborts_and_keeps_partial_results(self, client):
        headers = _register_and_login(client, "tools_plan_abort")
        resp = client.post(
            "/api/tools/run",
            json={
                "calls": [
                    {"tool": "calculator", "arguments": {"expression": "1+1"}},
                    {"tool": "calculator", "arguments": {"expression": "1/0"}},
                    {"tool": "calculator", "arguments": {"expression": "3+3"}},
                ]
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["aborted"] is True
        assert body["completed"] == 1
        assert len(body["results"]) == 2, "失败即停，不应继续执行后续步骤"
        failure = body["results"][1]
        assert failure["ok"] is False
        assert failure["error"]["code"] == "TOOL_INVALID_ARGUMENTS"
        print(f"[PASS] 计划在第 2 步失败并中止：{failure['error']['message']}")

    def test_plan_over_max_calls_rejected(self, client, monkeypatch):
        from app.services.tools import registry as registry_module

        monkeypatch.setattr(registry_module.settings, "TOOL_MAX_CALLS_PER_REQUEST", 1)
        headers = _register_and_login(client, "tools_plan_limit")
        resp = client.post(
            "/api/tools/run",
            json={
                "calls": [
                    {"tool": "calculator", "arguments": {"expression": "1+1"}},
                    {"tool": "calculator", "arguments": {"expression": "2+2"}},
                ]
            },
            headers=headers,
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == "TOOL_INVALID_ARGUMENTS"
        print(f"[PASS] 超过最大调用次数 → 400：{resp.json()['message']}")

    def test_slow_tool_returns_504(self, client, monkeypatch):
        from app.api import tools as tools_api

        registry = ToolRegistry(timeout=0.05)
        registry.register(_SlowTool())
        monkeypatch.setattr(tools_api, "tool_registry", registry)

        headers = _register_and_login(client, "tools_timeout")
        resp = client.post(
            "/api/tools/slow_probe/invoke",
            json={"arguments": {"seconds": 5}},
            headers=headers,
        )
        assert resp.status_code == 504, resp.text
        body = resp.json()
        assert body["code"] == "TOOL_TIMEOUT"
        assert body.get("request_id"), "504 也必须带 request_id"
        print(f"[PASS] 慢工具 → {body['code']}（{body['message']}）")



class TestFrontendPlannedMarks:
    """审计 §4 改进建议 1：前端页面必须打真实接口，并用文本契约钉住。

    这些断言直接读源码文本（与 ``test_sprint32_production`` 检查 Dockerfile /
    nginx 配置同一种做法）——前端没有 UI 测试框架，用文本契约把"不许再用假数据
    冒充功能"钉住，比截图/人工检查可靠。

    2026-09 更新：Agent 已落地最小真实路径（``agents`` 表 + ``/api/agents`` +
    ``AgentRunner``）；2026-10 更新：Workflow 也已落地（``workflows`` 表 +
    ``/api/workflows`` + ``app/services/workflow``），两个页面都必须是真实页面，
    不再允许 Planned 标注或假数据。
    """

    REPO_ROOT = Path(__file__).resolve().parents[2]

    def _read(self, relative: str) -> str:
        path = self.REPO_ROOT / relative
        assert path.is_file(), f"缺少文件: {relative}"
        return path.read_text(encoding="utf-8")

    def test_workflow_page_uses_real_api(self):
        """Workflow 已实现：页面必须打真实接口，且不得再出现 Planned 标注。"""
        source = self._read("frontend/src/pages/ai/WorkflowManagementPage.tsx")

        assert "PlannedNotice" not in source, "Workflow 已实现，不应再标注 Planned"
        assert "from '../../api/workflows'" in source, "必须使用真实 Workflow 客户端"
        for call in ("listWorkflows", "createWorkflow", "executeWorkflow"):
            assert call in source, f"Workflow 页面缺少真实调用: {call}"

        api_client = self._read("frontend/src/api/workflows.ts")
        assert "apiClient.get('/workflows')" in api_client
        assert "apiClient.post(`/workflows/${workflowId}/execute`" in api_client
        print("[PASS] WorkflowManagementPage 打真实 /api/workflows（CRUD + execute）")

    def test_agent_page_uses_real_api(self):
        """Agent 已实现：页面必须打真实接口，且不得再出现假数据/Planned 标注。"""
        source = self._read("frontend/src/pages/ai/AgentManagementPage.tsx")

        assert "const placeholderAgents" not in source, "假数据必须删除，不能用假数据冒充功能"
        assert "model: 'agnes-2.5-flash'" not in source
        assert "<table" not in source, "假数据表格应整体删除，不要留下空壳表格"
        assert "PlannedNotice" not in source, "Agent 已实现，不应再标注 Planned"

        assert "from '../../api/agents'" in source, "必须使用真实 Agent 客户端"
        for call in ("listAgents", "createAgent", "executeAgent"):
            assert call in source, f"Agent 页面缺少真实调用: {call}"

        api_client = self._read("frontend/src/api/agents.ts")
        assert "apiClient.get('/agents')" in api_client
        assert "apiClient.post(`/agents/${agentId}/execute`" in api_client
        print("[PASS] AgentManagementPage 打真实 /api/agents（CRUD + execute）")

    def test_workflow_shells_are_removed(self):
        """Workflow 的空壳编排器 / 死 store 必须删除（真实页面与客户端已就位）。"""
        for relative in (
            "frontend/src/store/workflow.ts",
            "frontend/src/pages/platform/workflows/WorkflowStudioPage.tsx",
        ):
            assert not (self.REPO_ROOT / relative).exists(), (
                f"{relative} 是会打 404 的空壳编排器残留，禁止重新引入"
            )

        router = self._read("frontend/src/router/index.tsx")
        assert '<Navigate to="/ai/workflows" replace />' in router

        nav = self._read("frontend/src/layout/EnterpriseLayout.tsx")
        assert "'/platform/workflows'" not in nav, (
            "侧边栏不应再直接指向已删除的空壳编排器"
        )
        assert "'/ai/workflows'" in nav, "真实 Workflow 页面必须保留侧边栏入口"
        print("[PASS] Workflow 空壳编排器已删除，旧 URL 改为 redirect，真实页面在架")

    def test_readme_describes_agent_and_workflow_accurately(self):
        readme = self._read("README.md")
        assert "Agents / Workflows：Agent 平台框架 —— ⚠️ **Planned**" not in readme
        assert "Agents：Agent 最小真实路径" in readme, "README 应说明 Agent 已实现"
        assert "Workflows：Workflow 最小真实路径" in readme, (
            "README 应说明 Workflow 已实现（不再标 Planned）"
        )
        assert "Workflows：⚠️ **Planned**" not in readme
        print("[PASS] README 对 Agent / Workflow（均已实现）的措辞一致")

