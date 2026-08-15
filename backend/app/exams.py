"""Exam blueprint, draft generation, attempts, and feedback services."""
from __future__ import annotations

import asyncio
import copy
import json
import math
import time
import uuid

from pydantic import ValidationError

from .exam_models import QuestionInput
from .learning import LearningError
from .model_client import ModelClientError
from .operations import OperationFailure
from .sources import SourceLibraryError


class ExamService:
    def __init__(self, learning, now=None, id_factory=None):
        self.learning = learning
        self.workspace = learning.workspace_service
        self.sources = learning.source_library
        self.operations = learning.operations
        self.model_client = learning.model_client
        self._now = now or (lambda: int(time.time() * 1000))
        self._ids = id_factory or (lambda prefix: f"{prefix}-{uuid.uuid4().hex}")
        self._recover_interrupted_resources()

    # Blueprints ----------------------------------------------------------

    def list_blueprints(self, subject_id: str) -> list[dict]:
        return self.learning._subject(subject_id).get("data", {}).get("exam_blueprints", [])

    def get_blueprint(self, blueprint_id: str) -> dict:
        return self.learning._find_owned("exam_blueprints", blueprint_id)[1]

    def parse_blueprint(self, subject_id: str, payload: dict) -> dict:
        self.learning._subject(subject_id)
        source_ids = payload.get("source_version_ids", [])
        self.learning._validate_source_scope(subject_id, source_ids, payload["grounding_mode"])
        profile = self._selected_model(subject_id, payload.get("model_id"))
        timestamp = self._now()
        blueprint_id = self._ids("blueprint")
        blueprint = {
            "id": blueprint_id,
            "subject_id": subject_id,
            "prompt": payload["prompt"],
            "title": "正在解析组卷要求",
            "status": "parsing",
            "syllabus": [],
            "source_version_ids": source_ids,
            "grounding_mode": payload["grounding_mode"],
            "question_plan": [],
            "total_score": 1.0,
            "duration_minutes": None,
            "issues": [],
            "confirmed_at": None,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        self._append(subject_id, "exam_blueprints", blueprint)

        async def worker():
            try:
                anchors = [] if payload["grounding_mode"] == "general-knowledge" else self.sources.retrieve(payload["prompt"], source_ids, limit=12)
                if payload["grounding_mode"] == "strict" and not anchors:
                    raise OperationFailure("GROUNDING_SOURCE_REQUIRED", "选定资料未覆盖组卷要求")
                context = self.learning._anchors_text(anchors)
                response = await self.model_client.chat(profile, [{
                    "role": "user",
                    "content": (
                        "把组卷要求解析为 JSON，只返回："
                        '{"title":"...","syllabus":["..."],"question_plan":['
                        '{"type":"single-choice","count":1,"difficulty":"medium","score_each":5}],'
                        '"total_score":5,"duration_minutes":30}。题型可用 single-choice、multiple-choice、fill-blank、'
                        "true-false、short-answer、argumentation、extended-response。\n\n"
                        f"用户要求：{payload['prompt']}\n\n相关资料：\n{context or '无'}"
                    ),
                }])
                parsed = json.loads(response["text"])
                plan = [self._normalize_plan(item) for item in parsed["question_plan"]]
                total_score = float(parsed["total_score"])
                issues = self._blueprint_issues(plan, total_score)
                updated = {
                    **blueprint,
                    "title": parsed["title"],
                    "status": "draft",
                    "syllabus": parsed.get("syllabus", []),
                    "question_plan": plan,
                    "total_score": total_score,
                    "duration_minutes": parsed.get("duration_minutes"),
                    "issues": issues,
                    "updated_at": self._now(),
                }
                self._replace(subject_id, "exam_blueprints", blueprint_id, updated)
                return {"type": "exam-blueprint", "id": blueprint_id}
            except OperationFailure:
                self._fail_blueprint(subject_id, blueprint, "选定资料未覆盖组卷要求")
                raise
            except (ModelClientError, SourceLibraryError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                self._fail_blueprint(subject_id, blueprint, "模型未返回有效的组卷蓝图")
                raise OperationFailure("MODEL_INVALID_RESPONSE", "模型未返回有效的组卷蓝图") from exc

        resource = {"type": "exam-blueprint", "id": blueprint_id}
        operation = self.operations.start("blueprint-parsing", worker, subject_id=subject_id, resource=resource)
        return {"operation": operation, "resource": resource}

    def update_blueprint(self, blueprint_id: str, patch: dict) -> dict:
        subject, blueprint = self.learning._find_owned("exam_blueprints", blueprint_id)
        source_ids = patch.get("source_version_ids", blueprint["source_version_ids"])
        grounding_mode = patch.get("grounding_mode", blueprint["grounding_mode"])
        self.learning._validate_source_scope(subject["id"], source_ids, grounding_mode)
        plan = patch.get("question_plan", blueprint["question_plan"])
        total_score = float(patch.get("total_score", blueprint["total_score"]))
        updated = {
            **blueprint,
            **patch,
            "source_version_ids": source_ids,
            "grounding_mode": grounding_mode,
            "question_plan": plan,
            "total_score": total_score,
            "status": "draft",
            "issues": self._blueprint_issues(plan, total_score),
            "confirmed_at": None,
            "updated_at": self._now(),
        }
        self._replace(subject["id"], "exam_blueprints", blueprint_id, updated)
        return updated

    def confirm_blueprint(self, blueprint_id: str) -> dict:
        subject, blueprint = self.learning._find_owned("exam_blueprints", blueprint_id)
        if blueprint["status"] not in {"draft", "confirmed"}:
            raise LearningError(409, "RESOURCE_CONFLICT", "当前蓝图无法确认")
        if any(issue["severity"] == "error" for issue in blueprint["issues"]):
            raise LearningError(409, "BLUEPRINT_CONSTRAINT_CONFLICT", "蓝图存在题量或分值冲突")
        updated = {**blueprint, "status": "confirmed", "confirmed_at": self._now(), "updated_at": self._now()}
        self._replace(subject["id"], "exam_blueprints", blueprint_id, updated)
        return updated

    def delete_blueprint(self, blueprint_id: str) -> None:
        subject, _ = self.learning._find_owned("exam_blueprints", blueprint_id)
        if any(item.get("blueprint_id") == blueprint_id for item in subject.get("data", {}).get("exam_drafts", [])):
            raise LearningError(409, "RESOURCE_CONFLICT", "该蓝图已被试卷草稿引用")
        self._remove(subject["id"], "exam_blueprints", blueprint_id)

    # Draft generation ----------------------------------------------------

    def generate_draft(self, blueprint_id: str) -> dict:
        subject, blueprint = self.learning._find_owned("exam_blueprints", blueprint_id)
        if blueprint["status"] != "confirmed":
            raise LearningError(409, "BLUEPRINT_NOT_CONFIRMED", "请先确认组卷蓝图")
        if any(item.get("blueprint_id") == blueprint_id and item["status"] != "published" for item in subject.get("data", {}).get("exam_drafts", [])):
            raise LearningError(409, "OPERATION_IN_PROGRESS", "该蓝图已有试卷草稿")
        profile = self._selected_model(subject["id"], None)
        timestamp = self._now()
        draft_id = self._ids("exam-draft")
        slots = []
        ordinal = 1
        for plan in blueprint["question_plan"]:
            for _ in range(plan["count"]):
                slots.append({
                    "id": self._ids("question"),
                    "ordinal": ordinal,
                    "planned_type": plan["type"],
                    "planned_difficulty": plan["difficulty"],
                    "planned_score": plan["score_each"],
                    "status": "queued",
                    "question": None,
                    "error": None,
                    "updated_at": timestamp,
                })
                ordinal += 1
        draft = {
            "id": draft_id,
            "subject_id": subject["id"],
            "blueprint_id": blueprint_id,
            "title": blueprint["title"],
            "instructions": [],
            "status": "generating",
            "questions": slots,
            "total_score": blueprint["total_score"],
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        self._append(subject["id"], "exam_drafts", draft)
        operation_holder = {}

        async def worker():
            completed = 0
            for slot in slots:
                self._update_slot(subject["id"], draft_id, slot["id"], {"status": "generating", "updated_at": self._now()})
                try:
                    question = await self._generate_question(profile, blueprint, slot)
                    status = "complete" if question["reliability"] == "reliable" else "needs-review"
                    self._update_slot(subject["id"], draft_id, slot["id"], {
                        "status": status,
                        "question": question,
                        "error": None,
                        "updated_at": self._now(),
                    })
                except json.JSONDecodeError as exc:
                    self._update_slot(subject["id"], draft_id, slot["id"], {
                        "status": "failed",
                        "question": None,
                        "error": {
                            "code": "QUESTION_GENERATION_FAILED",
                            "message": str(exc) or "题目生成失败",
                            "retryable": True,
                            "details": {},
                        },
                        "updated_at": self._now(),
                    })
                except (LearningError, ValidationError, KeyError, TypeError, ValueError) as exc:
                    self._update_slot(subject["id"], draft_id, slot["id"], {
                        "status": "needs-review",
                        "question": None,
                        "error": {
                            "code": "QUESTION_STRUCTURE_INVALID",
                            "message": str(exc) or "题目结构不完整",
                            "retryable": True,
                            "details": {},
                        },
                        "updated_at": self._now(),
                    })
                except (ModelClientError, SourceLibraryError) as exc:
                    self._update_slot(subject["id"], draft_id, slot["id"], {
                        "status": "failed",
                        "question": None,
                        "error": {
                            "code": "QUESTION_GENERATION_FAILED",
                            "message": str(exc) or "题目生成失败",
                            "retryable": True,
                            "details": {},
                        },
                        "updated_at": self._now(),
                    })
                completed += 1
                self.operations.update_progress(operation_holder["id"], completed, len(slots), f"已生成 {completed}/{len(slots)} 题")
            current = self.learning._find_owned("exam_drafts", draft_id)[1]
            final_status = "failed" if all(item["status"] == "failed" for item in current["questions"]) else "editable"
            self._replace(subject["id"], "exam_drafts", draft_id, {**current, "status": final_status, "updated_at": self._now()})
            return {"type": "exam-draft", "id": draft_id}

        resource = {"type": "exam-draft", "id": draft_id}
        operation = self.operations.start(
            "exam-generation",
            worker,
            subject_id=subject["id"],
            resource=resource,
            total=len(slots),
        )
        operation_holder["id"] = operation["id"]
        return {"operation": operation, "resource": resource}

    def list_drafts(self, subject_id: str) -> list[dict]:
        return [self._draft_view(item) for item in self.learning._subject(subject_id).get("data", {}).get("exam_drafts", [])]

    def get_draft(self, draft_id: str) -> dict:
        return self._draft_view(self.learning._find_owned("exam_drafts", draft_id)[1])

    def update_draft(self, draft_id: str, patch: dict) -> dict:
        subject, draft = self.learning._find_owned("exam_drafts", draft_id)
        if draft["status"] in {"generating", "published"}:
            raise LearningError(409, "RESOURCE_CONFLICT", "当前试卷草稿不可编辑")
        if "question_order" in patch:
            order = patch.pop("question_order")
            by_id = {item["id"]: item for item in draft["questions"]}
            if set(order) != set(by_id):
                raise LearningError(422, "VALIDATION_FAILED", "题目顺序必须包含当前全部题目")
            patch["questions"] = [{**by_id[item_id], "ordinal": index + 1} for index, item_id in enumerate(order)]
        updated = {**draft, **patch, "updated_at": self._now()}
        self._replace(subject["id"], "exam_drafts", draft_id, updated)
        return self._draft_view(updated)

    def delete_draft(self, draft_id: str) -> None:
        subject, draft = self.learning._find_owned("exam_drafts", draft_id)
        if draft["status"] == "generating":
            raise LearningError(409, "OPERATION_IN_PROGRESS", "试卷草稿仍在生成")
        self._remove(subject["id"], "exam_drafts", draft_id)

    def replace_draft_question(self, draft_id: str, question_id: str, question: dict) -> dict:
        subject, draft = self.learning._find_owned("exam_drafts", draft_id)
        slot = next((item for item in draft["questions"] if item["id"] == question_id), None)
        if not slot:
            raise LearningError(404, "RESOURCE_NOT_FOUND", "题目不存在")
        if draft["status"] in {"generating", "published"}:
            raise LearningError(409, "RESOURCE_CONFLICT", "当前试卷草稿不可编辑")
        normalized = self._validate_manual_question(question, question_id)
        status = "complete" if normalized["reliability"] == "reliable" else "needs-review"
        updated_slot = {**self._slot_view(slot), "planned_type": normalized["type"], "status": status, "question": normalized, "error": None, "updated_at": self._now()}
        self._update_slot(subject["id"], draft_id, question_id, updated_slot)
        return updated_slot

    def delete_draft_question(self, draft_id: str, question_id: str) -> None:
        subject, draft = self.learning._find_owned("exam_drafts", draft_id)
        if draft["status"] in {"generating", "published"}:
            raise LearningError(409, "RESOURCE_CONFLICT", "当前试卷草稿不可编辑")
        if not any(item["id"] == question_id for item in draft["questions"]):
            raise LearningError(404, "RESOURCE_NOT_FOUND", "题目不存在")
        questions = [item for item in draft["questions"] if item["id"] != question_id]
        questions = [{**item, "ordinal": index + 1} for index, item in enumerate(questions)]
        self._replace(subject["id"], "exam_drafts", draft_id, {**draft, "questions": questions, "total_score": self._draft_score(questions), "updated_at": self._now()})

    def retry_question(self, draft_id: str, question_id: str) -> dict:
        subject, draft = self.learning._find_owned("exam_drafts", draft_id)
        slot = next((item for item in draft["questions"] if item["id"] == question_id), None)
        if not slot:
            raise LearningError(404, "RESOURCE_NOT_FOUND", "题目不存在")
        if slot["status"] in {"queued", "generating"}:
            raise LearningError(409, "OPERATION_IN_PROGRESS", "该题仍在生成")
        blueprint = self.get_blueprint(draft["blueprint_id"])
        profile = self._selected_model(subject["id"], None)
        self._update_slot(subject["id"], draft_id, question_id, {"status": "queued", "error": None, "updated_at": self._now()})

        async def worker():
            self._update_slot(subject["id"], draft_id, question_id, {"status": "generating", "updated_at": self._now()})
            try:
                question = await self._generate_question(profile, blueprint, slot)
            except json.JSONDecodeError as exc:
                self._update_slot(subject["id"], draft_id, question_id, {
                    "status": "failed",
                    "question": None,
                    "error": {"code": "QUESTION_GENERATION_FAILED", "message": str(exc), "retryable": True, "details": {}},
                    "updated_at": self._now(),
                })
                raise OperationFailure("QUESTION_GENERATION_FAILED", "题目生成失败", retryable=True) from exc
            except (LearningError, ValidationError, KeyError, TypeError, ValueError) as exc:
                self._update_slot(subject["id"], draft_id, question_id, {
                    "status": "needs-review",
                    "question": None,
                    "error": {"code": "QUESTION_STRUCTURE_INVALID", "message": str(exc), "retryable": True, "details": {}},
                    "updated_at": self._now(),
                })
                raise OperationFailure("QUESTION_STRUCTURE_INVALID", "题目结构不完整", retryable=True) from exc
            except (ModelClientError, SourceLibraryError) as exc:
                self._update_slot(subject["id"], draft_id, question_id, {
                    "status": "failed",
                    "question": None,
                    "error": {"code": "QUESTION_GENERATION_FAILED", "message": str(exc), "retryable": True, "details": {}},
                    "updated_at": self._now(),
                })
                raise OperationFailure("QUESTION_GENERATION_FAILED", "题目生成失败", retryable=True) from exc
            status = "complete" if question["reliability"] == "reliable" else "needs-review"
            self._update_slot(subject["id"], draft_id, question_id, {"status": status, "question": question, "error": None, "updated_at": self._now()})
            return {"type": "question", "id": question_id}

        resource = {"type": "question", "id": question_id}
        operation = self.operations.start("question-retry", worker, subject_id=subject["id"], resource=resource)
        return {"operation": operation, "resource": resource}

    def publish_draft(self, draft_id: str, accept_needs_review: bool) -> dict:
        subject, draft = self.learning._find_owned("exam_drafts", draft_id)
        if draft["status"] != "editable":
            raise LearningError(409, "RESOURCE_CONFLICT", "当前试卷草稿不可发布")
        incomplete = [item for item in draft["questions"] if item["status"] in {"failed", "needs-review"}]
        if incomplete and not accept_needs_review:
            raise LearningError(409, "QUESTION_EVIDENCE_INCOMPLETE", "草稿包含失败或待核查题目，请明确确认")
        if any(item.get("question") is None for item in draft["questions"]):
            raise LearningError(409, "QUESTION_STRUCTURE_INVALID", "草稿包含结构不完整的题目，不能发布")
        questions = [item["question"] for item in draft["questions"] if item.get("question")]
        if not questions:
            raise LearningError(409, "QUESTION_STRUCTURE_INVALID", "试卷没有可发布的题目")
        timestamp = self._now()
        exam_id = self._ids("exam")
        version_id = self._ids("exam-version")
        document = {"title": draft["title"], "instructions": draft["instructions"], "questions": questions}
        exam = {
            "id": exam_id,
            "subject_id": subject["id"],
            "source_blueprint_id": draft["blueprint_id"],
            "current_version_id": version_id,
            "document": document,
            "total_score": sum(item["score"] for item in questions),
            "can_undo": False,
            "can_redo": False,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        version = {
            "id": version_id,
            "exam_id": exam_id,
            "number": 1,
            "actor": "user",
            "summary": "发布试卷草稿",
            "model": None,
            "document": copy.deepcopy(document),
            "created_at": timestamp,
        }

        def update(data):
            return {
                **data,
                "exams": [*data.get("exams", []), exam],
                "exam_versions": [*data.get("exam_versions", []), version],
                "exam_drafts": [
                    {**item, "status": "published", "updated_at": timestamp} if item["id"] == draft_id else item
                    for item in data.get("exam_drafts", [])
                ],
            }
        self.learning._mutate(subject["id"], update)
        return exam

    # Exams and attempts --------------------------------------------------

    def list_exams(self, subject_id: str) -> list[dict]:
        return self.learning._subject(subject_id).get("data", {}).get("exams", [])

    def get_exam(self, exam_id: str) -> dict:
        return self.learning._find_owned("exams", exam_id)[1]

    def delete_exam(self, exam_id: str) -> None:
        subject, _ = self.learning._find_owned("exams", exam_id)
        if any(item.get("exam_id") == exam_id for item in subject.get("data", {}).get("attempts", [])):
            raise LearningError(409, "RESOURCE_CONFLICT", "试卷已有作答记录，不能删除")
        self._remove(subject["id"], "exams", exam_id)

    def create_attempt(self, exam_id: str, payload: dict) -> dict:
        subject, exam = self.learning._find_owned("exams", exam_id)
        timestamp = self._now()
        attempt_id = self._ids("attempt")
        document = self._version_document(subject, exam_id, exam["current_version_id"])
        paper = {
            "exam_id": exam_id,
            "exam_version_id": exam["current_version_id"],
            "title": document["title"],
            "instructions": document["instructions"],
            "questions": [
                {
                    "id": question["id"],
                    "ordinal": index + 1,
                    "type": question["type"],
                    "stem": question["stem"],
                    "options": question.get("options", []),
                    "score": question["score"],
                    "answer_area": question["answer_area"],
                }
                for index, question in enumerate(document["questions"])
            ],
            "total_score": sum(question["score"] for question in document["questions"]),
        }
        attempt = {
            "id": attempt_id,
            "exam_id": exam_id,
            "exam_version_id": exam["current_version_id"],
            "mode": payload["mode"],
            "status": "in-progress",
            "show_suggested_score": bool(payload.get("show_suggested_score")),
            "paper": paper,
            "answers": [],
            "feedback": [],
            "created_at": timestamp,
            "updated_at": timestamp,
            "submitted_at": None,
        }
        self._append(subject["id"], "attempts", attempt)
        return attempt

    def get_attempt(self, attempt_id: str) -> dict:
        return self.learning._find_owned("attempts", attempt_id)[1]

    def update_attempt(self, attempt_id: str, patch: dict) -> dict:
        subject, attempt = self.learning._find_owned("attempts", attempt_id)
        if attempt["status"] not in {"in-progress", "paused"}:
            raise LearningError(409, "ATTEMPT_STATE_CONFLICT", "已提交的作答不能修改设置")
        updated = {**attempt, **patch, "updated_at": self._now()}
        if updated["mode"] == "exam":
            updated["feedback"] = []
        self._replace(subject["id"], "attempts", attempt_id, updated)
        return updated

    def save_answer(self, attempt_id: str, question_id: str, answer: dict) -> dict:
        subject, attempt = self.learning._find_owned("attempts", attempt_id)
        if attempt["status"] != "in-progress":
            raise LearningError(409, "ATTEMPT_STATE_CONFLICT", "当前作答状态不能保存答案")
        question = self._attempt_question(subject, attempt, question_id)
        self._validate_answer_kind(question, answer)
        timestamp = self._now()
        existing = next((item for item in attempt["answers"] if item["question_id"] == question_id), None)
        saved = {
            "id": existing["id"] if existing else self._ids("answer"),
            "attempt_id": attempt_id,
            "question_id": question_id,
            "answer": answer,
            "saved_at": timestamp,
        }
        answers = [saved if item["question_id"] == question_id else item for item in attempt["answers"]]
        if not existing:
            answers.append(saved)
        feedback = attempt["feedback"]
        if attempt["mode"] == "practice" and question["type"] in {"single-choice", "multiple-choice", "fill-blank", "true-false"}:
            objective = self._objective_feedback(attempt, question, saved)
            feedback = [item for item in feedback if item["question_id"] != question_id] + [objective]
        updated = {**attempt, "answers": answers, "feedback": feedback, "updated_at": timestamp}
        self._replace(subject["id"], "attempts", attempt_id, updated)
        return saved

    def request_feedback(self, attempt_id: str, question_id: str, payload: dict) -> dict:
        subject, attempt = self.learning._find_owned("attempts", attempt_id)
        if attempt["mode"] == "exam" and attempt["status"] != "submitted":
            raise LearningError(409, "ANSWER_NOT_AVAILABLE", "考试模式提交前不能查看反馈")
        question = self._attempt_question(subject, attempt, question_id)
        answer = next((item for item in attempt["answers"] if item["question_id"] == question_id), None)
        if not answer:
            raise LearningError(409, "FEEDBACK_UNAVAILABLE", "请先保存答案")
        feedback_id = self._ids("feedback")
        resource = {"type": "feedback", "id": feedback_id}

        async def worker():
            try:
                if question["type"] in {"single-choice", "multiple-choice", "fill-blank", "true-false"}:
                    feedback = self._objective_feedback(attempt, question, answer, feedback_id=feedback_id)
                else:
                    profile = self._selected_model(subject["id"], payload.get("model_id"))
                    feedback = await self._subjective_feedback(
                        attempt,
                        question,
                        answer,
                        profile,
                        payload.get("show_suggested_score", attempt["show_suggested_score"]),
                        feedback_id,
                    )
                self._save_feedback(subject["id"], attempt_id, feedback)
                return resource
            except (LearningError, ModelClientError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                code = getattr(exc, "code", "MODEL_INVALID_RESPONSE")
                raise OperationFailure(code, str(exc) or "无法生成题目反馈") from exc

        operation = self.operations.start("subjective-feedback", worker, subject_id=subject["id"], resource=resource)
        return {"operation": operation, "resource": resource}

    def pause_attempt(self, attempt_id: str) -> dict:
        subject, attempt = self.learning._find_owned("attempts", attempt_id)
        if attempt["status"] != "in-progress":
            raise LearningError(409, "ATTEMPT_STATE_CONFLICT", "当前作答不能暂停")
        updated = {**attempt, "status": "paused", "updated_at": self._now()}
        self._replace(subject["id"], "attempts", attempt_id, updated)
        return updated

    def resume_attempt(self, attempt_id: str) -> dict:
        subject, attempt = self.learning._find_owned("attempts", attempt_id)
        if attempt["status"] != "paused":
            raise LearningError(409, "ATTEMPT_STATE_CONFLICT", "当前作答不在暂停状态")
        updated = {**attempt, "status": "in-progress", "updated_at": self._now()}
        self._replace(subject["id"], "attempts", attempt_id, updated)
        return updated

    def submit_attempt(self, attempt_id: str) -> dict:
        subject, attempt = self.learning._find_owned("attempts", attempt_id)
        if attempt["status"] not in {"in-progress", "paused"}:
            raise LearningError(409, "ATTEMPT_STATE_CONFLICT", "当前作答不能提交")
        grading = {**attempt, "status": "grading", "feedback": [], "updated_at": self._now()}
        self._replace(subject["id"], "attempts", attempt_id, grading)
        resource = {"type": "attempt", "id": attempt_id}

        async def worker():
            current = self.get_attempt(attempt_id)
            document = self._version_document(subject, current["exam_id"], current["exam_version_id"])
            feedback = []
            for question in document["questions"]:
                answer = next((item for item in current["answers"] if item["question_id"] == question["id"]), None)
                if not answer:
                    continue
                if question["type"] in {"single-choice", "multiple-choice", "fill-blank", "true-false"}:
                    feedback.append(self._objective_feedback(current, question, answer))
                else:
                    try:
                        profile = self._selected_model(subject["id"], None)
                        feedback.append(await self._subjective_feedback(
                            current,
                            question,
                            answer,
                            profile,
                            current["show_suggested_score"],
                            self._ids("feedback"),
                        ))
                    except (LearningError, ModelClientError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                        feedback.append(self._unable_feedback(current, question, answer))
            timestamp = self._now()
            submitted = {**current, "status": "submitted", "feedback": feedback, "updated_at": timestamp, "submitted_at": timestamp}
            self._replace(subject["id"], "attempts", attempt_id, submitted)
            return resource

        operation = self.operations.start("attempt-grading", worker, subject_id=subject["id"], resource=resource)
        return {"operation": operation, "resource": resource}

    def review_attempt(self, attempt_id: str) -> dict:
        subject, attempt = self.learning._find_owned("attempts", attempt_id)
        if attempt["mode"] == "exam" and attempt["status"] != "submitted":
            raise LearningError(409, "ANSWER_NOT_AVAILABLE", "考试模式提交前不能查看答案和解析")
        document = self._version_document(subject, attempt["exam_id"], attempt["exam_version_id"])
        feedback_by_question = {item["question_id"]: item for item in attempt["feedback"]}
        answers = {item["question_id"]: item for item in attempt["answers"]}
        questions = document["questions"]
        if attempt["mode"] == "practice" and attempt["status"] != "submitted":
            questions = [item for item in questions if item["id"] in feedback_by_question]
        scores = [item["suggested_score"] for item in feedback_by_question.values() if item.get("suggested_score") is not None]
        return {
            "attempt_id": attempt_id,
            "mode": attempt["mode"],
            "status": attempt["status"],
            "items": [
                {
                    "question": question,
                    "answer": answers.get(question["id"]),
                    "feedback": feedback_by_question.get(question["id"]),
                }
                for question in questions
            ],
            "total_suggested_score": sum(scores) if scores and attempt["show_suggested_score"] else None,
        }

    def create_revision_proposal(self, exam_id: str, payload: dict) -> dict:
        subject, exam = self.learning._find_owned("exams", exam_id)
        if payload["base_version_id"] != exam["current_version_id"]:
            raise LearningError(409, "EXAM_VERSION_CONFLICT", "试卷版本已变化，请基于最新版本重试")
        if payload.get("selection"):
            self.resolve_selection(payload["selection"])
        profile = self._selected_model(subject["id"], payload.get("model_id"))
        timestamp = self._now()
        proposal_id = self._ids("revision-proposal")
        proposal = {
            "id": proposal_id,
            "exam_id": exam_id,
            "base_version_id": payload["base_version_id"],
            "instruction": payload["instruction"],
            "scope": payload["scope"],
            "status": "generating",
            "changes": [],
            "model": self.learning._model_snapshot(profile),
            "error": None,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        self._append(subject["id"], "revision_proposals", proposal)
        resource = {"type": "revision-proposal", "id": proposal_id}

        async def worker():
            try:
                response = await self.model_client.chat(profile, [{
                    "role": "user",
                    "content": (
                        "根据修改指令生成结构化差异预览，只返回 JSON："
                        '{"changes":[{"path":"/title","operation":"replace","summary":"...","before":"...","after":"..."}]}。'
                        "不要直接应用修改。\n\n"
                        f"试卷：{json.dumps(exam['document'], ensure_ascii=False)}\n\n指令：{payload['instruction']}"
                    ),
                }])
                changes = json.loads(response["text"])["changes"]
                if not isinstance(changes, list) or not changes:
                    raise ValueError("changes is required")
                ready = {**proposal, "status": "ready", "changes": changes, "updated_at": self._now()}
                self._replace(subject["id"], "revision_proposals", proposal_id, ready)
                return resource
            except (ModelClientError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                failed = {
                    **proposal,
                    "status": "failed",
                    "error": {"code": "REVISION_PROPOSAL_INVALID", "message": "模型未返回有效修改提案", "retryable": True, "details": {}},
                    "updated_at": self._now(),
                }
                self._replace(subject["id"], "revision_proposals", proposal_id, failed)
                raise OperationFailure("REVISION_PROPOSAL_INVALID", "模型未返回有效修改提案", retryable=True) from exc

        operation = self.operations.start("exam-revision", worker, subject_id=subject["id"], resource=resource)
        return {"operation": operation, "resource": resource}

    # Selection -----------------------------------------------------------

    def resolve_selection(self, selection: dict) -> dict:
        kind = selection["document_kind"]
        if kind == "exam":
            subject, exam = self.learning._find_owned("exams", selection["document_id"])
            try:
                document = self._version_document(subject, exam["id"], selection["version_id"])
            except LearningError as exc:
                raise LearningError(409, "CHAT_SELECTION_INVALID", "试卷选区版本已失效") from exc
        elif kind == "exam-draft":
            _, draft = self.learning._find_owned("exam_drafts", selection["document_id"])
            if selection["version_id"] != draft["id"]:
                raise LearningError(409, "CHAT_SELECTION_INVALID", "试卷草稿选区版本已失效")
            document = {
                "questions": [item["question"] for item in draft["questions"] if item.get("question")],
                "instructions": draft["instructions"],
            }
        else:
            _, artifact = self.learning._find_owned("artifacts", selection["document_id"])
            if selection["version_id"] != artifact["id"]:
                raise LearningError(409, "CHAT_SELECTION_INVALID", "学习产物选区版本已失效")
            document = artifact

        serialized = json.dumps(document, ensure_ascii=False)
        if selection.get("question_id") and f'"id": "{selection["question_id"]}"' not in serialized:
            raise LearningError(409, "CHAT_SELECTION_INVALID", "选中的题目不属于该文档版本")
        if selection.get("block_id") and f'"id": "{selection["block_id"]}"' not in serialized:
            raise LearningError(409, "CHAT_SELECTION_INVALID", "选中的内容块不属于该文档版本")
        if selection.get("selected_text") and selection["selected_text"] not in serialized:
            raise LearningError(409, "CHAT_SELECTION_INVALID", "选中文字已不属于当前文档版本")
        asset = selection.get("image_asset")
        if asset and asset["asset_id"] not in serialized:
            raise LearningError(409, "CHAT_SELECTION_INVALID", "选中图片已不属于当前文档版本")
        for citation_id in selection.get("citation_ids", []):
            try:
                self.sources.get_citation(citation_id)
            except SourceLibraryError as exc:
                raise LearningError(409, "CHAT_SELECTION_INVALID", "选区引用已失效") from exc
        return selection

    # Question and grading helpers ---------------------------------------

    async def _generate_question(self, profile: dict, blueprint: dict, slot: dict) -> dict:
        query = " ".join([*blueprint.get("syllabus", []), slot["planned_type"]])
        anchors = [] if blueprint["grounding_mode"] == "general-knowledge" else self.sources.retrieve(query, blueprint["source_version_ids"], limit=5)
        if blueprint["grounding_mode"] == "strict" and not anchors:
            raise SourceLibraryError(409, "QUESTION_EVIDENCE_INCOMPLETE", "资料未覆盖该题目计划")
        citations = [self.sources.create_citation(anchor) for anchor in anchors]
        context = self.learning._anchors_text(anchors)
        response = await self.model_client.chat(profile, [{
            "role": "user",
            "content": (
                f"生成一道 {slot['planned_type']} 题，难度 {slot['planned_difficulty']}，分值 {slot['planned_score']}。"
                "只返回 JSON，字段为 type、stem、options（选择题）、answer、explanation、knowledge_points。"
                "answer.kind 按题型使用 choice、fill-blank、true-false 或 subjective。\n\n"
                f"资料片段：\n{context or '无'}"
            ),
        }])
        raw = json.loads(response["text"])
        return self._normalize_generated_question(raw, slot, citations, blueprint["grounding_mode"])

    def _normalize_generated_question(self, raw: dict, slot: dict, citations: list[dict], basis: str) -> dict:
        question_type = raw.get("type") or slot["planned_type"]
        if question_type != slot["planned_type"]:
            raise ValueError("generated question type does not match the plan")
        options = []
        if question_type in {"single-choice", "multiple-choice"}:
            options = []
            for index, item in enumerate(raw["options"]):
                option_id = item.get("id") if isinstance(item, dict) else chr(65 + index)
                content = item.get("content") if isinstance(item, dict) else item
                options.append({"id": option_id, "content": self._blocks(content)})
        answer = self._normalize_answer(raw["answer"], question_type)
        complete_evidence = bool(citations) or basis == "general-knowledge"
        question = {
            "id": slot["id"],
            "type": question_type,
            "stem": self._blocks(raw["stem"]),
            "options": options,
            "score": float(slot["planned_score"]),
            "answer_area": {"lines": 0 if question_type in {"single-choice", "multiple-choice", "true-false"} else 3 if question_type == "fill-blank" else 8},
            "answer": answer,
            "explanation": self._blocks(raw["explanation"]),
            "knowledge_points": raw["knowledge_points"],
            "evidence": {
                "basis": basis,
                "citations": citations,
                "status": "complete" if complete_evidence else "needs-review",
                "note": None if complete_evidence else "未找到足够的资料依据",
            },
            "reliability": "reliable" if complete_evidence else "needs-review",
        }
        return self._validate_manual_question(question, slot["id"])

    def _normalize_answer(self, answer: dict, question_type: str) -> dict:
        if question_type in {"single-choice", "multiple-choice"}:
            return {"kind": "choice", "option_ids": answer["option_ids"]}
        if question_type == "fill-blank":
            blanks = []
            for index, blank in enumerate(answer["blanks"]):
                blanks.append({
                    "id": blank.get("id") or f"blank-{index + 1}",
                    "acceptable_answers": blank["acceptable_answers"],
                    "normalization": blank.get("normalization") or {
                        "trim": True,
                        "case_sensitive": False,
                        "collapse_whitespace": True,
                    },
                })
            return {"kind": "fill-blank", "blanks": blanks}
        if question_type == "true-false":
            return {"kind": "true-false", "value": bool(answer["value"])}
        points = [
            {
                "id": point.get("id") or self._ids("scoring-point"),
                "description": point["description"],
                "score": float(point["score"]),
            }
            for point in answer["scoring_points"]
        ]
        return {"kind": "subjective", "reference_answer": self._blocks(answer["reference_answer"]), "scoring_points": points}

    def _validate_manual_question(self, question: dict, question_id: str) -> dict:
        candidate = {**question, "id": question_id}
        question_type = candidate["type"]
        expected = (
            "choice" if question_type in {"single-choice", "multiple-choice"}
            else "fill-blank" if question_type == "fill-blank"
            else "true-false" if question_type == "true-false"
            else "subjective"
        )
        if candidate["answer"]["kind"] != expected:
            raise LearningError(422, "QUESTION_STRUCTURE_INVALID", "题型与答案结构不一致")
        if expected == "choice":
            option_ids = {item["id"] for item in candidate.get("options") or []}
            if not option_ids or not set(candidate["answer"]["option_ids"]) <= option_ids:
                raise LearningError(422, "QUESTION_STRUCTURE_INVALID", "选择题答案引用了不存在的选项")
        validated = QuestionInput.model_validate(candidate).model_dump()
        if validated["evidence"]["status"] != "complete":
            validated["reliability"] = "needs-review"
        return validated

    def _objective_feedback(self, attempt: dict, question: dict, saved: dict, feedback_id: str | None = None) -> dict:
        correct = self._objective_correct(question["answer"], saved["answer"])
        return {
            "id": feedback_id or self._ids("feedback"),
            "attempt_id": attempt["id"],
            "question_id": question["id"],
            "answer_snapshot": copy.deepcopy(saved["answer"]),
            "status": "complete",
            "correct": correct,
            "matched_points": [],
            "missed_points": [],
            "reasoning_issues": [],
            "suggestions": [] if correct else ["对照解析检查答案"],
            "suggested_score": question["score"] if correct and attempt["show_suggested_score"] else 0 if attempt["show_suggested_score"] else None,
            "reference_answer": [],
            "evidence": question["evidence"],
            "model": None,
            "created_at": self._now(),
        }

    async def _subjective_feedback(self, attempt: dict, question: dict, saved: dict, profile: dict, show_score: bool, feedback_id: str) -> dict:
        points = question["answer"]["scoring_points"]
        response = await self.model_client.chat(profile, [{
            "role": "user",
            "content": (
                "根据评分点评估答案，只返回 JSON："
                '{"status":"complete","matched_point_ids":[],"missed_point_ids":[],"reasoning_issues":[],"suggestions":[],"suggested_score":0}。\n\n'
                f"评分点：{json.dumps(points, ensure_ascii=False)}\n用户答案：{saved['answer']['text']}"
            ),
        }])
        result = json.loads(response["text"])
        by_id = {item["id"]: item for item in points}
        matched_ids = result.get("matched_point_ids", [])
        missed_ids = result.get("missed_point_ids", [])
        matched = [by_id[item_id] for item_id in matched_ids if item_id in by_id]
        missed = [by_id[item_id] for item_id in missed_ids if item_id in by_id]
        covered = {item["id"] for item in [*matched, *missed]}
        status = result.get("status", "needs-review")
        if status != "unable-to-assess" and covered != set(by_id):
            status = "needs-review"
        suggested_score = result.get("suggested_score")
        return {
            "id": feedback_id,
            "attempt_id": attempt["id"],
            "question_id": question["id"],
            "answer_snapshot": copy.deepcopy(saved["answer"]),
            "status": status,
            "correct": None,
            "matched_points": matched,
            "missed_points": missed,
            "reasoning_issues": result.get("reasoning_issues", []),
            "suggestions": result.get("suggestions", []),
            "suggested_score": float(suggested_score) if show_score and suggested_score is not None and status != "unable-to-assess" else None,
            "reference_answer": question["answer"]["reference_answer"],
            "evidence": question["evidence"],
            "model": self.learning._model_snapshot(profile),
            "created_at": self._now(),
        }

    def _unable_feedback(self, attempt: dict, question: dict, saved: dict) -> dict:
        return {
            "id": self._ids("feedback"),
            "attempt_id": attempt["id"],
            "question_id": question["id"],
            "answer_snapshot": copy.deepcopy(saved["answer"]),
            "status": "unable-to-assess",
            "correct": None,
            "matched_points": [],
            "missed_points": question["answer"]["scoring_points"],
            "reasoning_issues": [],
            "suggestions": ["请选择模型后重新请求反馈"],
            "suggested_score": None,
            "reference_answer": question["answer"]["reference_answer"],
            "evidence": question["evidence"],
            "model": None,
            "created_at": self._now(),
        }

    @staticmethod
    def _objective_correct(answer_key: dict, answer: dict) -> bool:
        if answer_key["kind"] == "choice":
            return set(answer_key["option_ids"]) == set(answer["option_ids"])
        if answer_key["kind"] == "true-false":
            return answer_key["value"] is answer["value"]
        expected = {item["id"]: item for item in answer_key["blanks"]}
        actual = {item["blank_id"]: item["value"] for item in answer["blanks"]}
        if set(expected) != set(actual):
            return False
        for blank_id, definition in expected.items():
            value = ExamService._normalize_blank(actual[blank_id], definition["normalization"])
            acceptable = {
                ExamService._normalize_blank(item, definition["normalization"])
                for item in definition["acceptable_answers"]
            }
            if value not in acceptable:
                return False
        return True

    @staticmethod
    def _normalize_blank(value: str, rules: dict) -> str:
        if rules["trim"]:
            value = value.strip()
        if rules["collapse_whitespace"]:
            value = " ".join(value.split())
        if not rules["case_sensitive"]:
            value = value.casefold()
        return value

    def _validate_answer_kind(self, question: dict, answer: dict) -> None:
        expected = (
            "choice" if question["type"] in {"single-choice", "multiple-choice"}
            else "fill-blank" if question["type"] == "fill-blank"
            else "true-false" if question["type"] == "true-false"
            else "text"
        )
        if answer["kind"] != expected:
            raise LearningError(422, "ANSWER_TYPE_MISMATCH", "答案类型与题型不一致")

    def _attempt_question(self, subject: dict, attempt: dict, question_id: str) -> dict:
        document = self._version_document(subject, attempt["exam_id"], attempt["exam_version_id"])
        question = next((item for item in document["questions"] if item["id"] == question_id), None)
        if not question:
            raise LearningError(404, "RESOURCE_NOT_FOUND", "题目不存在")
        return question

    def _version_document(self, subject: dict, exam_id: str, version_id: str) -> dict:
        version = next(
            (item for item in subject.get("data", {}).get("exam_versions", []) if item["exam_id"] == exam_id and item["id"] == version_id),
            None,
        )
        if not version:
            raise LearningError(404, "RESOURCE_NOT_FOUND", "试卷版本不存在")
        return copy.deepcopy(version["document"])

    def _selected_model(self, subject_id: str, model_id: str | None) -> dict:
        selected = model_id or self.learning.get_chat(subject_id).get("active_model_id")
        if not selected:
            raise LearningError(409, "CHAT_MODEL_NOT_SELECTED", "请先选择模型服务")
        return self.learning._model(selected)

    def _save_feedback(self, subject_id: str, attempt_id: str, feedback: dict) -> None:
        _, attempt = self.learning._find_owned("attempts", attempt_id)
        updated = {
            **attempt,
            "feedback": [item for item in attempt["feedback"] if item["question_id"] != feedback["question_id"]] + [feedback],
            "updated_at": self._now(),
        }
        self._replace(subject_id, "attempts", attempt_id, updated)

    def _blocks(self, value) -> list[dict]:
        if isinstance(value, str):
            return [self.learning._markdown_block(value)]
        if isinstance(value, list):
            return [item if isinstance(item, dict) else self.learning._markdown_block(str(item)) for item in value]
        raise ValueError("content blocks must be a string or list")

    @staticmethod
    def _normalize_plan(item: dict) -> dict:
        return {
            "type": item["type"],
            "count": int(item["count"]),
            "difficulty": item["difficulty"],
            "score_each": float(item["score_each"]),
        }

    @staticmethod
    def _blueprint_issues(plan: list[dict], total_score: float) -> list[dict]:
        expected = sum(item["count"] * item["score_each"] for item in plan)
        if not math.isclose(expected, total_score, rel_tol=1e-9, abs_tol=1e-9):
            return [{
                "code": "BLUEPRINT_TOTAL_SCORE_MISMATCH",
                "severity": "error",
                "path": "total_score",
                "message": f"题目分值合计为 {expected:g}，与总分 {total_score:g} 不一致",
            }]
        return []

    def _fail_blueprint(self, subject_id: str, blueprint: dict, message: str) -> None:
        failed = {
            **blueprint,
            "status": "failed",
            "issues": [{"code": "BLUEPRINT_PARSE_FAILED", "severity": "error", "path": "prompt", "message": message}],
            "updated_at": self._now(),
        }
        self._replace(subject_id, "exam_blueprints", blueprint["id"], failed)

    def _update_slot(self, subject_id: str, draft_id: str, question_id: str, changes: dict) -> None:
        _, draft = self.learning._find_owned("exam_drafts", draft_id)
        updated = {
            **draft,
            "questions": [
                {**item, **changes} if item["id"] == question_id else item
                for item in draft["questions"]
            ],
            "updated_at": self._now(),
        }
        self._replace(subject_id, "exam_drafts", draft_id, updated)

    @staticmethod
    def _slot_view(slot: dict) -> dict:
        return {key: slot.get(key) for key in ("id", "ordinal", "planned_type", "status", "question", "error", "updated_at")}

    def _draft_view(self, draft: dict) -> dict:
        return {**draft, "questions": [self._slot_view(item) for item in draft["questions"]]}

    @staticmethod
    def _draft_score(questions: list[dict]) -> float:
        return sum((item.get("question") or {}).get("score", 0) for item in questions)

    def _append(self, subject_id: str, collection: str, resource: dict) -> None:
        self.learning._mutate(subject_id, lambda data: {**data, collection: [*data.get(collection, []), resource]})

    def _replace(self, subject_id: str, collection: str, resource_id: str, resource: dict) -> None:
        self.learning._mutate(subject_id, lambda data: {
            **data,
            collection: [resource if item["id"] == resource_id else item for item in data.get(collection, [])],
        })

    def _remove(self, subject_id: str, collection: str, resource_id: str) -> None:
        self.learning._mutate(subject_id, lambda data: {
            **data,
            collection: [item for item in data.get(collection, []) if item["id"] != resource_id],
        })

    def _recover_interrupted_resources(self) -> None:
        timestamp = self._now()
        for subject in self.workspace.snapshot().get("subjects", []):
            data = subject.get("data", {})
            if not any(
                item.get("status") in {"parsing", "generating", "grading"}
                for collection in ("exam_blueprints", "exam_drafts", "attempts", "revision_proposals")
                for item in data.get(collection, [])
            ):
                continue

            def recover(current):
                blueprints = [
                    {
                        **item,
                        "status": "failed",
                        "issues": [{"code": "BLUEPRINT_PARSE_FAILED", "severity": "error", "path": "prompt", "message": "服务重启中断了蓝图解析"}],
                        "updated_at": timestamp,
                    }
                    if item.get("status") == "parsing" else item
                    for item in current.get("exam_blueprints", [])
                ]
                drafts = []
                for item in current.get("exam_drafts", []):
                    if item.get("status") != "generating":
                        drafts.append(item)
                        continue
                    questions = [
                        {
                            **slot,
                            "status": "failed",
                            "error": {"code": "QUESTION_GENERATION_FAILED", "message": "服务重启中断了题目生成", "retryable": True, "details": {}},
                            "updated_at": timestamp,
                        }
                        if slot.get("status") in {"queued", "generating"} else slot
                        for slot in item["questions"]
                    ]
                    drafts.append({
                        **item,
                        "status": "editable" if any(slot.get("question") for slot in questions) else "failed",
                        "questions": questions,
                        "updated_at": timestamp,
                    })
                attempts = [
                    {**item, "status": "paused", "feedback": [], "updated_at": timestamp}
                    if item.get("status") == "grading" else item
                    for item in current.get("attempts", [])
                ]
                proposals = [
                    {
                        **item,
                        "status": "failed",
                        "error": {"code": "REVISION_PROPOSAL_INVALID", "message": "服务重启中断了修改提案生成", "retryable": True, "details": {}},
                        "updated_at": timestamp,
                    }
                    if item.get("status") == "generating" else item
                    for item in current.get("revision_proposals", [])
                ]
                return {
                    **current,
                    "exam_blueprints": blueprints,
                    "exam_drafts": drafts,
                    "attempts": attempts,
                    "revision_proposals": proposals,
                }

            self.learning._mutate(subject["id"], recover)
