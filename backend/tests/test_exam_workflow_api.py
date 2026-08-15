import json
import re

from backend.tests.conftest import ImmediateFakeModelClient, make_client
from backend.tests.test_learning_api import create_subject_and_model
from backend.tests.test_sources_api import upload_source, wait_for_operation


class ExamFakeModel(ImmediateFakeModelClient):
    def __init__(self):
        super().__init__(answer="选区解释")
        self.fill_attempts = 0

    async def chat(self, profile, messages):
        self.chat_calls.append({"profile": profile, "messages": messages})
        content = messages[-1]["content"]
        if not isinstance(content, str):
            return {"text": "选区解释", "provider": profile["provider"], "model": profile["model"]}
        if "把组卷要求解析为 JSON" in content:
            result = {
                "title": "极限综合练习",
                "syllabus": ["Limits"],
                "question_plan": [
                    {"type": "single-choice", "count": 1, "difficulty": "easy", "score_each": 5},
                    {"type": "fill-blank", "count": 1, "difficulty": "easy", "score_each": 5},
                    {"type": "true-false", "count": 1, "difficulty": "medium", "score_each": 5},
                    {"type": "short-answer", "count": 1, "difficulty": "medium", "score_each": 5},
                ],
                "total_score": 20,
                "duration_minutes": 30,
            }
            return {"text": json.dumps(result), "provider": profile["provider"], "model": profile["model"]}
        if "生成一道 single-choice" in content:
            result = {
                "type": "single-choice",
                "stem": "A limit primarily describes what?",
                "options": [
                    {"id": "A", "content": "Nearby behavior"},
                    {"id": "B", "content": "Only the point value"},
                ],
                "answer": {"kind": "choice", "option_ids": ["A"]},
                "explanation": "Limits describe nearby behavior.",
                "knowledge_points": ["Limits"],
            }
        elif "生成一道 fill-blank" in content:
            self.fill_attempts += 1
            if self.fill_attempts == 1:
                return {"text": "{}", "provider": profile["provider"], "model": profile["model"]}
            result = {
                "type": "fill-blank",
                "stem": "The nearby behavior is described by a ____.",
                "answer": {
                    "kind": "fill-blank",
                    "blanks": [{"id": "blank-1", "acceptable_answers": ["limit", "Limit"]}],
                },
                "explanation": "The missing term is limit.",
                "knowledge_points": ["Limits"],
            }
        elif "生成一道 true-false" in content:
            result = {
                "type": "true-false",
                "stem": "A limit can exist even when the point value differs.",
                "answer": {"kind": "true-false", "value": True},
                "explanation": "A limit concerns nearby values.",
                "knowledge_points": ["Limits"],
            }
        elif "生成一道 short-answer" in content:
            result = {
                "type": "short-answer",
                "stem": "Explain what a limit describes.",
                "answer": {
                    "kind": "subjective",
                    "reference_answer": "It describes nearby behavior.",
                    "scoring_points": [{"id": "point-1", "description": "Mentions nearby behavior", "score": 5}],
                },
                "explanation": "Focus on values near the point.",
                "knowledge_points": ["Limits"],
            }
        elif "根据评分点评估答案" in content:
            points_text = re.search(r"评分点：(.*?)\n用户答案", content, re.S).group(1)
            point_id = json.loads(points_text)[0]["id"]
            result = {
                "status": "complete",
                "matched_point_ids": [point_id],
                "missed_point_ids": [],
                "reasoning_issues": [],
                "suggestions": ["表达可以更精确"],
                "suggested_score": 5,
            }
        elif "结构化差异预览" in content:
            result = {"changes": [{
                "path": "/title",
                "operation": "replace",
                "summary": "调整标题",
                "before": "极限综合练习",
                "after": "极限复习卷",
            }]}
        else:
            return {"text": "选区解释", "provider": profile["provider"], "model": profile["model"]}
        return {"text": json.dumps(result), "provider": profile["provider"], "model": profile["model"]}


def build_exam(client):
    subject_id, model_id = create_subject_and_model(client)
    client.post(f"/api/subjects/{subject_id}/chat/model", json={"model_id": model_id})
    uploaded = upload_source(
        client,
        subject_id,
        "limits.md",
        b"# Limits\n\nLimits describe nearby behavior. single-choice fill-blank true-false short-answer.",
    )
    version_id = wait_for_operation(client, uploaded.json()["operation"]["id"])["result"]["id"]
    parsed = client.post(f"/api/subjects/{subject_id}/exam-blueprints", json={
        "prompt": "Create a Limits exam",
        "grounding_mode": "strict",
        "source_version_ids": [version_id],
    })
    blueprint_id = parsed.json()["resource"]["id"]
    assert wait_for_operation(client, parsed.json()["operation"]["id"])["status"] == "succeeded"
    return subject_id, model_id, version_id, blueprint_id


def test_blueprint_draft_exam_attempt_and_selection_workflow(tmp_path):
    fake = ExamFakeModel()
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id, model_id, version_id, blueprint_id = build_exam(client)
        blueprint = client.get(f"/api/exam-blueprints/{blueprint_id}").json()
        assert blueprint["status"] == "draft"

        conflict = client.patch(f"/api/exam-blueprints/{blueprint_id}", json={"total_score": 21}).json()
        assert conflict["issues"][0]["severity"] == "error"
        blocked = client.post(f"/api/exam-blueprints/{blueprint_id}/confirm")
        assert blocked.status_code == 409
        client.patch(f"/api/exam-blueprints/{blueprint_id}", json={"total_score": 20})
        assert client.post(f"/api/exam-blueprints/{blueprint_id}/confirm").json()["status"] == "confirmed"

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
        original_document = exam["document"]

        attempt = client.post(f"/api/exams/{exam_id}/attempts", json={"mode": "exam"}).json()
        attempt_id = attempt["id"]
        assert all("answer" not in question and "explanation" not in question and "evidence" not in question for question in attempt["paper"]["questions"])
        choice = next(question for question in exam["document"]["questions"] if question["type"] == "single-choice")
        saved = client.put(f"/api/attempts/{attempt_id}/answers/{choice['id']}", json={
            "answer": {"kind": "choice", "option_ids": ["A"]},
        })
        assert saved.status_code == 200
        assert client.get(f"/api/attempts/{attempt_id}").json()["feedback"] == []
        assert client.get(f"/api/attempts/{attempt_id}/review").status_code == 409
        assert client.post(f"/api/attempts/{attempt_id}/pause").json()["status"] == "paused"
        assert client.post(f"/api/attempts/{attempt_id}/resume").json()["status"] == "in-progress"
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
