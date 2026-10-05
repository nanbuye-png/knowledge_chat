"""Workflow 端到端测试 —— 审计 §4（Agent / Workflow / Tools）。

审计原文（改进建议）：

    若实现，只做一个真实场景（KB 检索 + Calculator），必须有 Tool 选择逻辑、
    Tool 超时、最大执行次数、失败处理

本文件打的是**生产代码**：``workflows`` 表（真迁移）+ ``/api/workflows`` 真实路由
+ ``app/services/workflow`` 的执行器 / 模板 / 条件分支 + 与 ``/api/tools``、
Agent 同一份 ToolRegistry。逐条覆盖审计硬要求：

1. 多个步骤 → ``test_runs_steps_in_order``；
2. 条件分支 → ``test_condition_skips_step_with_reason`` /
   ``test_previous_failed_branch_runs_fallback``；
3. 状态 → ``test_step_output_is_passed_to_next_step`` /
   ``test_input_placeholder_is_resolved``；
4. 失败处理 → ``test_on_error_abort_stops_workflow`` /
   ``test_on_error_continue_keeps_going`` / ``test_template_error_is_visible``；
5. 写入口校验 → 未注册工具 / 重复步骤 id / 前向引用 / 超过步骤上限 /
   缺"不能自动取用"的必填参数（`kb_search.knowledge_base_id`，见
   `test_kb_search_step_without_knowledge_base_is_rejected_on_save`）。

KB 检索通过替换 ``kb_search`` 工具实例的 ``_pipeline``（与 ``test_agents.py``
同一注入点）来避免真实向量检索，注册表 / 执行器 / API 全部走生产代码。
"""

import pytest

pytestmark = pytest.mark.usefixtures("no_rate_limits")

PASSWORD = "Str0ng!Passw0rd123"


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


def _create_workflow(client, headers: dict, **payload) -> dict:
    body = {
        "name": payload.pop("name", "测试 Workflow"),
        "steps": payload.pop("steps", [{"id": "calc", "tool": "calculator",
                                        "arguments": {"expression": "1+1"}}]),
        **payload,
    }
    resp = client.post("/api/workflows", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _execute(client, headers: dict, workflow_id: int, text: str):
    return client.post(
        f"/api/workflows/{workflow_id}/execute",
        json={"input": text},
        headers=headers,
    )


class _FakeCitation:
    def to_dict(self) -> dict:
        return {
            "document_id": "doc-1",
            "filename": "手册.pdf",
            "chunk_id": 0,
            "score": 0.9,
        }


class _FakeRetrieval:
    def __init__(self):
        self.sources = [
            {
                "document_id": "doc-1",
                "filename": "手册.pdf",
                "chunk_index": 0,
                "score": 0.91,
                "text": "门诊时间：周一至周五 8:00-17:00",
            }
        ]
        self.results = list(self.sources)
        self.has_results = True
        self.search_query = "门诊时间"
        self.rewrite_status = "skipped"
        self.citations = [_FakeCitation()]


class _FakePipeline:
    def __init__(self, error: Exception | None = None):
        self._error = error
        self.calls: list[dict] = []

    async def retrieve(self, question, knowledge_base_id, top_k=None, **kwargs):
        self.calls.append(
            {"question": question, "kb": knowledge_base_id, "top_k": top_k}
        )
        if self._error is not None:
            raise self._error
        return _FakeRetrieval()


def _patch_kb_search_pipeline(monkeypatch, pipeline) -> None:
    """把检索替身注入生产工具实例（注册表 / 路由 / 执行器都不替换）。"""
    from app.services.tools import tool_registry

    monkeypatch.setattr(tool_registry.get("kb_search"), "_pipeline", pipeline)


class TestWorkflowConfiguration:
    """workflows 表的真实 CRUD（步骤必须指向真实工具与已定义的步骤）。"""

    def test_requires_authentication(self, client):
        assert client.get("/api/workflows").status_code in (401, 403)
        assert client.post(
            "/api/workflows", json={"name": "x", "steps": []}
        ).status_code in (401, 403)
        assert client.get("/api/workflows/limits").status_code in (401, 403)
        print("[PASS] /api/workflows 未登录一律拒绝")

    def test_limits_endpoint_exposes_real_limits(self, client):
        """/limits 暴露真实上限（前端不再硬编码步骤数，也不再收到英文 422）。"""
        from app.core.config import settings
        from app.services.tools import tool_registry

        headers = _register_and_login(client, "wf_limits")
        resp = client.get("/api/workflows/limits", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["max_steps"] == int(settings.WORKFLOW_MAX_STEPS)
        assert body["max_input_chars"] >= 1
        assert body["tools"] == tool_registry.names(), "工具清单必须与注册表一致"
        print(
            f"[PASS] /api/workflows/limits 暴露真实上限"
            f"（max_steps={body['max_steps']}，输入上限 {body['max_input_chars']} 字符）"
        )

    def test_crud_roundtrip(self, client):
        headers = _register_and_login(client, "wf_crud")
        kb_id = _create_kb(client, headers, "CRUD 库")

        created = _create_workflow(
            client,
            headers,
            name="门诊流程",
            description="检索 + 计算",
            steps=[
                {
                    "id": "search",
                    "tool": "kb_search",
                    "arguments": {"query": "{{input}}", "knowledge_base_id": kb_id},
                },
                {
                    "id": "calc",
                    "tool": "calculator",
                    "arguments": {"expression": "2*3"},
                    "when": "previous_succeeded",
                    "on_error": "continue",
                },
            ],
        )
        assert created["id"] > 0
        assert [s["id"] for s in created["steps"]] == ["search", "calc"]
        assert created["steps"][1]["when"] == "previous_succeeded"
        assert created["steps"][1]["on_error"] == "continue"
        assert created["enabled"] is True

        listed = client.get("/api/workflows", headers=headers)
        assert listed.status_code == 200, listed.text
        assert [w["id"] for w in listed.json()] == [created["id"]]

        fetched = client.get(f"/api/workflows/{created['id']}", headers=headers)
        assert fetched.status_code == 200
        assert fetched.json()["name"] == "门诊流程"

        updated = client.patch(
            f"/api/workflows/{created['id']}",
            json={"name": "门诊流程 v2", "enabled": False},
            headers=headers,
        )
        assert updated.status_code == 200, updated.text
        body = updated.json()
        assert body["name"] == "门诊流程 v2"
        assert body["enabled"] is False
        assert len(body["steps"]) == 2, "未给出的字段不应被清空"

        deleted = client.delete(f"/api/workflows/{created['id']}", headers=headers)
        assert deleted.status_code == 204, deleted.text
        assert client.get(
            f"/api/workflows/{created['id']}", headers=headers
        ).status_code == 404
        assert client.get("/api/workflows", headers=headers).json() == []
        print("[PASS] Workflow CRUD 全链路（创建/列表/详情/更新/删除）")

    def test_rejects_unknown_tool(self, client):
        headers = _register_and_login(client, "wf_bad_tool")
        resp = client.post(
            "/api/workflows",
            json={
                "name": "假工具",
                "steps": [{"id": "s1", "tool": "web_search", "arguments": {}}],
            },
            headers=headers,
        )
        assert resp.status_code == 400, resp.text
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert "未注册的工具" in body["message"]
        assert "kb_search" in body["message"], "错误信息应给出可用工具"
        print(f"[PASS] 步骤使用未注册工具被拒绝：{body['message']}")

    def test_rejects_duplicate_step_ids(self, client):
        headers = _register_and_login(client, "wf_dup_id")
        resp = client.post(
            "/api/workflows",
            json={
                "name": "重复 id",
                "steps": [
                    {"id": "same", "tool": "calculator",
                     "arguments": {"expression": "1+1"}},
                    {"id": "same", "tool": "calculator",
                     "arguments": {"expression": "2+2"}},
                ],
            },
            headers=headers,
        )
        assert resp.status_code == 400, resp.text
        assert "步骤 id 重复" in resp.json()["message"]
        print("[PASS] 重复步骤 id 被拒绝")

    def test_rejects_forward_reference(self, client):
        """引用后面的步骤 = 运行时必然取不到值，创建时就该拒绝。"""
        headers = _register_and_login(client, "wf_forward_ref")
        resp = client.post(
            "/api/workflows",
            json={
                "name": "前向引用",
                "steps": [
                    {
                        "id": "first",
                        "tool": "calculator",
                        "arguments": {"expression": "{{steps.second.output.result}}"},
                    },
                    {"id": "second", "tool": "calculator",
                     "arguments": {"expression": "1+1"}},
                ],
            },
            headers=headers,
        )
        assert resp.status_code == 400, resp.text
        assert "尚未定义的步骤: second" in resp.json()["message"]
        print("[PASS] 前向引用被创建时拦截（不等到执行才炸）")

    def test_rejects_over_max_steps(self, client):
        from app.core.config import settings

        headers = _register_and_login(client, "wf_too_many")
        steps = [
            {"id": f"s{i}", "tool": "calculator", "arguments": {"expression": f"{i}+1"}}
            for i in range(int(settings.WORKFLOW_MAX_STEPS) + 1)
        ]
        resp = client.post(
            "/api/workflows", json={"name": "超长", "steps": steps}, headers=headers
        )
        assert resp.status_code == 422, resp.text
        print(f"[PASS] 超过 {settings.WORKFLOW_MAX_STEPS} 步被拒绝（422）")

    def test_other_user_cannot_touch_workflow(self, client):
        owner = _register_and_login(client, "wf_owner")
        workflow = _create_workflow(client, owner, name="私有流程")
        intruder = _register_and_login(client, "wf_intruder")

        assert client.get(
            f"/api/workflows/{workflow['id']}", headers=intruder
        ).status_code == 404
        assert client.put(
            f"/api/workflows/{workflow['id']}", json={"name": "改名"}, headers=intruder
        ).status_code == 404
        assert client.delete(
            f"/api/workflows/{workflow['id']}", headers=intruder
        ).status_code == 404
        assert _execute(client, intruder, workflow["id"], "1+1").status_code == 404
        assert client.get(
            f"/api/workflows/{workflow['id']}", headers=owner
        ).status_code == 200
        print("[PASS] 非本人访问一律 404（不区分不存在与越权）")


class TestWorkflowExecution:
    """真实执行：有序步骤 + 条件分支 + 状态传递 + 失败处理。"""

    def test_runs_steps_in_order_and_carries_state(self, client):
        headers = _register_and_login(client, "wf_exec_state")
        workflow = _create_workflow(
            client,
            headers,
            name="两步计算",
            steps=[
                {"id": "first", "tool": "calculator",
                 "arguments": {"expression": "6*7"}},
                {
                    "id": "second",
                    "tool": "calculator",
                    "arguments": {"expression": "{{steps.first.output.result}} + 8"},
                },
            ],
        )

        resp = _execute(client, headers, workflow["id"], "任意输入")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert [s["id"] for s in body["steps"]] == ["first", "second"]
        assert body["steps"][0]["output"]["result"] == 42
        assert body["steps"][1]["output"]["expression"] == "42 + 8"
        assert body["steps"][1]["output"]["result"] == 50, "第二步必须吃到第一步的输出"
        assert body["completed"] == 2 and body["skipped"] == 0
        assert body["aborted"] is False and body["aborted_at"] is None
        assert body["warnings"] == []
        print("[PASS] 多步骤按序执行，且前置输出通过 {{steps.*}} 传给后置步骤")

    def test_input_placeholder_is_resolved(self, client):
        headers = _register_and_login(client, "wf_exec_input")
        workflow = _create_workflow(
            client,
            headers,
            name="输入计算",
            steps=[
                {"id": "calc", "tool": "calculator",
                 "arguments": {"expression": "{{input}}"}}
            ],
        )

        resp = _execute(client, headers, workflow["id"], "6*7")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["input"] == "6*7"
        assert body["steps"][0]["output"]["result"] == 42
        print("[PASS] {{input}} 被解析为本次执行的输入")

    def test_calculator_step_without_expression_uses_input(self, client):
        """漏填 expression 的 calculator 步骤：按同一套规则从输入取，补齐写进 warnings。"""
        headers = _register_and_login(client, "wf_exec_default")
        workflow = _create_workflow(
            client,
            headers,
            name="漏填参数",
            steps=[{"id": "step1", "tool": "calculator", "arguments": {}}],
        )

        body = _execute(client, headers, workflow["id"], "1+2是多少").json()
        assert body["aborted"] is False, body
        assert body["steps"][0]["ok"] is True, body["steps"]
        assert body["steps"][0]["output"]["result"] == 3
        assert any("自动取用" in w for w in body["warnings"]), body["warnings"]

        missed = _execute(client, headers, workflow["id"], "门诊时间是什么时候").json()
        assert missed["steps"][0]["ok"] is False
        assert missed["steps"][0]["error"]["code"] == "TOOL_INVALID_ARGUMENTS"
        assert any(
            "expression" in w and "{{input}}" in w for w in missed["warnings"]
        ), missed["warnings"]
        print("[PASS] calculator 步骤漏填 expression：能自动取就取，取不到给出可执行提示")

    def test_input_placeholder_accepts_natural_language_question(self, client):
        """``{{input}}`` 拿到问句（1+2是多少）也能算 —— 与 input_is_math 同一套规则。"""
        headers = _register_and_login(client, "wf_exec_nl")
        workflow = _create_workflow(
            client,
            headers,
            name="问句计算",
            steps=[
                {
                    "id": "calc",
                    "tool": "calculator",
                    "arguments": {"expression": "{{input}}"},
                    "when": "input_is_math",
                }
            ],
        )

        body = _execute(client, headers, workflow["id"], "1+2是多少").json()
        assert body["steps"][0]["skipped"] is False, body["steps"]
        assert body["steps"][0]["output"]["result"] == 3
        assert body["steps"][0]["output"]["input_expression"] == "1+2是多少"
        print("[PASS] 问句「1+2是多少」在 Workflow 里算得出来（条件与取值同一套规则）")

    def test_condition_skips_step_with_reason(self, client):
        headers = _register_and_login(client, "wf_exec_cond")
        workflow = _create_workflow(
            client,
            headers,
            name="数学条件",
            steps=[
                {
                    "id": "calc",
                    "tool": "calculator",
                    "arguments": {"expression": "{{input}}"},
                    "when": "input_is_math",
                }
            ],
        )

        skipped = _execute(client, headers, workflow["id"], "门诊时间是什么时候").json()
        assert skipped["skipped"] == 1 and skipped["completed"] == 0
        assert skipped["steps"][0]["skipped"] is True
        assert "input_is_math" in skipped["steps"][0]["skip_reason"]
        assert any("已跳过" in w for w in skipped["warnings"]), skipped["warnings"]

        ran = _execute(client, headers, workflow["id"], "1+1").json()
        assert ran["skipped"] == 0 and ran["steps"][0]["output"]["result"] == 2
        print("[PASS] 条件分支：不满足即跳过并给出 skip_reason（不静默跳过）")

    def test_previous_failed_branch_runs_fallback(self, client):
        headers = _register_and_login(client, "wf_exec_fallback")
        workflow = _create_workflow(
            client,
            headers,
            name="失败兜底",
            steps=[
                {
                    "id": "bad",
                    "tool": "calculator",
                    "arguments": {"expression": "1/0"},
                    "on_error": "continue",
                },
                {
                    "id": "fallback",
                    "tool": "calculator",
                    "arguments": {"expression": "1+1"},
                    "when": "previous_failed",
                },
            ],
        )

        body = _execute(client, headers, workflow["id"], "1").json()
        assert body["steps"][0]["ok"] is False
        assert body["steps"][0]["error"]["code"] == "TOOL_INVALID_ARGUMENTS"
        assert body["steps"][1]["ok"] is True
        assert body["steps"][1]["output"]["result"] == 2
        assert body["aborted"] is False, "on_error=continue 不应中止流程"
        assert body["completed"] == 1
        assert any("失败" in w for w in body["warnings"]), body["warnings"]
        print("[PASS] on_error=continue + previous_failed 兜底分支真实执行")

    def test_on_error_abort_stops_workflow(self, client):
        headers = _register_and_login(client, "wf_exec_abort")
        workflow = _create_workflow(
            client,
            headers,
            name="失败即停",
            steps=[
                {"id": "bad", "tool": "calculator",
                 "arguments": {"expression": "1/0"}},
                {"id": "never", "tool": "calculator",
                 "arguments": {"expression": "1+1"}},
            ],
        )

        body = _execute(client, headers, workflow["id"], "1").json()
        assert len(body["steps"]) == 1, "abort 后不得继续执行后续步骤"
        assert body["aborted"] is True
        assert body["aborted_at"] == "bad"
        assert body["steps"][0]["error"]["code"] == "TOOL_INVALID_ARGUMENTS"
        assert any("失败" in w for w in body["warnings"])
        print("[PASS] 单步失败（on_error=abort）中止整条流程并记录 aborted_at")

    def test_template_error_is_visible_not_swallowed(self, client):
        headers = _register_and_login(client, "wf_exec_tpl")
        workflow = _create_workflow(
            client,
            headers,
            name="坏引用",
            steps=[
                {"id": "first", "tool": "calculator",
                 "arguments": {"expression": "1+1"}},
                {
                    "id": "second",
                    "tool": "calculator",
                    "arguments": {"expression": "{{steps.first.output.missing}}"},
                },
            ],
        )

        body = _execute(client, headers, workflow["id"], "1").json()
        assert body["steps"][1]["ok"] is False
        assert body["steps"][1]["error"]["code"] == "WORKFLOW_TEMPLATE_ERROR"
        assert "字段不存在" in body["steps"][1]["error"]["message"]
        assert body["aborted"] is True and body["aborted_at"] == "second"
        print("[PASS] 模板引用错误不会被吞掉（WORKFLOW_TEMPLATE_ERROR 可见）")

    def test_reference_to_skipped_step_is_reported(self, client):
        headers = _register_and_login(client, "wf_exec_skipref")
        workflow = _create_workflow(
            client,
            headers,
            name="跳过引用",
            steps=[
                {
                    "id": "first",
                    "tool": "calculator",
                    "arguments": {"expression": "9"},
                    "when": "input_is_math",
                },
                {
                    "id": "second",
                    "tool": "calculator",
                    "arguments": {"expression": "{{steps.first.output.result}}"},
                },
            ],
        )

        body = _execute(client, headers, workflow["id"], "你好").json()
        assert body["steps"][0]["skipped"] is True
        assert body["steps"][1]["error"]["code"] == "WORKFLOW_TEMPLATE_ERROR"
        assert "被条件跳过" in body["steps"][1]["error"]["message"]
        print("[PASS] 引用被跳过的步骤时给出明确原因（而不是 None 或空串）")

    def test_disabled_workflow_returns_409(self, client):
        headers = _register_and_login(client, "wf_disabled")
        workflow = _create_workflow(client, headers, name="已禁用", enabled=False)
        resp = _execute(client, headers, workflow["id"], "1+1")
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "WORKFLOW_DISABLED"
        print("[PASS] 禁用的 Workflow 执行返回 409（不是空结果）")

    def test_kb_search_step_uses_owned_knowledge_base(self, client, monkeypatch):
        headers = _register_and_login(client, "wf_kb_owner")
        kb_id = _create_kb(client, headers, "流程库")
        workflow = _create_workflow(
            client,
            headers,
            name="检索流程",
            steps=[
                {
                    "id": "search",
                    "tool": "kb_search",
                    "arguments": {"query": "{{input}}", "knowledge_base_id": kb_id},
                }
            ],
        )
        pipeline = _FakePipeline()
        _patch_kb_search_pipeline(monkeypatch, pipeline)

        body = _execute(client, headers, workflow["id"], "门诊时间是什么时候").json()
        assert body["steps"][0]["ok"] is True
        assert body["steps"][0]["output"]["snippets"][0]["content"].startswith(
            "门诊时间"
        )
        assert body["steps"][0]["output"]["citations"][0]["filename"] == "手册.pdf"
        assert pipeline.calls == [
            {"question": "门诊时间是什么时候", "kb": kb_id, "top_k": 5}
        ]
        print("[PASS] Workflow 的 kb_search 步骤走真实检索链路（含知识库归属校验）")

    def test_kb_search_step_denies_other_users_knowledge_base(self, client):
        owner = _register_and_login(client, "wf_kb_victim")
        victim_kb = _create_kb(client, owner, "别人的库")
        intruder = _register_and_login(client, "wf_kb_intruder")
        workflow = _create_workflow(
            client,
            intruder,
            name="越权检索",
            steps=[
                {
                    "id": "search",
                    "tool": "kb_search",
                    "arguments": {"query": "门诊", "knowledge_base_id": victim_kb},
                }
            ],
        )

        body = _execute(client, intruder, workflow["id"], "门诊").json()
        assert body["steps"][0]["ok"] is False
        assert body["steps"][0]["error"]["code"] == "TOOL_PERMISSION_DENIED"
        assert body["aborted"] is True
        print("[PASS] Workflow 不能成为绕过知识库归属校验的越权入口")

    def test_kb_search_step_without_knowledge_base_is_rejected_on_save(self, client):
        """kb_search 缺 knowledge_base_id：保存时 400 —— 不让"存进去也必然失败"的编排进库。

        回归背景：页面此前按扁平结构读工具 Schema（`parameters[名字]` 而实际是
        `parameters.properties[名字]`），于是新步骤的参数永远是 `{}`；calculator 靠执行器
        补齐 `expression` 蒙混过关，kb_search 则只能等执行时才抛
        `TOOL_INVALID_ARGUMENTS: 缺少必填参数: query`。现在写入口直接把话说清楚。
        """
        headers = _register_and_login(client, "wf_kb_missing")
        resp = client.post(
            "/api/workflows",
            json={
                "name": "缺知识库",
                "steps": [{"id": "search", "tool": "kb_search", "arguments": {}}],
            },
            headers=headers,
        )
        assert resp.status_code == 400, resp.text
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert "knowledge_base_id" in body["message"]
        assert "query" in body["message"], (
            "错误信息应说明 query 可以省略（执行时按本次输入取用），只有知识库必须写"
        )
        print("[PASS] kb_search 缺 knowledge_base_id：保存即 400 并给出照做的写法")

    def test_kb_search_query_missing_is_filled_from_input(self, client, monkeypatch):
        """只写了 knowledge_base_id 的 kb_search 步骤：query 按本次输入自动取用（不静默）。"""
        headers = _register_and_login(client, "wf_kb_query_default")
        kb_id = _create_kb(client, headers, "流程库2")
        workflow = _create_workflow(
            client,
            headers,
            name="只给知识库的检索",
            steps=[
                {
                    "id": "search",
                    "tool": "kb_search",
                    "arguments": {"knowledge_base_id": kb_id},
                }
            ],
        )
        pipeline = _FakePipeline()
        _patch_kb_search_pipeline(monkeypatch, pipeline)

        body = _execute(client, headers, workflow["id"], "门诊时间是什么时候").json()
        assert body["steps"][0]["ok"] is True, body
        assert pipeline.calls == [
            {"question": "门诊时间是什么时候", "kb": kb_id, "top_k": 5}
        ], "query 缺失时应取用本次输入（与 Agent 规划器同一约定）"
        assert any("query" in warning for warning in body["warnings"]), (
            "自动取用不静默：必须出现在 warnings 里"
        )
        print("[PASS] kb_search 缺 query：按本次输入自动取用，并如实写进 warnings")

    def test_execute_writes_audit_log(self, client, temp_db):
        import asyncio

        from sqlalchemy import select

        from app.models.audit_log import AuditLog

        headers = _register_and_login(client, "wf_audit")
        workflow = _create_workflow(client, headers, name="审计流程")
        assert _execute(client, headers, workflow["id"], "1+1").status_code == 200

        async def _fetch():
            async with temp_db.session() as db:
                result = await db.execute(
                    select(AuditLog).where(
                        AuditLog.action == "WORKFLOW_EXECUTE",
                        AuditLog.target_id == workflow["id"],
                    )
                )
                return [(row.target_type, row.status) for row in result.scalars().all()]

        rows = asyncio.run(_fetch())
        assert rows == [("workflow", "SUCCESS")], rows
        print("[PASS] 执行写入审计日志（WORKFLOW_EXECUTE / SUCCESS）")


class TestWorkflowTemplating:
    """模板解析 / 条件判断的纯单元断言（不含 HTTP）。"""

    _STATE = {
        "input": "6*7",
        "steps": {
            "calc": {
                "ok": True,
                "output": {"result": 42, "items": [{"name": "a"}]},
                "error": None,
                "skipped": False,
            }
        },
    }

    def test_resolve_value_preserves_type_and_walks_paths(self):
        from app.services.workflow import resolve_value

        state = self._STATE
        assert resolve_value("{{input}}", state) == "6*7"
        assert resolve_value("{{steps.calc.output.result}}", state) == 42, (
            "整个参数就是一个占位符时必须保留原始类型（int 仍是 int）"
        )
        assert resolve_value("结果: {{steps.calc.output.result}}", state) == "结果: 42"
        assert resolve_value("{{steps.calc.output.items.0.name}}", state) == "a"
        assert resolve_value("{{steps.calc.ok}}", state) is True
        assert resolve_value(7, state) == 7
        assert resolve_value({"a": ["{{input}}"]}, state) == {"a": ["6*7"]}
        print("[PASS] 占位符解析：类型保留 / 点号路径 / 数组下标 / 嵌套结构")

    def test_resolve_value_rejects_unknown_references(self):
        from app.services.workflow import TemplateError, resolve_value

        state = {"input": "x", "steps": {}}
        with pytest.raises(TemplateError):
            resolve_value("{{steps.nope.output.result}}", state)
        with pytest.raises(TemplateError):
            resolve_value("{{query}}", state)
        with pytest.raises(TemplateError):
            resolve_value("{{steps.a.output.result}}", state)
        print("[PASS] 未知引用一律报错（不原样透传给工具）")

    def test_known_step_references_flags_forward_and_unknown(self):
        from app.services.workflow import known_step_references

        assert (
            known_step_references(
                [
                    {"id": "a", "arguments": {"expression": "{{input}}"}},
                    {"id": "b", "arguments": {"expression": "{{steps.a.output.result}}"}},
                ]
            )
            == []
        )

        problems = known_step_references(
            [
                {"id": "a", "arguments": {"expression": "{{steps.b.output.result}}"}},
                {"id": "b", "arguments": {}},
            ]
        )
        assert problems and "尚未定义" in problems[0]
        print("[PASS] 创建期引用校验：前向引用 / 未知步骤被拦截")

    def test_apply_argument_defaults_matrix(self):
        """参数补齐只做"只有一个明确答案"的事，且如实回报（不静默）。"""
        from app.services.workflow import apply_argument_defaults

        # calculator：从输入里取数学表达式（与 Agent 规划器同一套规则）
        filled, warning = apply_argument_defaults("calculator", {}, "1+2是多少")
        assert filled == {"expression": "1+2"}
        assert warning and "1+2" in warning

        # 空白字符串等同于缺失
        filled, warning = apply_argument_defaults(
            "calculator", {"expression": "   "}, "1+2是多少"
        )
        assert filled == {"expression": "1+2"} and warning

        # 显式写了就不动
        kept, warning = apply_argument_defaults("calculator", {"expression": "6*7"}, "1+2")
        assert kept == {"expression": "6*7"} and warning is None

        # 输入不是数学表达式：不改参数，只给出一条能照做的提示
        empty, warning = apply_argument_defaults("calculator", {}, "门诊时间")
        assert empty == {} and warning and "expression" in warning and "{{input}}" in warning

        # 类型写错时交给工具层按契约报错，这里不自作主张
        assert apply_argument_defaults("calculator", {"expression": 3}, "1+2") == (
            {"expression": 3},
            None,
        )

        # kb_search 的 query 与 calculator 的 expression 是同一类参数（"要的就是本次输入"），
        # 必须同口径：否则同一个页面上"calculator 留空能跑通、kb_search 留空必失败"
        filled, warning = apply_argument_defaults("kb_search", {}, "门诊时间是什么时候")
        assert filled == {"query": "门诊时间是什么时候"}, (
            "kb_search.query 缺失时应原样取用本次输入"
        )
        assert warning and "query" in warning and "knowledge_base_id" in warning
        assert "GET /api/knowledge-bases" in warning, (
            "knowledge_base_id 不能猜，但提示必须给出\"去哪查 ID\""
        )
        assert "knowledge_base_id" not in filled

        # 参数齐全时不做任何改动，也不产生 warning
        kept, warning = apply_argument_defaults(
            "kb_search", {"query": "门诊", "knowledge_base_id": 1}, "无关输入"
        )
        assert kept == {"query": "门诊", "knowledge_base_id": 1} and warning is None

        # query 写成非字符串：不猜，交给工具层按契约报类型错误
        kept, warning = apply_argument_defaults(
            "kb_search", {"query": 123, "knowledge_base_id": 1}, "门诊"
        )
        assert kept == {"query": 123, "knowledge_base_id": 1} and warning is None

        # 未知工具一律不猜
        assert apply_argument_defaults("no_such_tool", {}, "1+2是多少") == ({}, None)
        print("[PASS] 参数补齐矩阵：calculator / kb_search 同口径，knowledge_base_id 只提示不猜")

    def test_evaluate_condition_matrix(self):
        from app.services.workflow import evaluate_condition

        assert evaluate_condition("always", None, "你好") == (True, None)

        ok, reason = evaluate_condition("previous_succeeded", None, "你好")
        assert ok is False and "没有前置步骤" in reason

        previous_ok = {"id": "a", "ok": True}
        previous_fail = {"id": "a", "ok": False}
        assert evaluate_condition("previous_succeeded", previous_ok, "x")[0] is True
        assert evaluate_condition("previous_succeeded", previous_fail, "x")[0] is False
        assert evaluate_condition("previous_failed", previous_fail, "x")[0] is True
        assert evaluate_condition("previous_failed", previous_ok, "x")[0] is False

        assert evaluate_condition("input_is_math", None, "1+1")[0] is True
        skipped, reason = evaluate_condition("input_is_math", None, "门诊时间")
        assert skipped is False and "input_is_math" in reason
        print("[PASS] 条件分支判定矩阵（always / previous_* / input_is_math）")

