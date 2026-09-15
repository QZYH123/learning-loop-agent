import asyncio
import copy
import json
import re

from backend.tests.conftest import ImmediateFakeModelClient, make_client, wait_for
from backend.tests.support.bootstrap import create_subject_and_model
from backend.tests.support.exam import (
    ExamFakeModel,
    _prepare_editable_draft,
    build_exam,
    publish_ready_exam,
)
from backend.tests.support.http import upload_source, wait_for_operation


class MessyExamFakeModel(ExamFakeModel):
    async def chat(self, profile, messages, max_tokens=None, tools=None, on_delta=None):
        content = messages[-1]["content"] if messages else ""
        if not isinstance(content, str) or "生成一道" not in content:
            return await super().chat(profile, messages, max_tokens, tools=tools)
        self.chat_calls.append({"profile": profile, "messages": messages})
        if "生成一道 single-choice" in content:
            payload = {
                "type": "single_choice",
                "stem": {"text": "A limit primarily describes what?"},
                "options": [
                    {"id": "A", "text": "Nearby behavior"},
                    {"id": "B", "text": "Only the point value"},
                ],
                "answer": "A",
                "explanation": "Limits describe nearby behavior.",
                "knowledge_points": "Limits",
            }
            return {"text": "```json\n" + json.dumps(payload) + "\n```", "provider": profile["provider"], "model": profile["model"]}
        if "生成一道 fill-blank" in content:
            payload = {
                "type": "fill-blank",
                "stem": "The nearby behavior is described by a ____.",
                "answer": "limit",
                "explanation": "The missing term is limit.",
                "knowledge_points": ["Limits"],
            }
            return {"text": json.dumps(payload), "provider": profile["provider"], "model": profile["model"]}
        if "生成一道 true-false" in content:
            payload = {
                "type": "true-false",
                "stem": "A limit can exist even when the point value differs.",
                "answer": True,
                "explanation": "A limit concerns nearby values.",
                "knowledge_points": ["Limits"],
            }
            return {"text": json.dumps(payload), "provider": profile["provider"], "model": profile["model"]}
        payload = {
            "type": "short-answer",
            "stem": "Explain what a limit describes.",
            "answer": "It describes nearby behavior.",
            "explanation": "Focus on values near the point.",
            "knowledge_points": ["Limits"],
        }
        return {"text": json.dumps(payload), "provider": profile["provider"], "model": profile["model"]}


class WaitingRevisionFakeModel(ExamFakeModel):
    def __init__(self):
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def chat(self, profile, messages, max_tokens=None, tools=None, on_delta=None):
        content = messages[-1]["content"] if messages else ""
        if isinstance(content, str) and "结构化差异预览" in content:
            self.started.set()
            await self.release.wait()
        return await super().chat(profile, messages, max_tokens, tools=tools)


def test_blueprint_draft_exam_attempt_and_selection_workflow(tmp_path):
    fake = ExamFakeModel()
    client, app = make_client(tmp_path, model_client=fake)
    with client:
        subject_id, model_id, version_id, blueprint_id = build_exam(client)
        blueprint = client.get(f"/api/exam-blueprints/{blueprint_id}").json()
        assert blueprint["status"] == "draft"

        conflict = client.patch(f"/api/exam-blueprints/{blueprint_id}", json={"total_score": 21}).json()
        assert conflict["issues"][0]["severity"] == "error"
        blocked = client.post(f"/api/exam-blueprints/{blueprint_id}/confirm")
        assert blocked.status_code == 409
        client.patch(f"/api/exam-blueprints/{blueprint_id}", json={"total_score": 20})
        confirmed = client.post(f"/api/exam-blueprints/{blueprint_id}/confirm").json()
        assert confirmed["status"] == "confirmed"
        renamed_blueprint = client.patch(f"/api/exam-blueprints/{blueprint_id}", json={"title": "极限小测"}).json()
        assert renamed_blueprint["status"] == "confirmed"
        assert renamed_blueprint["title"] == "极限小测"

        generated = client.post(f"/api/exam-blueprints/{blueprint_id}/generate")
        draft_id = generated.json()["resource"]["id"]
        assert wait_for_operation(client, generated.json()["operation"]["id"])["status"] == "succeeded"
        draft = client.get(f"/api/exam-drafts/{draft_id}").json()
        assert [item["status"] for item in draft["questions"]].count("needs-review") == 1
        failed_id = next(item["id"] for item in draft["questions"] if item["status"] == "needs-review")

        retried = client.post(f"/api/exam-drafts/{draft_id}/questions/{failed_id}/retry")
        assert wait_for_operation(client, retried.json()["operation"]["id"])["status"] == "succeeded"
        draft = client.get(f"/api/exam-drafts/{draft_id}").json()
        assert {item["status"] for item in draft["questions"]} == {"complete"}

        published = client.post(f"/api/exam-drafts/{draft_id}/publish", json={})
        assert published.status_code == 201
        exam = published.json()
        exam_id = exam["id"]
        renamed_exam = client.patch(f"/api/exams/{exam_id}", json={"title": "极限试卷"}).json()
        assert renamed_exam["document"]["title"] == "极限试卷"
        assert renamed_exam["can_undo"] is False
        assert renamed_exam["current_version_id"] == exam["current_version_id"]
        original_document = renamed_exam["document"]

        attempt = client.post(f"/api/exams/{exam_id}/attempts", json={"mode": "exam"}).json()
        attempt_id = attempt["id"]
        assert attempt["elapsed_ms"] == 0
        assert attempt["timing_started_at"] == attempt["created_at"]
        assert all("answer" not in question and "explanation" not in question and "evidence" not in question for question in attempt["paper"]["questions"])
        choice = next(question for question in exam["document"]["questions"] if question["type"] == "single-choice")
        saved = client.put(f"/api/attempts/{attempt_id}/answers/{choice['id']}", json={
            "answer": {"kind": "choice", "option_ids": ["A"]},
        })
        assert saved.status_code == 200
        assert client.get(f"/api/attempts/{attempt_id}").json()["feedback"] == []
        assert client.get(f"/api/attempts/{attempt_id}/review").status_code == 409
        clock = {"now": attempt["timing_started_at"]}
        app.state.exam_service._now = lambda: clock["now"]
        clock["now"] += 5000
        paused = client.post(f"/api/attempts/{attempt_id}/pause").json()
        assert paused["status"] == "paused"
        assert paused["timing_started_at"] is None
        assert paused["elapsed_ms"] == 5000
        clock["now"] += 8000
        resumed = client.post(f"/api/attempts/{attempt_id}/resume").json()
        assert resumed["status"] == "in-progress"
        assert resumed["elapsed_ms"] == 5000
        assert resumed["timing_started_at"] == clock["now"]
        app.state.exam_service._now = lambda: int(__import__("time").time() * 1000)
        submitted = client.post(f"/api/attempts/{attempt_id}/submit")
        wait_for_operation(client, submitted.json()["operation"]["id"])
        review = client.get(f"/api/attempts/{attempt_id}/review")
        assert review.status_code == 200
        assert review.json()["items"][0]["question"]["answer"]

        practice = client.post(f"/api/exams/{exam_id}/attempts", json={
            "mode": "practice",
            "show_suggested_score": False,
        }).json()
        fill = next(question for question in exam["document"]["questions"] if question["type"] == "fill-blank")
        client.put(f"/api/attempts/{practice['id']}/answers/{fill['id']}", json={
            "answer": {"kind": "fill-blank", "blanks": [{"blank_id": "blank-1", "value": "  LIMIT  "}]},
        })
        restored = client.get(f"/api/attempts/{practice['id']}").json()
        assert restored["feedback"][0]["correct"] is True

        subjective = next(question for question in exam["document"]["questions"] if question["type"] == "short-answer")
        client.put(f"/api/attempts/{practice['id']}/answers/{subjective['id']}", json={
            "answer": {"kind": "text", "text": "It describes nearby behavior."},
        })
        feedback = client.post(f"/api/attempts/{practice['id']}/answers/{subjective['id']}/feedback", json={
            "model_id": model_id,
            "show_suggested_score": False,
        })
        assert wait_for_operation(client, feedback.json()["operation"]["id"])["status"] == "succeeded"
        restored = client.get(f"/api/attempts/{practice['id']}").json()
        subjective_feedback = next(item for item in restored["feedback"] if item["question_id"] == subjective["id"])
        assert subjective_feedback["matched_points"][0]["id"] == "point-1"
        assert subjective_feedback["suggested_score"] is None

        stem = choice["stem"][0]
        citation_id = choice["evidence"]["citations"][0]["id"]
        selected = client.post(f"/api/subjects/{subject_id}/chat/messages", json={
            "intent": "ask",
            "content": "解释这个选区",
            "grounding_mode": "strict",
            "source_version_ids": [version_id],
            "selection": {
                "document_kind": "exam",
                "document_id": exam_id,
                "version_id": exam["current_version_id"],
                "question_id": choice["id"],
                "block_id": stem["id"],
                "citation_ids": [citation_id],
                "selected_text": stem["text"],
            },
        })
        assert wait_for_operation(client, selected.json()["operation"]["id"])["status"] == "succeeded"
        chat = client.get(f"/api/subjects/{subject_id}/chat").json()
        assert chat["messages"][-1]["selection"]["question_id"] == choice["id"]
        assert client.get(f"/api/exams/{exam_id}").json()["document"] == original_document

        session = client.post(f"/api/subjects/{subject_id}/sessions", json={
            "source_version_ids": [version_id],
        }).json()
        call_count = len(fake.chat_calls)
        session_selected = client.post(f"/api/sessions/{session['id']}/messages", json={
            "intent": "ask",
            "content": "解释这个选区",
            "grounding_mode": "strict",
            "selection": {
                "document_kind": "exam",
                "document_id": exam_id,
                "version_id": exam["current_version_id"],
                "question_id": choice["id"],
                "block_id": stem["id"],
                "citation_ids": [citation_id],
                "selected_text": stem["text"],
            },
        })
        assert wait_for_operation(client, session_selected.json()["operation"]["id"])["status"] == "succeeded"
        assert len(fake.chat_calls) == call_count + 2
        generation = next(
            call for call in fake.chat_calls[call_count:]
            if "起一个不超过12个字" not in call["messages"][-1]["content"]
        )
        assert stem["text"] in generation["messages"][-1]["content"]

        invalid_selection = client.post(f"/api/subjects/{subject_id}/chat/messages", json={
            "intent": "ask",
            "content": "无效选区",
            "selection": {
                "document_kind": "exam",
                "document_id": exam_id,
                "version_id": "stale-version",
                "selected_text": stem["text"],
            },
        })
        assert invalid_selection.status_code == 409
        assert invalid_selection.json()["error"]["code"] == "CHAT_SELECTION_INVALID"

def _user_contents(fake, marker):
    contents = []
    for call in fake.chat_calls:
        content = call["messages"][-1]["content"]
        if isinstance(content, str) and marker in content:
            contents.append(content)
    return contents


def publish_exam_from_blueprint(client, blueprint_id):
    assert client.post(f"/api/exam-blueprints/{blueprint_id}/confirm").status_code == 200
    generated = client.post(f"/api/exam-blueprints/{blueprint_id}/generate").json()
    assert wait_for_operation(client, generated["operation"]["id"])["status"] == "succeeded"
    draft_id = generated["resource"]["id"]
    draft = client.get(f"/api/exam-drafts/{draft_id}").json()
    for slot in draft["questions"]:
        if slot["status"] == "needs-review":
            retried = client.post(f"/api/exam-drafts/{draft_id}/questions/{slot['id']}/retry").json()
            assert wait_for_operation(client, retried["operation"]["id"])["status"] == "succeeded"
    published = client.post(f"/api/exam-drafts/{draft_id}/publish", json={})
    assert published.status_code == 201
    return published.json()


def test_practice_objective_review_and_exam_review_gate(tmp_path):
    fake = ExamFakeModel()
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        _, _, _, blueprint_id = build_exam(client)
        exam = publish_ready_exam(client, blueprint_id)
        choice = next(question for question in exam["document"]["questions"] if question["type"] == "single-choice")

        practice = client.post(f"/api/exams/{exam['id']}/attempts", json={"mode": "practice"}).json()
        wrong = client.put(f"/api/attempts/{practice['id']}/answers/{choice['id']}", json={
            "answer": {"kind": "choice", "option_ids": ["B"]},
        })
        assert wrong.status_code == 200
        wrong_feedback = next(
            item for item in client.get(f"/api/attempts/{practice['id']}").json()["feedback"]
            if item["question_id"] == choice["id"]
        )
        assert wrong_feedback["correct"] is False
        assert wrong_feedback["suggestions"] == []

        review = client.get(f"/api/attempts/{practice['id']}/review")
        assert review.status_code == 200
        reviewed = next(item for item in review.json()["items"] if item["question"]["id"] == choice["id"])
        assert reviewed["question"]["explanation"]
        assert reviewed["question"]["knowledge_points"]

        right = client.put(f"/api/attempts/{practice['id']}/answers/{choice['id']}", json={
            "answer": {"kind": "choice", "option_ids": ["A"]},
        })
        assert right.status_code == 200
        right_feedback = next(
            item for item in client.get(f"/api/attempts/{practice['id']}").json()["feedback"]
            if item["question_id"] == choice["id"]
        )
        assert right_feedback["correct"] is True
        assert right_feedback["suggestions"] == []

        exam_attempt = client.post(f"/api/exams/{exam['id']}/attempts", json={"mode": "exam"}).json()
        client.put(f"/api/attempts/{exam_attempt['id']}/answers/{choice['id']}", json={
            "answer": {"kind": "choice", "option_ids": ["B"]},
        })
        blocked = client.get(f"/api/attempts/{exam_attempt['id']}/review")
        assert blocked.status_code == 409


def test_parse_blueprint_omits_missed_points_without_attempts(tmp_path):
    fake = ExamFakeModel()
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        build_exam(client)
        contents = _user_contents(fake, "把组卷要求解析为 JSON")
        assert contents
        assert "参考错点" not in contents[0]


def test_parse_blueprint_includes_deduped_missed_points(tmp_path):
    fake = ExamFakeModel()
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id, _, version_id, blueprint_id = build_exam(client)
        exam = publish_exam_from_blueprint(client, blueprint_id)
        document = copy.deepcopy(exam["document"])
        choice = next(question for question in document["questions"] if question["type"] == "single-choice")
        fill = next(question for question in document["questions"] if question["type"] == "fill-blank")
        true_false = next(question for question in document["questions"] if question["type"] == "true-false")
        choice["knowledge_points"] = [
            "Limits",
            "Continuity",
            "Limits",
            "Derivative",
            "Integral",
            "Series",
            "Sequence",
            "Topology",
            "Measure",
            "Algebra",
        ]
        fill["knowledge_points"] = ["Continuity", "ShouldStayDeduped", "OverCap"]
        true_false["knowledge_points"] = ["ShouldNotAppear"]
        replaced = client.put(f"/api/exams/{exam['id']}", json={
            "base_version_id": exam["current_version_id"],
            "document": document,
        })
        assert replaced.status_code == 200

        practice = client.post(f"/api/exams/{exam['id']}/attempts", json={"mode": "practice"}).json()
        client.put(f"/api/attempts/{practice['id']}/answers/{choice['id']}", json={
            "answer": {"kind": "choice", "option_ids": ["B"]},
        })
        client.put(f"/api/attempts/{practice['id']}/answers/{fill['id']}", json={
            "answer": {"kind": "fill-blank", "blanks": [{"blank_id": "blank-1", "value": "wrong"}]},
        })
        client.put(f"/api/attempts/{practice['id']}/answers/{true_false['id']}", json={
            "answer": {"kind": "true-false", "value": True},
        })

        parsed = client.post(f"/api/subjects/{subject_id}/exam-blueprints", json={
            "prompt": "再出一套 Limits，重点考我错的地方",
            "grounding_mode": "strict",
            "source_version_ids": [version_id],
        })
        assert wait_for_operation(client, parsed.json()["operation"]["id"])["status"] == "succeeded"
        content = _user_contents(fake, "把组卷要求解析为 JSON")[-1]
        expected = [
            "Limits",
            "Continuity",
            "Derivative",
            "Integral",
            "Series",
            "Sequence",
            "Topology",
            "Measure",
            "Algebra",
            "ShouldStayDeduped",
        ]
        assert "参考错点（仅当用户表达复习、巩固、再出一套等意图时才纳入考纲，否则忽略）：" + "、".join(expected) in content
        assert "OverCap" not in content
        assert "ShouldNotAppear" not in content


def test_patch_syllabus_is_persisted(tmp_path):
    fake = ExamFakeModel()
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        _, _, _, blueprint_id = build_exam(client)
        patched = client.patch(f"/api/exam-blueprints/{blueprint_id}", json={"syllabus": ["极限", "连续性"]})
        assert patched.status_code == 200
        assert patched.json()["syllabus"] == ["极限", "连续性"]
        assert client.get(f"/api/exam-blueprints/{blueprint_id}").json()["syllabus"] == ["极限", "连续性"]


def test_draft_revision_can_target_one_question(tmp_path):
    fake = ExamFakeModel()
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        _, model_id, _, blueprint_id = build_exam(client)
        client.patch(f"/api/exam-blueprints/{blueprint_id}", json={"total_score": 20})
        assert client.post(f"/api/exam-blueprints/{blueprint_id}/confirm").status_code == 200
        generated = client.post(f"/api/exam-blueprints/{blueprint_id}/generate").json()
        assert wait_for_operation(client, generated["operation"]["id"])["status"] == "succeeded"
        draft_id = generated["resource"]["id"]
        draft = client.get(f"/api/exam-drafts/{draft_id}").json()
        for slot in draft["questions"]:
            if slot["status"] == "needs-review":
                retried = client.post(f"/api/exam-drafts/{draft_id}/questions/{slot['id']}/retry").json()
                assert wait_for_operation(client, retried["operation"]["id"])["status"] == "succeeded"
        draft = client.get(f"/api/exam-drafts/{draft_id}").json()
        ready = [item for item in draft["questions"] if item.get("question")]
        assert len(ready) >= 2
        target, other = ready[0], ready[1]
        other_stem = copy.deepcopy(other["question"]["stem"])

        missing = client.post(f"/api/exam-drafts/{draft_id}/revision-proposals", json={
            "instruction": "把这题改简单一点",
            "scope": {"kind": "questions", "question_ids": ["missing-question"], "block_ids": []},
            "model_id": model_id,
        })
        assert missing.status_code == 422

        proposed = client.post(f"/api/exam-drafts/{draft_id}/revision-proposals", json={
            "instruction": "把这题改简单一点",
            "scope": {"kind": "questions", "question_ids": [target["id"]], "block_ids": []},
            "model_id": model_id,
        })
        assert proposed.status_code == 202
        assert wait_for_operation(client, proposed.json()["operation"]["id"])["status"] == "succeeded"
        proposal = next(
            item
            for item in client.get(f"/api/exam-drafts/{draft_id}/revision-proposals").json()["items"]
            if item["status"] == "ready"
        )
        assert proposal["scope"] == {"kind": "questions", "question_ids": [target["id"]], "block_ids": []}

        applied = client.post(f"/api/draft-revision-proposals/{proposal['id']}/apply")
        assert applied.status_code == 200
        updated = next(item for item in applied.json()["questions"] if item["id"] == target["id"])
        untouched = next(item for item in applied.json()["questions"] if item["id"] == other["id"])
        assert "改写后的题干" in json.dumps(updated["question"]["stem"], ensure_ascii=False)
        assert untouched["question"]["stem"] == other_stem


def test_generate_question_prompt_includes_syllabus_or_none(tmp_path):
    fake = ExamFakeModel()
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id, _, version_id, blueprint_id = build_exam(client)
        publish_exam_from_blueprint(client, blueprint_id)
        generate_contents = _user_contents(fake, "生成一道")
        assert generate_contents
        assert all("考纲重点：Limits" in content for content in generate_contents)

        parsed = client.post(f"/api/subjects/{subject_id}/exam-blueprints", json={
            "prompt": "Create a Limits exam",
            "grounding_mode": "strict",
            "source_version_ids": [version_id],
        })
        new_blueprint_id = parsed.json()["resource"]["id"]
        assert wait_for_operation(client, parsed.json()["operation"]["id"])["status"] == "succeeded"
        client.patch(f"/api/exam-blueprints/{new_blueprint_id}", json={"syllabus": []})
        before = len(_user_contents(fake, "生成一道"))
        publish_exam_from_blueprint(client, new_blueprint_id)
        empty_contents = _user_contents(fake, "生成一道")[before:]
        assert empty_contents
        assert all("考纲重点：无" in content for content in empty_contents)


def test_generate_accepts_common_model_json_shapes(tmp_path):
    fake = MessyExamFakeModel()
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        _, _, _, blueprint_id = build_exam(client)
        client.patch(f"/api/exam-blueprints/{blueprint_id}", json={"total_score": 20})
        assert client.post(f"/api/exam-blueprints/{blueprint_id}/confirm").status_code == 200
        generated = client.post(f"/api/exam-blueprints/{blueprint_id}/generate").json()
        assert wait_for_operation(client, generated["operation"]["id"])["status"] == "succeeded"
        draft = client.get(f"/api/exam-drafts/{generated['resource']['id']}").json()
        assert {item["status"] for item in draft["questions"]} == {"complete"}
        choice = next(item for item in draft["questions"] if item["planned_type"] == "single-choice")
        assert choice["question"]["answer"]["option_ids"] == ["A"]
        fill = next(item for item in draft["questions"] if item["planned_type"] == "fill-blank")
        assert fill["question"]["answer"]["blanks"][0]["acceptable_answers"] == ["limit"]
        subjective = next(item for item in draft["questions"] if item["planned_type"] == "short-answer")
        assert subjective["question"]["answer"]["scoring_points"]


def test_apply_stale_draft_revision_returns_conflict(tmp_path):
    client, _ = make_client(tmp_path, model_client=ExamFakeModel())
    with client:
        model_id, draft = _prepare_editable_draft(client)
        target = next(item for item in draft["questions"] if item.get("question"))
        proposed = client.post(f"/api/exam-drafts/{draft['id']}/revision-proposals", json={
            "instruction": "把这题改简单一点",
            "scope": {"kind": "questions", "question_ids": [target["id"]], "block_ids": []},
            "model_id": model_id,
        })
        assert proposed.status_code == 202
        assert wait_for_operation(client, proposed.json()["operation"]["id"])["status"] == "succeeded"
        proposal = next(
            item
            for item in client.get(f"/api/exam-drafts/{draft['id']}/revision-proposals").json()["items"]
            if item["status"] == "ready"
        )
        edited = copy.deepcopy(target["question"])
        edited["stem"][0]["text"] = "人工改过的题干"
        assert client.put(f"/api/exam-drafts/{draft['id']}/questions/{target['id']}", json=edited).status_code == 200
        applied = client.post(f"/api/draft-revision-proposals/{proposal['id']}/apply")
        assert applied.status_code == 409
        assert applied.json()["error"]["code"] in {"REVISION_PROPOSAL_STALE", "REVISION_PROPOSAL_INVALID"}


def test_second_draft_revision_blocked_while_generating(tmp_path):
    fake = WaitingRevisionFakeModel()
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        model_id, draft = _prepare_editable_draft(client)
        target = next(item for item in draft["questions"] if item.get("question"))
        payload = {
            "instruction": "把这题改简单一点",
            "scope": {"kind": "questions", "question_ids": [target["id"]], "block_ids": []},
            "model_id": model_id,
        }
        first = client.post(f"/api/exam-drafts/{draft['id']}/revision-proposals", json=payload)
        assert first.status_code == 202
        wait_for(lambda: fake.started.is_set())
        second = client.post(f"/api/exam-drafts/{draft['id']}/revision-proposals", json=payload)
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "OPERATION_IN_PROGRESS"
        fake.release.set()
        assert wait_for_operation(client, first.json()["operation"]["id"])["status"] == "succeeded"


def test_parse_blueprint_use_defaults_skips_model(tmp_path):
    fake = ImmediateFakeModelClient()
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id, _ = create_subject_and_model(client)
        posted = client.post(f"/api/subjects/{subject_id}/exam-blueprints", json={
            "prompt": "出一套练习卷",
            "grounding_mode": "general-knowledge",
            "use_defaults": True,
        })
        assert posted.status_code == 202
        assert wait_for_operation(client, posted.json()["operation"]["id"])["status"] == "succeeded"
        assert fake.chat_calls == []
        blueprint = client.get(f"/api/exam-blueprints/{posted.json()['resource']['id']}").json()
        assert blueprint["status"] == "draft"
        assert blueprint["question_plan"]
        assert blueprint["total_score"] == 100
        assert any(issue["code"] == "BLUEPRINT_USED_DEFAULTS" for issue in blueprint["issues"])


def test_parse_blueprint_falls_back_to_defaults_when_model_json_invalid(tmp_path):
    fake = ImmediateFakeModelClient(answer="这不是有效蓝图")
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id, model_id = create_subject_and_model(client)
        client.post(f"/api/subjects/{subject_id}/chat/model", json={"model_id": model_id})
        posted = client.post(f"/api/subjects/{subject_id}/exam-blueprints", json={
            "prompt": "生成一套比较简单的计网试卷",
            "grounding_mode": "general-knowledge",
            "model_id": model_id,
        })
        assert posted.status_code == 202
        assert wait_for_operation(client, posted.json()["operation"]["id"])["status"] == "succeeded"
        blueprint = client.get(f"/api/exam-blueprints/{posted.json()['resource']['id']}").json()
        assert blueprint["status"] == "draft"
        assert len(blueprint["question_plan"]) >= 1
        assert any(issue["code"] == "BLUEPRINT_USED_DEFAULTS" for issue in blueprint["issues"])


def test_generate_exam_bundle_keeps_choice_stems_distinct(tmp_path):
    fake = ExamFakeModel()
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        _, _, _, blueprint_id = build_exam(client)
        client.patch(f"/api/exam-blueprints/{blueprint_id}", json={
            "question_plan": [
                {"type": "single-choice", "count": 2, "difficulty": "easy", "score_each": 10},
            ],
            "total_score": 20,
        })
        assert client.post(f"/api/exam-blueprints/{blueprint_id}/confirm").status_code == 200
        generated = client.post(f"/api/exam-blueprints/{blueprint_id}/generate").json()
        assert wait_for_operation(client, generated["operation"]["id"])["status"] == "succeeded"
        bundle_prompts = _user_contents(fake, "一次生成整张试卷")
        assert bundle_prompts
        assert "不得重复" in bundle_prompts[0]
        draft = client.get(f"/api/exam-drafts/{generated['resource']['id']}").json()
        stems = [
            item["question"]["stem"][0]["text"]
            for item in draft["questions"]
            if item.get("question")
        ]
        assert len(stems) == 2
        assert stems[0] != stems[1]


def test_fill_in_question_sees_later_bundle_stems(tmp_path):
    fake = ExamFakeModel()
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        _, _, _, blueprint_id = build_exam(client)
        client.patch(f"/api/exam-blueprints/{blueprint_id}", json={
            "question_plan": [
                {"type": "single-choice", "count": 1, "difficulty": "easy", "score_each": 5},
                {"type": "fill-blank", "count": 1, "difficulty": "easy", "score_each": 5},
                {"type": "true-false", "count": 1, "difficulty": "easy", "score_each": 5},
            ],
            "total_score": 15,
        })
        assert client.post(f"/api/exam-blueprints/{blueprint_id}/confirm").status_code == 200
        generated = client.post(f"/api/exam-blueprints/{blueprint_id}/generate").json()
        assert wait_for_operation(client, generated["operation"]["id"])["status"] == "succeeded"
        fill_prompts = _user_contents(fake, "生成一道 fill-blank")
        assert fill_prompts
        prompt = fill_prompts[0]
        assert "A limit primarily describes what? (1)" in prompt
        assert "A limit can exist even when the point value differs." in prompt
