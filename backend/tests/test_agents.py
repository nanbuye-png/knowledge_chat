"""Agent 端到端测试 —— 审计 §4（Agent / Workflow / Tools）。

审计原文（改进建议）：

    若实现，只做一个真实场景（KB 检索 + Calculator），必须有 Tool 选择逻辑、
    Tool 超时、最大执行次数、失败处理

本文件打的是**生产代码**：``agents`` 表（真迁移）+ ``/api/agents`` 真实路由 +
``app/services/agent`` 的规划器/执行器 + 与 ``/api/tools`` 同一份 ToolRegistry。
逐条覆盖审计四条硬要求：

1. Tool 选择逻辑 → 规划器只选"输入确实需要"的工具（``TestAgentPlanning``）；
2. Tool 超时 → 由工具层 ``asyncio.wait_for`` 兜底（``tool_registry`` 单测见
   ``test_tools.py``；本文件覆盖"失败即停 + 轨迹可见"）；
3. 最大执行次数 → ``agent.max_tool_calls`` 与 ``TOOL_MAX_CALLS_PER_REQUEST`` 取小，
   超出部分进 ``warnings``（``test_plan_respects_agent_max_tool_calls``）；
4. 失败处理 → 工具失败 200 + ``steps[].error`` + ``warnings``（不吞、不泄漏），
   未启用 409、无能力 400、LLM 故障 502。

LLM 路径通过替换 ``app.services.agent.runner._build_provider`` 注入替身，
**不**替换执行器本身，也不发起真实网络调用。
"""

import asyncio

import pytest

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


def _create_agent(client, headers: dict, **payload) -> dict:
    body = {"name": payload.pop("name", "测试 Agent"), "tools": [], **payload}
    resp = client.post("/api/agents", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _add_llm_model(
    temp_db,
    name: str = "测试模型",
    provider: str = "agens",
    model_name: str = "agnes-2.5-flash",
    enabled: bool = True,
) -> int:
    """直接写入 ``llm_models``（管理端接口只对 ADMIN 开放，测试用真实 SQL 建行）。"""
    from app.models.llm_model import LLMModel

    async def scenario() -> int:
        async with temp_db.session() as db:
            model = LLMModel(
                name=name, provider=provider, model_name=model_name, enabled=enabled
            )
            db.add(model)
            await db.commit()
            await db.refresh(model)
            return model.id

    return asyncio.run(scenario())



class _FakeCitation:
    def to_dict(self) -> dict:
        return {
            "document_id": "doc-1",
            "filename": "手册.pdf",
            "chunk_id": 0,
            "score": 0.9,
        }


class _FakeRetrieval:
    """检索链路替身（只替检索，不替工具本身）。"""

    def __init__(self, sources=None, has_results=True):
        self.sources = sources if sources is not None else [
            {
                "document_id": "doc-1",
                "filename": "手册.pdf",
                "chunk_index": 0,
                "score": 0.91,
                "text": "门诊时间：周一至周五 8:00-17:00",
            },
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
        self.calls.append(
            {"question": question, "kb": knowledge_base_id, "top_k": top_k}
        )
        if self._error is not None:
            raise self._error
        return self._result


def _patch_kb_search_pipeline(monkeypatch, pipeline) -> None:
    """把检索替身注入生产工具实例（注册表/路由/执行器都不替换）。"""
    from app.services.tools import tool_registry

    monkeypatch.setattr(tool_registry.get("kb_search"), "_pipeline", pipeline)


class _FakeProvider:
    """LLM 替身：记录 messages，返回固定文本或抛异常。"""

    def __init__(
        self,
        reply: str = "根据知识库，门诊时间是周一至周五 8:00-17:00。",
        error: Exception | None = None,
    ):
        self.reply = reply
        self.error = error
        self.calls: list[list[dict]] = []

    async def chat(self, messages, stream: bool = False, **kwargs):
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return self.reply


def _patch_provider(monkeypatch, provider) -> None:
    """替换 Provider 构造（唯一注入点），执行器/API 全部走生产代码。"""
    from app.services.agent import runner as runner_module

    monkeypatch.setattr(
        runner_module, "_build_provider", lambda model, settings_obj: provider
    )



class TestAgentConfiguration:
    """agents 表的真实 CRUD（配置项必须指向真实资源）。"""

    def test_requires_authentication(self, client):
        assert client.get("/api/agents").status_code in (401, 403)
        assert client.post("/api/agents", json={"name": "x"}).status_code in (401, 403)
        print("[PASS] /api/agents 未登录一律拒绝")

    def test_crud_roundtrip(self, client):
        headers = _register_and_login(client, "agents_crud")
        kb_id = _create_kb(client, headers, "CRUD 库")

        created = _create_agent(
            client,
            headers,
            name="门诊助手",
            description="回答门诊时间",
            system_prompt="只回答门诊相关问题",
            knowledge_base_id=kb_id,
            tools=["kb_search", "calculator", "kb_search"],
            max_tool_calls=2,
        )
        assert created["id"] > 0
        assert created["knowledge_base_id"] == kb_id
        assert created["tools"] == ["kb_search", "calculator"], "工具名必须去重"
        assert created["enabled"] is True
        assert created["max_tool_calls"] == 2

        listed = client.get("/api/agents", headers=headers)
        assert listed.status_code == 200, listed.text
        assert [a["id"] for a in listed.json()] == [created["id"]]

        fetched = client.get(f"/api/agents/{created['id']}", headers=headers)
        assert fetched.status_code == 200
        assert fetched.json()["name"] == "门诊助手"

        updated = client.put(
            f"/api/agents/{created['id']}",
            json={"name": "门诊助手 v2", "enabled": False, "tools": ["calculator"]},
            headers=headers,
        )
        assert updated.status_code == 200, updated.text
        body = updated.json()
        assert body["name"] == "门诊助手 v2"
        assert body["enabled"] is False
        assert body["tools"] == ["calculator"]
        assert body["knowledge_base_id"] == kb_id, "未给出的字段不应被清空"

        deleted = client.delete(f"/api/agents/{created['id']}", headers=headers)
        assert deleted.status_code == 204, deleted.text
        assert (
            client.get(f"/api/agents/{created['id']}", headers=headers).status_code == 404
        )
        assert client.get("/api/agents", headers=headers).json() == []
        print("[PASS] Agent CRUD 全链路（创建/列表/详情/更新/删除）")

    def test_rejects_unknown_tool(self, client):
        headers = _register_and_login(client, "agents_bad_tool")
        resp = client.post(
            "/api/agents",
            json={"name": "假工具", "tools": ["web_search"]},
            headers=headers,
        )
        assert resp.status_code == 400, resp.text
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert "未注册的工具" in body["message"]
        assert "kb_search" in body["message"], "错误信息应给出可用工具"
        print(f"[PASS] 未注册工具被拒绝：{body['message']}")

    def test_rejects_other_users_knowledge_base(self, client):
        owner = _register_and_login(client, "agents_kb_owner")
        kb_id = _create_kb(client, owner, "别人的库")
        intruder = _register_and_login(client, "agents_kb_intruder")

        resp = client.post(
            "/api/agents",
            json={"name": "越权", "knowledge_base_id": kb_id, "tools": ["kb_search"]},
            headers=intruder,
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["message"] == "知识库不存在或无权访问"
        print("[PASS] 绑定他人知识库被拒绝（400）")

    def test_rejects_bogus_model_and_over_limit(self, client):
        headers = _register_and_login(client, "agents_bad_model")

        bogus = client.post(
            "/api/agents", json={"name": "缺模型", "model_id": 999999}, headers=headers
        )
        assert bogus.status_code == 400, bogus.text
        assert bogus.json()["message"] == "LLM 模型不存在或未启用"

        from app.core.config import settings

        too_many = client.post(
            "/api/agents",
            json={
                "name": "超限",
                "max_tool_calls": int(settings.TOOL_MAX_CALLS_PER_REQUEST) + 1,
            },
            headers=headers,
        )
        assert too_many.status_code == 400, too_many.text
        assert "max_tool_calls" in too_many.json()["message"]
        print("[PASS] 假模型 / 超上限 max_tool_calls 均被拒绝")

    def test_other_user_cannot_touch_agent(self, client):
        owner = _register_and_login(client, "agents_owner")
        agent = _create_agent(client, owner, name="私有 Agent", tools=["calculator"])
        intruder = _register_and_login(client, "agents_intruder")

        assert (
            client.get(f"/api/agents/{agent['id']}", headers=intruder).status_code == 404
        )
        assert (
            client.put(
                f"/api/agents/{agent['id']}", json={"name": "改名"}, headers=intruder
            ).status_code
            == 404
        )
        assert (
            client.delete(
                f"/api/agents/{agent['id']}", headers=intruder
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/agents/{agent['id']}/execute",
                json={"query": "1+1"},
                headers=intruder,
            ).status_code
            == 404
        )
        assert (
            client.get(f"/api/agents/{agent['id']}", headers=owner).status_code == 200
        )
        print("[PASS] 非本人访问一律 404（不区分不存在与越权）")


class TestAgentPlanning:
    """审计要求 1：Tool 选择逻辑（确定性规则，不依赖 LLM / function calling）。"""

    @pytest.mark.parametrize(
        "query, expected",
        [
            ("计算 (1+2)*3", "(1+2)*3"),
            ("请计算 100/4", "100/4"),
            ("1+1=?", "1+1"),
            ("sqrt(16) + pi", "sqrt(16) + pi"),
            ("What is 12 * 12", "12 * 12"),
        ],
    )
    def test_extracts_math_expression(self, query, expected):
        from app.services.agent import extract_math_expression

        assert extract_math_expression(query) == expected

    @pytest.mark.parametrize(
        "query",
        [
            "门诊时间是什么时候",
            "1+1 等于多少",
            "第 2026 年的营收",
            "SELECT * FROM users",
            "3 天内回复我",
            "2026",
        ],
    )
    def test_non_math_input_is_not_routed_to_calculator(self, query):
        from app.services.agent import extract_math_expression

        assert extract_math_expression(query) is None, f"{query!r} 不应被当成表达式"

    def test_plan_orders_kb_then_calculator(self):
        from types import SimpleNamespace

        from app.services.agent import build_plan
        from app.services.tools import tool_registry

        agent = SimpleNamespace(
            tools=["calculator", "kb_search"], knowledge_base_id=7, max_tool_calls=3
        )
        calls, warnings, available = build_plan(agent, "计算 2+3", tool_registry)

        assert [call["tool"] for call in calls] == ["kb_search", "calculator"]
        assert calls[0]["arguments"]["knowledge_base_id"] == 7
        assert sorted(available) == ["calculator", "kb_search"]
        assert warnings == []

    def test_plan_respects_agent_max_tool_calls(self):
        """审计要求 3：次数上限（取 agent 与全局配置的较小值），且不静默丢步。"""
        from types import SimpleNamespace

        from app.services.agent import build_plan
        from app.services.tools import tool_registry

        agent = SimpleNamespace(
            tools=["kb_search", "calculator"], knowledge_base_id=7, max_tool_calls=1
        )
        calls, warnings, _ = build_plan(agent, "计算 2+3", tool_registry)

        assert [call["tool"] for call in calls] == ["kb_search"]
        assert any("已丢弃" in warning for warning in warnings), warnings

    def test_plan_ignores_unregistered_tools_and_unbound_kb(self):
        from types import SimpleNamespace

        from app.services.agent import build_plan
        from app.services.tools import tool_registry

        unregistered = SimpleNamespace(
            tools=["web_search", "calculator"], knowledge_base_id=None, max_tool_calls=3
        )
        calls, warnings, available = build_plan(
            unregistered, "门诊时间", tool_registry
        )
        assert calls == [], "无知识库且非数学输入 → 不产生调用"
        assert available == ["calculator"], "未注册的工具不应算作可用"
        assert any("未在注册表中注册" in warning for warning in warnings)

        no_math = SimpleNamespace(
            tools=["kb_search", "calculator"], knowledge_base_id=7, max_tool_calls=3
        )
        calls, _, _ = build_plan(no_math, "门诊时间是什么时候", tool_registry)
        assert [call["tool"] for call in calls] == ["kb_search"]


class TestAgentExecution:
    """真实执行：规划 → 受限执行 → 汇总（无模型时如实标注 tools_only）。"""

    def test_tools_only_answers_from_knowledge_base(self, client, monkeypatch):
        headers = _register_and_login(client, "agents_exec_kb")
        kb_id = _create_kb(client, headers, "执行库")
        agent = _create_agent(
            client,
            headers,
            name="检索 Agent",
            knowledge_base_id=kb_id,
            tools=["kb_search"],
        )
        pipeline = _FakePipeline()
        _patch_kb_search_pipeline(monkeypatch, pipeline)

        resp = client.post(
            f"/api/agents/{agent['id']}/execute",
            json={"query": "门诊时间是什么时候"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["answer_mode"] == "tools_only"
        assert body["plan"] == ["kb_search"]
        assert body["completed"] == 1 and body["aborted"] is False
        assert body["steps"][0]["tool"] == "kb_search" and body["steps"][0]["ok"] is True
        assert "门诊时间：周一至周五 8:00-17:00" in body["answer"]
        assert body["citations"][0]["filename"] == "手册.pdf"
        assert pipeline.calls == [
            # 未显式传 top_k 时由工具默认值填充（kb_search 的 schema default=5）
            {"question": "门诊时间是什么时候", "kb": kb_id, "top_k": 5}
        ]
        assert any("tools_only" in w for w in body["warnings"]), body["warnings"]
        assert body["model"] is None
        assert body["max_tool_calls"] == agent["max_tool_calls"]
        print("[PASS] tools_only 模式：回答来自真实检索结果，且如实标注来源")

    def test_calculator_only_agent(self, client):
        headers = _register_and_login(client, "agents_exec_calc")
        agent = _create_agent(client, headers, name="计算 Agent", tools=["calculator"])

        resp = client.post(
            f"/api/agents/{agent['id']}/execute",
            json={"query": "计算 12*12+1"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["plan"] == ["calculator"], "没有知识库时不应出现 kb_search"
        assert body["steps"][0]["output"]["result"] == 145
        assert "12*12+1 = 145" in body["answer"]
        print(f"[PASS] calculator 路径：{body['answer']}")

    def test_combined_plan_with_top_k(self, client, monkeypatch):
        headers = _register_and_login(client, "agents_exec_both")
        kb_id = _create_kb(client, headers, "混合库")
        agent = _create_agent(
            client,
            headers,
            name="混合 Agent",
            knowledge_base_id=kb_id,
            tools=["kb_search", "calculator"],
            max_tool_calls=3,
        )
        pipeline = _FakePipeline()
        _patch_kb_search_pipeline(monkeypatch, pipeline)

        resp = client.post(
            f"/api/agents/{agent['id']}/execute",
            json={"query": "计算 2+3", "top_k": 2},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["plan"] == ["kb_search", "calculator"]
        assert body["completed"] == 2
        assert "门诊时间：周一至周五 8:00-17:00" in body["answer"]
        assert "2+3 = 5" in body["answer"]
        assert pipeline.calls[0]["top_k"] == 2, "top_k 必须透传到 kb_search"
        print("[PASS] 多步计划（kb_search → calculator）顺序执行且 top_k 透传")

    def test_disabled_agent_returns_409(self, client):
        headers = _register_and_login(client, "agents_exec_disabled")
        agent = _create_agent(
            client, headers, name="停用 Agent", tools=["calculator"], enabled=False
        )

        resp = client.post(
            f"/api/agents/{agent['id']}/execute",
            json={"query": "1+1"},
            headers=headers,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "AGENT_DISABLED"
        print("[PASS] 停用的 Agent 执行 → 409（不是空结果）")

    def test_agent_without_capability_returns_400(self, client):
        headers = _register_and_login(client, "agents_exec_empty")
        agent = _create_agent(client, headers, name="空 Agent", tools=[])

        resp = client.post(
            f"/api/agents/{agent['id']}/execute",
            json={"query": "门诊时间"},
            headers=headers,
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == "AGENT_NOT_CONFIGURED"
        print("[PASS] 无工具/无模型的 Agent → 400 AGENT_NOT_CONFIGURED")

    def test_tool_failure_is_visible_but_opaque(self, client, monkeypatch):
        """审计要求 4：失败不吞（steps/warnings 可见），但内部细节不泄漏。"""
        headers = _register_and_login(client, "agents_exec_fail")
        kb_id = _create_kb(client, headers, "故障库")
        agent = _create_agent(
            client,
            headers,
            name="故障 Agent",
            knowledge_base_id=kb_id,
            tools=["kb_search", "calculator"],
        )
        _patch_kb_search_pipeline(
            monkeypatch, _FakePipeline(error=RuntimeError(SECRET_LEAK))
        )

        resp = client.post(
            f"/api/agents/{agent['id']}/execute",
            json={"query": "计算 1+1"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert SECRET_LEAK not in resp.text

        body = resp.json()
        assert body["aborted"] is True
        assert body["completed"] == 0
        assert len(body["steps"]) == 1, "失败即停：calculator 不应再执行"
        assert body["steps"][0]["error"]["code"] == "TOOL_EXECUTION_FAILED"
        assert any("失败" in warning for warning in body["warnings"])
        assert "4" not in body["answer"] or "计算结果" not in body["answer"]
        print(f"[PASS] 工具失败可见且不泄漏：{body['warnings'][0]}")


def _set_model_enabled(temp_db, model_id: int, enabled: bool) -> None:
    """把 ``llm_models`` 行的 enabled 改掉（模拟"绑定后被禁用"）。"""
    from sqlalchemy import select

    from app.models.llm_model import LLMModel

    async def scenario() -> None:
        async with temp_db.session() as db:
            result = await db.execute(select(LLMModel).where(LLMModel.id == model_id))
            model = result.scalar_one()
            model.enabled = enabled
            await db.commit()

    asyncio.run(scenario())


class TestAgentLlmMode:
    """绑定模型时走真实 Provider 装配（只在构造处注入替身，避免网络调用）。"""

    def test_llm_mode_uses_bound_model_and_system_prompt(
        self, client, temp_db, monkeypatch
    ):
        headers = _register_and_login(client, "agents_llm")
        kb_id = _create_kb(client, headers, "LLM 库")
        model_id = _add_llm_model(temp_db)
        agent = _create_agent(
            client,
            headers,
            name="LLM Agent",
            knowledge_base_id=kb_id,
            model_id=model_id,
            system_prompt="你是门诊助手",
            tools=["kb_search"],
        )
        provider = _FakeProvider(reply="门诊时间是周一至周五 8:00-17:00。")
        _patch_provider(monkeypatch, provider)
        _patch_kb_search_pipeline(monkeypatch, _FakePipeline())

        resp = client.post(
            f"/api/agents/{agent['id']}/execute",
            json={"query": "门诊时间是什么时候"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["answer_mode"] == "llm"
        assert body["model"] == "agnes-2.5-flash"
        assert body["answer"] == "门诊时间是周一至周五 8:00-17:00。"
        assert body["steps"][0]["tool"] == "kb_search"

        messages = provider.calls[0]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "你是门诊助手"
        assert "门诊时间：周一至周五 8:00-17:00" in messages[1]["content"], (
            "检索片段必须进入 prompt（否则等于没接知识库）"
        )
        assert "门诊时间是什么时候" in messages[1]["content"]
        assert not any("tools_only" in w for w in body["warnings"]), body["warnings"]
        print("[PASS] llm 模式：真实调用链 + 片段进 prompt + answer_mode=llm")

    def test_llm_failure_returns_502_without_leaking(self, client, temp_db, monkeypatch):
        headers = _register_and_login(client, "agents_llm_fail")
        model_id = _add_llm_model(temp_db)
        agent = _create_agent(
            client, headers, name="LLM 故障", model_id=model_id, tools=["calculator"]
        )
        _patch_provider(monkeypatch, _FakeProvider(error=RuntimeError(SECRET_LEAK)))

        resp = client.post(
            f"/api/agents/{agent['id']}/execute",
            json={"query": "1+1"},
            headers=headers,
        )
        assert resp.status_code == 502, resp.text
        assert SECRET_LEAK not in resp.text
        body = resp.json()
        assert body["code"] == "AGENT_GENERATION_FAILED"
        assert body.get("request_id"), "5xx 必须带 request_id"
        print(f"[PASS] LLM 故障 → {body['code']}（无细节泄漏）")

    def test_model_disabled_after_binding_returns_400(self, client, temp_db, monkeypatch):
        """绑定后被禁用 → 明确报错，**不**静默降级成 tools_only。"""
        headers = _register_and_login(client, "agents_llm_disabled")
        model_id = _add_llm_model(temp_db)
        agent = _create_agent(
            client, headers, name="模型停用", model_id=model_id, tools=["calculator"]
        )
        _set_model_enabled(temp_db, model_id, False)

        resp = client.post(
            f"/api/agents/{agent['id']}/execute",
            json={"query": "1+1"},
            headers=headers,
        )
        assert resp.status_code == 400, resp.text
        body = resp.json()
        assert body["code"] == "AGENT_NOT_CONFIGURED"
        assert "已禁用" in body["message"]
        print(f"[PASS] 模型被禁用 → {body['message']}")


if __name__ == "__main__":  # pragma: no cover - 便于手工单跑
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
