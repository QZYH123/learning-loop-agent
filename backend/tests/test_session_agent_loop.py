from backend.tests.conftest import ImmediateFakeModelClient, make_client, wait_for
from backend.tests.test_exam_workflow_api import ExamFakeModel, build_exam, publish_ready_exam
from backend.tests.test_issue16_workflows import create_subject_and_source
from backend.tests.test_sources_api import wait_for_operation


class SessionProposalFake(ImmediateFakeModelClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._workers = ExamFakeModel()

    async def chat(self, profile, messages, max_tokens=None, tools=None, on_delta=None):
        content = messages[-1].get("content") if messages else ""
        text = content if isinstance(content, str) else ""
        if not tools:
            if "创建资料文档" in text or "第一行只输出文档标题" in text:
                self.chat_calls.append({
                    "profile": profile,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "tools": tools,
                })
                return {
                    "text": "复习提纲\n这是正文。",
                    "provider": profile["provider"],
                    "model": profile["model"],
                    "tool_calls": [],
                }
            if "请按要求修改资料文档" in text:
                self.chat_calls.append({
                    "profile": profile,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "tools": tools,
                })
                return {
                    "text": "修改后的文档。",
                    "provider": profile["provider"],
                    "model": profile["model"],
                    "tool_calls": [],
                }
            worker_hints = (
                "把组卷要求解析为 JSON",
                "结构化差异预览",
                "生成一道",
                "一次生成整张试卷",
                "完整选择题",
                "题目版选择题",
            )
            if any(hint in text for hint in worker_hints):
                return await self._workers.chat(profile, messages, max_tokens, tools)
        return await super().chat(profile, messages, max_tokens, tools)


def _create_subject_and_model(client):
    subject_id = client.post("/api/subjects", json={"name": "数学"}).json()["id"]
    model_id = client.post(
        "/api/models",
        json={"provider": "Fake", "api_format": "openai-chat-completions", "model": "fake-1", "base_url": "http://localhost/v1"},
    ).json()["id"]
    return subject_id, model_id


def _editable_draft(client, blueprint_id):
    client.patch(f"/api/exam-blueprints/{blueprint_id}", json={"total_score": 20})
    assert client.post(f"/api/exam-blueprints/{blueprint_id}/confirm").status_code == 200
    generated = client.post(f"/api/exam-blueprints/{blueprint_id}/generate").json()
    assert wait_for_operation(client, generated["operation"]["id"])["status"] == "succeeded"
    draft_id = generated["resource"]["id"]
    draft = client.get(f"/api/exam-drafts/{draft_id}").json()
    for slot in draft["questions"]:
        if slot["status"] == "needs-review":
            retried = client.post(
                f"/api/exam-drafts/{draft_id}/questions/{slot['id']}/retry"
            ).json()
            wait_for_operation(client, retried["operation"]["id"])
    return client.get(f"/api/exam-drafts/{draft_id}").json()


def _script_tool_then_text(name, arguments, text):
    return [
        {"text": "", "tool_calls": [{"id": "call_1", "name": name, "arguments": arguments}]},
        {"text": text},
    ]


def _generation_calls(model_client):
    calls = []
    for call in model_client.chat_calls:
        content = call["messages"][-1].get("content")
        text = content if isinstance(content, str) else ""
        if "起一个不超过12个字" not in text:
            calls.append(call)
    return calls


def _send_session_message(client, session_id, model_id, content, **extra):
    sent = client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": content, "model_id": model_id, **extra},
    )
    assert sent.status_code == 202
    wait_for(lambda: client.get(f"/api/operations/{sent.json()['operation']['id']}").json()["status"] == "succeeded")
    return client.get(f"/api/sessions/{session_id}").json()["messages"][-1]


def test_session_agent_search_sources_writes_tool_events_and_citations(tmp_path):
    fake = ImmediateFakeModelClient(script=[
        {
            "text": "",
            "tool_calls": [{"id": "call_1", "name": "search_sources", "arguments": {"query": "limit"}}],
        },
        {"text": "极限描述函数在某点附近的行为。"},
    ])
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id, version_id = create_subject_and_source(client)
        model_id = client.post(
            "/api/models",
            json={"provider": "Fake", "api_format": "openai-chat-completions", "model": "fake-1", "base_url": "http://localhost/v1"},
        ).json()["id"]
        session = client.post(
            f"/api/subjects/{subject_id}/sessions",
            json={"title": "资料检索", "source_version_ids": [version_id]},
        ).json()
        message = _send_session_message(
            client,
            session["id"],
            model_id,
            "TCP 拥塞控制是什么？",
            grounding_mode="supplemental",
        )
        assert message["status"] == "complete"
        assert message["content"][0]["text"] == "极限描述函数在某点附近的行为。"
        events = message["tool_events"]
        assert len(events) == 1
        assert events[0]["name"] == "search_sources"
        assert events[0]["status"] == "succeeded"
        assert events[0]["summary"].startswith("已检索资料：")
        assert events[0]["arguments"]["query"] == "limit"
        assert any(item["source_version_id"] == version_id for item in message["citations"])
        assert any("limit" in (item.get("excerpt") or "").casefold() for item in message["citations"])

        first, second = _generation_calls(fake)
        assert "search_sources" in [item["name"] for item in first["tools"]]
        assert second["messages"][-1]["role"] == "tool"
        assert "The limit of x is x." in second["messages"][-1]["content"]

        runs = client.get("/api/orchestration-runs", params={"subject_id": subject_id, "category": "chat-generation"}).json()["items"]
        assert any(stage["name"] == "tool-call" for run in runs for stage in run["stages"])


def test_session_agent_get_study_state_includes_recent_missed_points(tmp_path):
    exam_fake = ExamFakeModel()
    client, app = make_client(tmp_path, model_client=exam_fake)
    with client:
        subject_id, model_id, _, blueprint_id = build_exam(client)
        exam = publish_ready_exam(client, blueprint_id)
        choice = next(question for question in exam["document"]["questions"] if question["type"] == "single-choice")
        practice = client.post(f"/api/exams/{exam['id']}/attempts", json={"mode": "practice"}).json()
        answered = client.put(
            f"/api/attempts/{practice['id']}/answers/{choice['id']}",
            json={"answer": {"kind": "choice", "option_ids": ["B"]}},
        )
        assert answered.status_code == 200
        missed = app.state.exam_service._recent_missed_knowledge_points(subject_id)
        assert missed

        fake = ImmediateFakeModelClient(script=[
            {"text": "", "tool_calls": [{"id": "call_1", "name": "get_study_state", "arguments": {}}]},
            {"text": "建议先复习最近错点。"},
        ])
        app.state.learning_service.model_client = fake
        session = client.post(f"/api/subjects/{subject_id}/sessions", json={"title": "错点复习"}).json()
        message = _send_session_message(client, session["id"], model_id, "我最近错在哪里？")
        assert message["status"] == "complete"
        events = message["tool_events"]
        assert events[0]["name"] == "get_study_state"
        assert events[0]["status"] == "succeeded"
        assert events[0]["summary"] == "已读取学习进度与最近错点"
        tool_result = _generation_calls(fake)[1]["messages"][-1]["content"]
        assert all(point in tool_result for point in missed)


def test_session_agent_stops_after_four_tool_rounds_with_final_text(tmp_path):
    script = [
        {"text": "", "tool_calls": [{"id": f"call_{index}", "name": "get_study_state", "arguments": {}}]}
        for index in range(1, 5)
    ]
    script.append({"text": "已根据已有结果作答。"})
    fake = ImmediateFakeModelClient(script=script)
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id = client.post("/api/subjects", json={"name": "数学"}).json()["id"]
        model_id = client.post(
            "/api/models",
            json={"provider": "Fake", "api_format": "openai-chat-completions", "model": "fake-1", "base_url": "http://localhost/v1"},
        ).json()["id"]
        session = client.post(f"/api/subjects/{subject_id}/sessions", json={"title": "循环截断"}).json()
        message = _send_session_message(client, session["id"], model_id, "连续看一下学习状态")
        assert message["status"] == "complete"
        assert message["content"][0]["text"] == "已根据已有结果作答。"
        assert len(message["tool_events"]) == 4
        assert all(event["name"] == "get_study_state" for event in message["tool_events"])
        calls = _generation_calls(fake)
        assert len(calls) == 5
        assert all(call["tools"] for call in calls[:4])
        assert calls[4]["tools"] is None
        assert "不要再调用工具" in calls[4]["messages"][-1]["content"]


def test_session_agent_tools_unsupported_falls_back_to_plain_answer(tmp_path):
    fake = ImmediateFakeModelClient(answer="普通问答回复", reject_tools=True)
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id = client.post("/api/subjects", json={"name": "数学"}).json()["id"]
        model_id = client.post(
            "/api/models",
            json={"provider": "Fake", "api_format": "openai-chat-completions", "model": "fake-1", "base_url": "http://localhost/v1"},
        ).json()["id"]
        session = client.post(f"/api/subjects/{subject_id}/sessions", json={"title": "无工具"}).json()
        message = _send_session_message(client, session["id"], model_id, "你好")
        assert message["status"] == "complete"
        assert message["content"][0]["text"] == "普通问答回复"
        assert message["tool_events"] == [{
            "id": message["tool_events"][0]["id"],
            "name": "tools-unsupported",
            "status": "failed",
            "summary": "当前模型不支持工具调用，已按普通问答回复",
            "resource": None,
            "arguments": None,
        }]
        assert _generation_calls(fake)[0]["tools"]


def test_session_agent_tool_error_does_not_fail_message(tmp_path):
    fake = ImmediateFakeModelClient(script=[
        {"text": "", "tool_calls": [{"id": "call_1", "name": "get_study_state", "arguments": {}}]},
        {"text": "我先根据已有信息回答。"},
    ])
    client, app = make_client(tmp_path, model_client=fake)
    with client:
        subject_id = client.post("/api/subjects", json={"name": "数学"}).json()["id"]
        model_id = client.post(
            "/api/models",
            json={"provider": "Fake", "api_format": "openai-chat-completions", "model": "fake-1", "base_url": "http://localhost/v1"},
        ).json()["id"]

        def boom(subject_id):
            raise RuntimeError("错点读取失败")

        app.state.exam_service._recent_missed_knowledge_points = boom
        session = client.post(f"/api/subjects/{subject_id}/sessions", json={"title": "工具失败"}).json()
        message = _send_session_message(client, session["id"], model_id, "看一下学习状态")
        assert message["status"] == "complete"
        assert message["content"][0]["text"] == "我先根据已有信息回答。"
        assert message["tool_events"][0]["name"] == "get_study_state"
        assert message["tool_events"][0]["status"] == "failed"
        tool_result = _generation_calls(fake)[1]["messages"][-1]
        assert tool_result["role"] == "tool"
        assert "错点读取失败" in tool_result["content"]


def test_session_strict_uncovered_short_circuit_does_not_call_model(tmp_path):
    fake = ImmediateFakeModelClient(answer="不该出现")
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id, version_id = create_subject_and_source(client)
        model_id = client.post(
            "/api/models",
            json={"provider": "Fake", "api_format": "openai-chat-completions", "model": "fake-1", "base_url": "http://localhost/v1"},
        ).json()["id"]
        session = client.post(
            f"/api/subjects/{subject_id}/sessions",
            json={"title": "严格短路", "source_version_ids": [version_id]},
        ).json()
        message = _send_session_message(
            client,
            session["id"],
            model_id,
            "光合作用是什么？",
            grounding_mode="strict",
        )
        assert message["status"] == "complete"
        assert message["grounding_result"] == "not-covered"
        assert "无法仅依据资料回答" in message["content"][0]["text"]
        assert fake.chat_calls == []
        assert message.get("tool_events") in ([], None)


def test_session_agent_propose_exam_blueprint_creates_blueprint_and_resource(tmp_path):
    fake = SessionProposalFake(script=_script_tool_then_text(
        "propose_exam_blueprint",
        {"requirements": "出一套极限小测"},
        "已创建蓝图，请到组卷区确认。",
    ))
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id, model_id = _create_subject_and_model(client)
        session = client.post(f"/api/subjects/{subject_id}/sessions", json={"title": "组卷"}).json()
        message = _send_session_message(
            client,
            session["id"],
            model_id,
            "帮我出一套极限练习",
            workspace_context={"workspace": "learn"},
        )
        assert message["status"] == "complete"
        assert message["content"][0]["text"] == "已创建蓝图，请到组卷区确认。"
        event = message["tool_events"][0]
        assert event["name"] == "propose_exam_blueprint"
        assert event["status"] == "succeeded"
        assert event["resource"]["type"] == "exam-blueprint"
        assert event["resource"]["id"]
        # 卡片标题只说发生了什么；去向由前端按 resource 类型渲染
        assert event["summary"] == "已创建蓝图，正在解析"
        blueprints = client.get(f"/api/subjects/{subject_id}/exam-blueprints").json()["items"]
        assert any(item["id"] == event["resource"]["id"] for item in blueprints)
        assert message["source_context"]["workspace_context"]["workspace"] == "learn"


def test_session_agent_propose_revision_routes_to_draft(tmp_path):
    exam_fake = ExamFakeModel()
    client, app = make_client(tmp_path, model_client=exam_fake)
    with client:
        subject_id, model_id, _, blueprint_id = build_exam(client)
        draft = _editable_draft(client, blueprint_id)
        app.state.learning_service.model_client = ImmediateFakeModelClient(
            script=_script_tool_then_text("propose_revision", {"instruction": "把标题改短"}, "提案已创建。"),
        )
        session = client.post(f"/api/subjects/{subject_id}/sessions", json={"title": "改草稿"}).json()
        message = _send_session_message(
            client,
            session["id"],
            model_id,
            "把标题改短一点",
            workspace_context={"workspace": "exam", "draft_id": draft["id"]},
        )
        assert message["status"] == "complete"
        event = message["tool_events"][0]
        assert event["name"] == "propose_revision"
        assert event["status"] == "succeeded"
        assert event["resource"]["type"] == "draft-revision-proposal"
        wait_for(
            lambda: any(
                item["id"] == event["resource"]["id"] and item["status"] == "ready"
                for item in client.get(f"/api/exam-drafts/{draft['id']}/revision-proposals").json()["items"]
            ),
            timeout=5,
        )
        assert message["source_context"]["workspace_context"]["draft_id"] == draft["id"]


def test_session_agent_propose_revision_routes_to_exam(tmp_path):
    exam_fake = ExamFakeModel()
    client, app = make_client(tmp_path, model_client=exam_fake)
    with client:
        subject_id, model_id, _, blueprint_id = build_exam(client)
        exam = publish_ready_exam(client, blueprint_id)
        app.state.learning_service.model_client = ImmediateFakeModelClient(
            script=_script_tool_then_text("propose_revision", {"instruction": "把标题改短"}, "提案已创建。"),
        )
        session = client.post(f"/api/subjects/{subject_id}/sessions", json={"title": "改试卷"}).json()
        message = _send_session_message(
            client,
            session["id"],
            model_id,
            "把标题改短一点",
            workspace_context={"workspace": "exam", "exam_id": exam["id"]},
        )
        assert message["status"] == "complete"
        event = message["tool_events"][0]
        assert event["name"] == "propose_revision"
        assert event["status"] == "succeeded"
        assert event["resource"]["type"] == "revision-proposal"
        wait_for(
            lambda: any(
                item["id"] == event["resource"]["id"] and item["status"] == "ready"
                for item in client.get(f"/api/exams/{exam['id']}/revision-proposals").json()["items"]
            ),
            timeout=5,
        )


def test_session_agent_propose_revision_routes_to_ai_document(tmp_path):
    model_client = ImmediateFakeModelClient(answer="复习提纲\n正文")
    client, app = make_client(tmp_path, model_client=model_client)
    with client:
        subject_id, model_id = _create_subject_and_model(client)
        created = client.post(
            f"/api/subjects/{subject_id}/documents",
            json={
                "instruction": "整理极限",
                "source_version_ids": [],
                "grounding_mode": "general-knowledge",
                "model_id": model_id,
            },
        )
        assert created.status_code == 202
        wait_for(lambda: client.get(f"/api/operations/{created.json()['operation']['id']}").json()["status"] == "succeeded")
        doc_id = created.json()["resource"]["id"]
        app.state.learning_service.model_client = ImmediateFakeModelClient(
            script=_script_tool_then_text("propose_revision", {"instruction": "写短一点"}, "提案已创建。"),
        )
        session = client.post(f"/api/subjects/{subject_id}/sessions", json={"title": "改文档"}).json()
        message = _send_session_message(
            client,
            session["id"],
            model_id,
            "把文档写短一点",
            workspace_context={"workspace": "sources", "ai_document_id": doc_id},
        )
        assert message["status"] == "complete"
        event = message["tool_events"][0]
        assert event["name"] == "propose_revision"
        assert event["status"] == "succeeded"
        assert event["resource"]["type"] == "ai-document-proposal"
        wait_for(
            lambda: any(
                item["id"] == event["resource"]["id"] and item["status"] == "ready"
                for item in client.get(f"/api/documents/{doc_id}/revision-proposals").json()["items"]
            ),
            timeout=5,
        )


def test_session_agent_propose_revision_without_context_creates_nothing(tmp_path):
    fake = ImmediateFakeModelClient(script=_script_tool_then_text(
        "propose_revision",
        {"instruction": "改一下"},
        "当前没有选中可修改的对象。",
    ))
    client, app = make_client(tmp_path, model_client=fake)
    with client:
        subject_id, model_id = _create_subject_and_model(client)
        session = client.post(f"/api/subjects/{subject_id}/sessions", json={"title": "无对象"}).json()
        message = _send_session_message(client, session["id"], model_id, "帮我改一下")
        assert message["status"] == "complete"
        event = message["tool_events"][0]
        assert event["name"] == "propose_revision"
        assert event["status"] == "succeeded"
        assert event["resource"] is None
        assert "没有选中可修改的对象" in event["summary"]
        data = app.state.learning_service._subject(subject_id)["data"]
        assert data.get("draft_revision_proposals", []) == []
        assert data.get("revision_proposals", []) == []
        assert data.get("ai_document_proposals", []) == []


def test_session_agent_create_ai_document_returns_resource(tmp_path):
    fake = SessionProposalFake(script=_script_tool_then_text(
        "create_ai_document",
        {"instruction": "整理极限要点"},
        "已创建文档，请到资料区确认。",
    ))
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id, model_id = _create_subject_and_model(client)
        session = client.post(f"/api/subjects/{subject_id}/sessions", json={"title": "文档"}).json()
        message = _send_session_message(
            client,
            session["id"],
            model_id,
            "整理一份极限笔记",
            workspace_context={"workspace": "sources"},
        )
        assert message["status"] == "complete"
        event = message["tool_events"][0]
        assert event["name"] == "create_ai_document"
        assert event["status"] == "succeeded"
        assert event["resource"]["type"] == "ai-document"
        assert event["resource"]["id"]
        # 卡片标题只说发生了什么；去向由前端按 resource 类型渲染
        assert event["summary"] == "已创建 AI 文档，正在生成"
        wait_for(
            lambda: any(
                item["id"] == event["resource"]["id"]
                for item in client.get(f"/api/subjects/{subject_id}/documents").json()["items"]
            ),
            timeout=5,
        )


def test_session_workspace_context_rejects_unknown_keys(tmp_path):
    fake = ImmediateFakeModelClient(answer="普通回复")
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id, model_id = _create_subject_and_model(client)
        session = client.post(f"/api/subjects/{subject_id}/sessions", json={"title": "契约"}).json()
        sent = client.post(
            f"/api/sessions/{session['id']}/messages",
            json={
                "content": "你好",
                "model_id": model_id,
                "workspace_context": {"workspace": "learn", "foo": "bar"},
            },
        )
        assert sent.status_code == 422
