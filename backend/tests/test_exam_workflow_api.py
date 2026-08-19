import copy
import json
import re

from backend.tests.conftest import ImmediateFakeModelClient, make_client
from backend.tests.test_learning_api import create_subject_and_model
from backend.tests.test_sources_api import upload_source, wait_for_operation


class ExamFakeModel(ImmediateFakeModelClient):
    def __init__(self):
        super().__init__(answer="选区解释")
        self.fill_attempts = 0

    async def chat(self, profile, messages, max_tokens=None):
        self.chat_calls.append({"profile": profile, "messages": messages})
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
