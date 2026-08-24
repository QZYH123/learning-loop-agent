import copy
import json
import re

from backend.tests.conftest import make_client
from backend.tests.test_exam_workflow_api import (
    ExamFakeModel,
    _user_contents,
    build_exam,
    publish_exam_from_blueprint,
    publish_ready_exam,
)
from backend.tests.test_sources_api import wait_for_operation


class MissedQuestionsFake(ExamFakeModel):
    async def chat(self, profile, messages, max_tokens=None, tools=None, on_delta=None):
        content = messages[-1]["content"] if messages else ""
        if isinstance(content, str) and "根据评分点评估答案" in content:
            self.chat_calls.append({"profile": profile, "messages": messages, "tools": tools})
            points_text = re.search(r"评分点：(.*?)\n用户答案", content, re.S).group(1)
            points = json.loads(points_text)
            result = {
                "status": "complete",
                "matched_point_ids": [],
                "missed_point_ids": [item["id"] for item in points],
                "reasoning_issues": [],
                "suggestions": ["补上遗漏点"],
                "suggested_score": 0,
            }
            return {"text": json.dumps(result), "provider": profile["provider"], "model": profile["model"]}
        if isinstance(content, str) and "把组卷要求解析为 JSON" in content and "针对以下薄弱考点出一套复习卷" in content:
            self.chat_calls.append({"profile": profile, "messages": messages, "tools": tools})
            match = re.search(r"针对以下薄弱考点出一套复习卷：([^\n]+)", content)
            syllabus = [part.strip() for part in match.group(1).split("、") if part.strip()] if match else ["Limits"]
            result = {
                "title": "薄弱点复习卷",
                "syllabus": syllabus,
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
        return await super().chat(profile, messages, max_tokens=max_tokens, tools=tools)


def _walk_keys(value):
    if isinstance(value, dict):
        yield from value.keys()
        for child in value.values():
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _replace_points(client, exam_id, updates):
    current = client.get(f"/api/exams/{exam_id}").json()
    document = copy.deepcopy(current["document"])
    by_id = {item["id"]: item for item in document["questions"]}
    for question_id, points in updates.items():
        by_id[question_id]["knowledge_points"] = points
    replaced = client.put(
        f"/api/exams/{exam_id}",
        json={"base_version_id": current["current_version_id"], "document": document},
    )
    assert replaced.status_code == 200
    return replaced.json()


def _publish_second_exam(client, subject_id, version_id):
    parsed = client.post(
        f"/api/subjects/{subject_id}/exam-blueprints",
        json={
            "prompt": "Create another Limits exam",
            "grounding_mode": "strict",
            "source_version_ids": [version_id],
        },
    )
    blueprint_id = parsed.json()["resource"]["id"]
    assert wait_for_operation(client, parsed.json()["operation"]["id"])["status"] == "succeeded"
    return publish_exam_from_blueprint(client, blueprint_id)


def _answer_choice(client, exam_id, question_id, option_id):
    practice = client.post(f"/api/exams/{exam_id}/attempts", json={"mode": "practice"}).json()
    saved = client.put(
        f"/api/attempts/{practice['id']}/answers/{question_id}",
        json={"answer": {"kind": "choice", "option_ids": [option_id]}},
    )
    assert saved.status_code == 200
    return practice


def _wrong_choice(client, exam_id, question_id):
    return _answer_choice(client, exam_id, question_id, "B")


def _listed_question_ids(payload, knowledge_point=None):
    ids = []
    for group in payload["items"]:
        if knowledge_point is not None and group["knowledge_point"] != knowledge_point:
            continue
        ids.extend(item["question_id"] for item in group["questions"])
    return ids


def test_missed_questions_group_across_exams_and_hide_answers(tmp_path):
    fake = MissedQuestionsFake()
    client, app = make_client(tmp_path, model_client=fake)
    with client:
        subject_id, model_id, version_id, blueprint_id = build_exam(client)
        exam_a = publish_ready_exam(client, blueprint_id)
        exam_b = _publish_second_exam(client, subject_id, version_id)
        client.patch(f"/api/exams/{exam_a['id']}", json={"title": "卷一"})
        client.patch(f"/api/exams/{exam_b['id']}", json={"title": "卷二"})

        choice_a = next(item for item in exam_a["document"]["questions"] if item["type"] == "single-choice")
        choice_b = next(item for item in exam_b["document"]["questions"] if item["type"] == "single-choice")
        subjective = next(item for item in exam_b["document"]["questions"] if item["type"] == "short-answer")
        exam_a = _replace_points(client, exam_a["id"], {choice_a["id"]: ["Limits"]})
        exam_b = _replace_points(client, exam_b["id"], {choice_b["id"]: ["Limits"], subjective["id"]: ["Continuity"]})
        choice_a = next(item for item in exam_a["document"]["questions"] if item["id"] == choice_a["id"])
        choice_b = next(item for item in exam_b["document"]["questions"] if item["id"] == choice_b["id"])
        subjective = next(item for item in exam_b["document"]["questions"] if item["id"] == subjective["id"])

        first = _wrong_choice(client, exam_a["id"], choice_a["id"])
        _wrong_choice(client, exam_a["id"], choice_a["id"])
        practice_b = client.post(f"/api/exams/{exam_b['id']}/attempts", json={"mode": "practice"}).json()
        assert client.put(
            f"/api/attempts/{practice_b['id']}/answers/{choice_b['id']}",
            json={"answer": {"kind": "choice", "option_ids": ["B"]}},
        ).status_code == 200
        assert client.put(
            f"/api/attempts/{practice_b['id']}/answers/{subjective['id']}",
            json={"answer": {"kind": "text", "text": "incomplete"}},
        ).status_code == 200
        feedback = client.post(
            f"/api/attempts/{practice_b['id']}/answers/{subjective['id']}/feedback",
            json={"model_id": model_id},
        )
        assert wait_for_operation(client, feedback.json()["operation"]["id"])["status"] == "succeeded"

        exam_attempt = client.post(f"/api/exams/{exam_a['id']}/attempts", json={"mode": "exam"}).json()
        client.put(
            f"/api/attempts/{exam_attempt['id']}/answers/{choice_a['id']}",
            json={"answer": {"kind": "choice", "option_ids": ["B"]}},
        )

        listed = client.get(f"/api/subjects/{subject_id}/missed-questions")
        assert listed.status_code == 200
        payload = listed.json()
        keys = set(_walk_keys(payload))
        assert keys.isdisjoint({"option_ids", "answer", "matched_points", "feedback", "paper"})

        groups = {item["knowledge_point"]: item for item in payload["items"]}
        assert groups["Limits"]["miss_count"] == 2
        assert groups["Continuity"]["miss_count"] == 1
        limit_exams = {item["exam_title"] for item in groups["Limits"]["questions"]}
        assert limit_exams == {"卷一", "卷二"}
        continuity = groups["Continuity"]["questions"][0]
        assert continuity["exam_title"] == "卷二"
        assert continuity["question_type"] == "short-answer"
        assert continuity["question_id"] == subjective["id"]

        limit_attempts = {item["attempt_id"] for item in groups["Limits"]["questions"] if item["exam_id"] == exam_a["id"]}
        assert first["id"] not in limit_attempts
        assert exam_attempt["id"] not in {item["attempt_id"] for group in payload["items"] for item in group["questions"]}

        for group in payload["items"]:
            for item in group["questions"]:
                assert len(item["stem_preview"]) <= 80

        parsed = client.post(
            f"/api/subjects/{subject_id}/exam-blueprints",
            json={
                "prompt": "针对以下薄弱考点出一套复习卷：Limits、Continuity",
                "grounding_mode": "strict",
                "source_version_ids": [version_id],
            },
        )
        assert wait_for_operation(client, parsed.json()["operation"]["id"])["status"] == "succeeded"
        content = _user_contents(fake, "把组卷要求解析为 JSON")[-1]
        assert "针对以下薄弱考点出一套复习卷：Limits、Continuity" in content
        assert "Algebra" not in content.split("用户要求：", 1)[1].split("参考错点", 1)[0]
        blueprint = client.get(f"/api/exam-blueprints/{parsed.json()['resource']['id']}").json()
        assert blueprint["syllabus"] == ["Limits", "Continuity"]

        def clear_points(data):
            for version in data.get("exam_versions", []):
                if version.get("exam_id") != exam_a["id"]:
                    continue
                for question in version.get("document", {}).get("questions", []):
                    if question["id"] == choice_a["id"]:
                        question["knowledge_points"] = []
            return data

        app.state.learning_service.workspace_service.update_subject_data(subject_id, clear_points)
        unmarked = client.get(f"/api/subjects/{subject_id}/missed-questions").json()
        names = [item["knowledge_point"] for item in unmarked["items"]]
        assert "未标考点" in names


def test_later_correct_attempt_drops_same_question(tmp_path):
    client, _ = make_client(tmp_path, model_client=MissedQuestionsFake())
    with client:
        subject_id, _, _, blueprint_id = build_exam(client)
        exam = publish_ready_exam(client, blueprint_id)
        choice = next(item for item in exam["document"]["questions"] if item["type"] == "single-choice")
        exam = _replace_points(client, exam["id"], {choice["id"]: ["Limits"]})
        choice = next(item for item in exam["document"]["questions"] if item["id"] == choice["id"])

        _wrong_choice(client, exam["id"], choice["id"])
        listed = client.get(f"/api/subjects/{subject_id}/missed-questions").json()
        assert choice["id"] in _listed_question_ids(listed, "Limits")

        _answer_choice(client, exam["id"], choice["id"], "A")
        listed = client.get(f"/api/subjects/{subject_id}/missed-questions").json()
        assert choice["id"] not in _listed_question_ids(listed)


def test_later_correct_on_same_point_drops_earlier_miss(tmp_path):
    client, _ = make_client(tmp_path, model_client=MissedQuestionsFake())
    with client:
        subject_id, _, version_id, blueprint_id = build_exam(client)
        exam_a = publish_ready_exam(client, blueprint_id)
        exam_b = _publish_second_exam(client, subject_id, version_id)
        choice_a = next(item for item in exam_a["document"]["questions"] if item["type"] == "single-choice")
        choice_b = next(item for item in exam_b["document"]["questions"] if item["type"] == "single-choice")
        exam_a = _replace_points(client, exam_a["id"], {choice_a["id"]: ["Limits"]})
        exam_b = _replace_points(client, exam_b["id"], {choice_b["id"]: ["Limits"]})
        choice_a = next(item for item in exam_a["document"]["questions"] if item["id"] == choice_a["id"])
        choice_b = next(item for item in exam_b["document"]["questions"] if item["id"] == choice_b["id"])

        _wrong_choice(client, exam_a["id"], choice_a["id"])
        _answer_choice(client, exam_b["id"], choice_b["id"], "A")

        listed = client.get(f"/api/subjects/{subject_id}/missed-questions").json()
        assert choice_a["id"] not in _listed_question_ids(listed, "Limits")
        assert "Limits" not in {item["knowledge_point"] for item in listed["items"]}


def test_missed_questions_unknown_subject_is_404(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        response = client.get("/api/subjects/missing/missed-questions")
        assert response.status_code == 404
