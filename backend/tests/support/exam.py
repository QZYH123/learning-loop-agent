import copy
import json
import re

from backend.tests.conftest import ImmediateFakeModelClient
from backend.tests.support.bootstrap import create_subject_and_model
from backend.tests.support.http import upload_source, wait_for_operation


class ExamFakeModel(ImmediateFakeModelClient):
    def __init__(self):
        super().__init__(answer="选区解释")
        self.fill_attempts = 0

    async def chat(self, profile, messages, max_tokens=None, tools=None, on_delta=None):
        self.chat_calls.append({"profile": profile, "messages": messages, "tools": tools})
        content = messages[-1]["content"]
        if not isinstance(content, str):
            return {"text": "选区解释", "provider": profile["provider"], "model": profile["model"]}
        if "回答 2 + 2" in content:
            return {"text": json.dumps({"answer": "4"}), "provider": profile["provider"], "model": profile["model"]}
        if "资料 [source-limit]" in content:
            return {
                "text": json.dumps({"answer": "极限描述附近行为", "citation_ids": ["source-limit"]}),
                "provider": profile["provider"],
                "model": profile["model"],
            }
        if "题目版选择题" in content:
            return {
                "text": json.dumps({
                    "type": "single-choice",
                    "stem": "2 + 2 = ?",
                    "options": ["3", "4"],
                    "score": 2,
                    "answer_area": {"lines": 0},
                }),
                "provider": profile["provider"],
                "model": profile["model"],
            }
        if "完整选择题" in content:
            return {
                "text": json.dumps({
                    "type": "single-choice",
                    "stem": "2 + 2 = ?",
                    "options": ["3", "4"],
                    "answer": "4",
                    "explanation": "基础加法",
                    "knowledge_points": ["加法"],
                }),
                "provider": profile["provider"],
                "model": profile["model"],
            }
        if "评分点 point-nearby" in content:
            return {
                "text": json.dumps({"matched_point_ids": ["point-nearby"], "missed_point_ids": []}),
                "provider": profile["provider"],
                "model": profile["model"],
            }
        if "一次生成整张试卷" in content:
            try:
                plan = json.loads(content.split("槽位：", 1)[1].split("\n", 1)[0])
            except (json.JSONDecodeError, IndexError, TypeError):
                plan = []
            questions = []
            for item in plan:
                qtype = item.get("type")
                if qtype == "fill-blank":
                    continue
                if qtype == "single-choice":
                    questions.append({
                        "id": item["id"],
                        "type": "single-choice",
                        "stem": f"A limit primarily describes what? ({item['ordinal']})",
                        "options": [
                            {"id": "A", "content": "Nearby behavior"},
                            {"id": "B", "content": "Only the point value"},
                        ],
                        "answer": {"kind": "choice", "option_ids": ["A"]},
                        "explanation": "Limits describe nearby behavior.",
                        "knowledge_points": ["Limits", f"point-{item['ordinal']}"],
                    })
                elif qtype == "true-false":
                    questions.append({
                        "id": item["id"],
                        "type": "true-false",
                        "stem": "A limit can exist even when the point value differs.",
                        "answer": {"kind": "true-false", "value": True},
                        "explanation": "A limit concerns nearby values.",
                        "knowledge_points": ["Limits"],
                    })
                elif qtype == "short-answer":
                    questions.append({
                        "id": item["id"],
                        "type": "short-answer",
                        "stem": "Explain what a limit describes.",
                        "answer": {
                            "kind": "subjective",
                            "reference_answer": "It describes nearby behavior.",
                            "scoring_points": [{"id": "point-1", "description": "Mentions nearby behavior", "score": 5}],
                        },
                        "explanation": "Focus on values near the point.",
                        "knowledge_points": ["Limits"],
                    })
            return {"text": json.dumps({"questions": questions}), "provider": profile["provider"], "model": profile["model"]}
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
            document = json.loads(content.split("试卷：", 1)[1].split("\n\n指令：", 1)[0])
            scope = {}
            if "修改范围：" in content:
                try:
                    scope = json.loads(content.split("修改范围：", 1)[1].split("\n", 1)[0])
                except json.JSONDecodeError:
                    scope = {}
            if scope.get("kind") == "questions" and scope.get("question_ids"):
                question_id = scope["question_ids"][0]
                index, question = next(
                    (idx, item)
                    for idx, item in enumerate(document["questions"])
                    if item["id"] == question_id
                )
                stem = question["stem"]
                after = copy.deepcopy(stem) if isinstance(stem, list) and stem else []
                if after and isinstance(after[0], dict) and after[0].get("type") == "markdown":
                    after[0]["text"] = "改写后的题干"
                else:
                    after = [{"id": "stem-revised", "type": "markdown", "text": "改写后的题干"}]
                result = {"changes": [{
                    "path": f"/questions/{index}/stem",
                    "operation": "replace",
                    "summary": "按指令改题",
                    "before": stem,
                    "after": after,
                }]}
            else:
                result = {"changes": [{
                    "path": "/title",
                    "operation": "replace",
                    "summary": "调整标题",
                    "before": document["title"],
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


def publish_ready_exam(client, blueprint_id):
    client.patch(f"/api/exam-blueprints/{blueprint_id}", json={"total_score": 20})
    assert client.post(f"/api/exam-blueprints/{blueprint_id}/confirm").json()["status"] == "confirmed"
    generated = client.post(f"/api/exam-blueprints/{blueprint_id}/generate")
    draft_id = generated.json()["resource"]["id"]
    assert wait_for_operation(client, generated.json()["operation"]["id"])["status"] == "succeeded"
    draft = client.get(f"/api/exam-drafts/{draft_id}").json()
    failed_id = next(item["id"] for item in draft["questions"] if item["status"] == "needs-review")
    retried = client.post(f"/api/exam-drafts/{draft_id}/questions/{failed_id}/retry")
    assert wait_for_operation(client, retried.json()["operation"]["id"])["status"] == "succeeded"
    published = client.post(f"/api/exam-drafts/{draft_id}/publish", json={})
    assert published.status_code == 201
    return published.json()


def prepare_editable_draft(client):
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
    return model_id, client.get(f"/api/exam-drafts/{draft_id}").json()


_prepare_editable_draft = prepare_editable_draft
