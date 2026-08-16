"""Exam blueprint, draft generation, attempts, and feedback services."""
from __future__ import annotations

import asyncio
import copy
import json
import math
import time
import uuid

from jsonpatch import JsonPatch, JsonPatchException
from jsonpointer import JsonPointerException, resolve_pointer
from pydantic import ValidationError

from .exam_models import BlueprintQuestionPlan, ExamBlueprint, ExamChange, ExamDocument, QuestionFeedback, QuestionInput
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
                    self._record_structure_stage(self._now(), time.perf_counter(), "failed")
                    raise OperationFailure("GROUNDING_SOURCE_REQUIRED", "选定资料未覆盖组卷要求")
                grounding_instruction = {
                    "strict": "只使用相关资料中的内容组卷。",
                    "supplemental": "优先使用相关资料，资料外的补充内容需要与资料依据区分。",
                    "general-knowledge": "使用通用知识组卷，并明确该蓝图未依据用户资料。",
                }[payload["grounding_mode"]]
                prompt = (
                    "把组卷要求解析为 JSON，只返回："
                    '{"title":"...","syllabus":["..."],"question_plan":['
                    '{"type":"single-choice","count":1,"difficulty":"medium","score_each":5}],'
                    '"total_score":5,"duration_minutes":30}。题型可用 single-choice、multiple-choice、fill-blank、'
                    "true-false、short-answer、argumentation、extended-response。\n"
                    f"{grounding_instruction}\n\n"
                    f"用户要求：{payload['prompt']}\n\n相关资料：\n{self.learning._anchors_text(anchors) or '无'}"
                )
                response = await self.model_client.chat(profile, [{
                    "role": "user",
                    "content": self.learning._grounded_content(prompt, anchors, profile),
                }])
                validation_started_at = self._now()
                validation_started = time.perf_counter()
                try:
                    parsed = json.loads(response["text"])
                    plan = [self._normalize_plan(item) for item in parsed["question_plan"]]
                    if not plan:
                        raise ValueError("question_plan is required")
                    total_score = float(parsed["total_score"])
                    if total_score <= 0:
                        raise ValueError("total_score must be positive")
                    issues = self._blueprint_issues(plan, total_score)
                except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                    self._record_structure_stage(validation_started_at, validation_started, "failed")
                    raise
                self._record_structure_stage(validation_started_at, validation_started, "succeeded")
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
                self._replace(
                    subject_id,
                    "exam_blueprints",
                    blueprint_id,
                    ExamBlueprint.model_validate(updated).model_dump(),
                )
                return {"type": "exam-blueprint", "id": blueprint_id}
            except asyncio.CancelledError:
                self._fail_blueprint(subject_id, blueprint, "组卷蓝图解析已取消")
                raise
            except OperationFailure:
                self._fail_blueprint(subject_id, blueprint, "选定资料未覆盖组卷要求")
                raise
            except (LearningError, ValidationError, ModelClientError, SourceLibraryError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                self._fail_blueprint(subject_id, blueprint, "模型未返回有效的组卷蓝图")
                raise OperationFailure("MODEL_INVALID_RESPONSE", "模型未返回有效的组卷蓝图") from exc

        resource = {"type": "exam-blueprint", "id": blueprint_id}
        operation = self.operations.start("blueprint-parsing", worker, subject_id=subject_id, resource=resource)
        return {"operation": operation, "resource": resource}

    def update_blueprint(self, blueprint_id: str, patch: dict) -> dict:
        subject, blueprint = self.learning._find_owned("exam_blueprints", blueprint_id)
        if blueprint["status"] == "parsing":
            raise LearningError(409, "OPERATION_IN_PROGRESS", "组卷蓝图仍在解析，暂不能编辑")
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
        validated = ExamBlueprint.model_validate(updated).model_dump()
        self._replace(subject["id"], "exam_blueprints", blueprint_id, validated)
        return validated

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
        subject, blueprint = self.learning._find_owned("exam_blueprints", blueprint_id)
        if blueprint["status"] == "parsing":
            raise LearningError(409, "OPERATION_IN_PROGRESS", "组卷蓝图仍在解析")
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
            try:
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
            except asyncio.CancelledError:
                self._cancel_draft_generation(subject["id"], draft_id)
                raise

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
        self._ensure_draft_operation_idle(draft)
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
        self._ensure_draft_operation_idle(draft)
        if draft["status"] == "generating":
            raise LearningError(409, "OPERATION_IN_PROGRESS", "试卷草稿仍在生成")
        self._remove(subject["id"], "exam_drafts", draft_id)

    def replace_draft_question(self, draft_id: str, question_id: str, question: dict) -> dict:
        subject, draft = self.learning._find_owned("exam_drafts", draft_id)
        self._ensure_draft_operation_idle(draft, question_id)
        slot = next((item for item in draft["questions"] if item["id"] == question_id), None)
        if not slot:
            raise LearningError(404, "RESOURCE_NOT_FOUND", "题目不存在")
        if draft["status"] in {"generating", "published"}:
            raise LearningError(409, "RESOURCE_CONFLICT", "当前试卷草稿不可编辑")
        blueprint = self.get_blueprint(draft["blueprint_id"])
        normalized = self._validate_manual_question(question, question_id)
        normalized = self._validate_question_resources(
            subject["id"],
            normalized,
            allowed_version_ids=set(blueprint["source_version_ids"]) if blueprint["grounding_mode"] != "general-knowledge" else set(),
        )
        status = "complete" if normalized["reliability"] == "reliable" else "needs-review"
        updated_slot = {**self._slot_view(slot), "planned_type": normalized["type"], "status": status, "question": normalized, "error": None, "updated_at": self._now()}
        self._update_slot(subject["id"], draft_id, question_id, updated_slot)
        refreshed = self.learning._find_owned("exam_drafts", draft_id)[1]
        self._replace(
            subject["id"],
            "exam_drafts",
            draft_id,
            {**refreshed, "total_score": self._draft_score(refreshed["questions"]), "updated_at": self._now()},
        )
        return updated_slot

    def delete_draft_question(self, draft_id: str, question_id: str) -> None:
        subject, draft = self.learning._find_owned("exam_drafts", draft_id)
        self._ensure_draft_operation_idle(draft, question_id)
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
            retry_started_at = self._now()
            self.operations.record_stage(
                "retry",
                started_at=retry_started_at,
                completed_at=self._now(),
                outer_elapsed_ms=0,
                counters={"retries": 1},
            )
            try:
                question = await self._generate_question(profile, blueprint, slot)
            except asyncio.CancelledError:
                self._update_slot(subject["id"], draft_id, question_id, {**slot, "updated_at": self._now()})
                raise
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
        self._ensure_draft_operation_idle(draft)
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
        history = {
            "id": exam_id,
            "exam_id": exam_id,
            "undo_version_ids": [],
            "redo_version_ids": [],
        }

        def update(data):
            return {
                **data,
                "exams": [*data.get("exams", []), exam],
                "exam_versions": [*data.get("exam_versions", []), version],
                "exam_histories": [*data.get("exam_histories", []), history],
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

    def replace_exam_document(self, exam_id: str, payload: dict) -> dict:
        document = self._validate_exam_document(payload["document"])
        return self._commit_exam_document(
            exam_id,
            document,
            actor="user",
            summary=payload.get("summary") or "人工编辑试卷",
            expected_version_id=payload["base_version_id"],
        )

    def list_exam_versions(self, exam_id: str) -> list[dict]:
        subject, _ = self.learning._find_owned("exams", exam_id)
        return [
            self._version_view(item)
            for item in subject.get("data", {}).get("exam_versions", [])
            if item["exam_id"] == exam_id
        ]

    def restore_exam_version(self, exam_id: str, version_id: str) -> dict:
        subject, _ = self.learning._find_owned("exams", exam_id)
        document = self._version_document(subject, exam_id, version_id)
        version = next(
            item
            for item in subject.get("data", {}).get("exam_versions", [])
            if item["exam_id"] == exam_id and item["id"] == version_id
        )
        return self._commit_exam_document(
            exam_id,
            document,
            actor="restore",
            summary=f"恢复到版本 {version['number']}",
        )

    def undo_exam_change(self, exam_id: str) -> dict:
        return self._commit_exam_document(exam_id, None, actor="undo", summary="撤销最近一次修改", history_action="undo")

    def redo_exam_change(self, exam_id: str) -> dict:
        return self._commit_exam_document(exam_id, None, actor="redo", summary="重做最近一次撤销", history_action="redo")

    def delete_exam(self, exam_id: str) -> None:
        subject, _ = self.learning._find_owned("exams", exam_id)
        if any(
            item.get("exam_id") == exam_id and item.get("status") == "generating"
            for item in subject.get("data", {}).get("revision_proposals", [])
        ) or any(
            item.get("exam_id") == exam_id and item.get("status") in {"queued", "rendering"}
            for item in subject.get("data", {}).get("exam_exports", [])
        ):
            raise LearningError(409, "OPERATION_IN_PROGRESS", "试卷仍有修改或导出任务正在执行")
        if any(item.get("exam_id") == exam_id for item in subject.get("data", {}).get("attempts", [])):
            raise LearningError(409, "RESOURCE_CONFLICT", "试卷已有作答记录，不能删除")

        def update(data):
            return {
                **data,
                "exams": [item for item in data.get("exams", []) if item["id"] != exam_id],
                "exam_versions": [item for item in data.get("exam_versions", []) if item["exam_id"] != exam_id],
                "exam_histories": [item for item in data.get("exam_histories", []) if item["exam_id"] != exam_id],
                "revision_proposals": [item for item in data.get("revision_proposals", []) if item["exam_id"] != exam_id],
            }

        self.learning._mutate(subject["id"], update)

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
            "completion_status": "in-progress",
            "grading_status": "not-requested",
            "unanswered_question_ids": [question["id"] for question in paper["questions"]],
            "show_suggested_score": bool(payload.get("show_suggested_score")),
            "paper": paper,
            "answers": [],
            "feedback": [],
            "created_at": timestamp,
            "updated_at": timestamp,
            "submitted_at": None,
            "completed_at": None,
            "grading_error": None,
        }
        self._append(subject["id"], "attempts", attempt)
        return attempt

    def get_attempt(self, attempt_id: str) -> dict:
        return self.learning._find_owned("attempts", attempt_id)[1]

    def update_attempt(self, attempt_id: str, patch: dict) -> dict:
        subject, attempt = self.learning._find_owned("attempts", attempt_id)
        if attempt["status"] not in {"in-progress", "paused"}:
            raise LearningError(409, "ATTEMPT_STATE_CONFLICT", "已提交的作答不能修改设置")
        if any(
            self.operations.has_active("feedback", f"feedback-{attempt_id}-{question['id']}")
            for question in attempt["paper"]["questions"]
        ):
            raise LearningError(409, "OPERATION_IN_PROGRESS", "题目反馈生成期间不能修改作答设置")
        updated = {**attempt, **patch, "updated_at": self._now()}
        if updated["mode"] == "exam":
            updated["feedback"] = []
        self._replace(subject["id"], "attempts", attempt_id, updated)
        return updated

    def save_answer(self, attempt_id: str, question_id: str, answer: dict) -> dict:
        subject, attempt = self.learning._find_owned("attempts", attempt_id)
        if attempt["status"] != "in-progress":
            raise LearningError(409, "ATTEMPT_STATE_CONFLICT", "当前作答状态不能保存答案")
        if attempt.get("completion_status", "in-progress") == "completed":
            raise LearningError(409, "ATTEMPT_ALREADY_COMPLETED", "作答已完成，请先继续作答")
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
        feedback = [item for item in attempt["feedback"] if item["question_id"] != question_id]
        if attempt["mode"] == "practice" and question["type"] in {"single-choice", "multiple-choice", "fill-blank", "true-false"}:
            objective = self._objective_feedback(attempt, question, saved)
            feedback.append(objective)
        grading_status = attempt.get("grading_status", "not-requested")
        if grading_status == "completed":
            grading_status = "stale"
        updated = {
            **attempt,
            "answers": answers,
            "feedback": feedback,
            "grading_status": grading_status,
            "unanswered_question_ids": self._unanswered_question_ids(attempt, answers),
            "updated_at": timestamp,
        }
        self._replace(subject["id"], "attempts", attempt_id, updated)
        return saved

    def request_feedback(self, attempt_id: str, question_id: str, payload: dict) -> dict:
        subject, attempt = self.learning._find_owned("attempts", attempt_id)
        if attempt["status"] == "grading":
            raise LearningError(409, "OPERATION_IN_PROGRESS", "作答正在统一批改，请等待完成")
        if attempt["mode"] == "exam" and attempt["status"] != "submitted":
            raise LearningError(409, "ANSWER_NOT_AVAILABLE", "考试模式提交前不能查看反馈")
        question = self._attempt_question(subject, attempt, question_id)
        answer = next((item for item in attempt["answers"] if item["question_id"] == question_id), None)
        if not answer:
            raise LearningError(409, "FEEDBACK_UNAVAILABLE", "请先保存答案")
        feedback_id = f"feedback-{attempt_id}-{question_id}"
        resource = {"type": "feedback", "id": feedback_id}
        if self.operations.has_active("feedback", feedback_id):
            raise LearningError(409, "OPERATION_IN_PROGRESS", "该题反馈正在生成")

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
        if attempt.get("grading_status") in {"queued", "grading"}:
            raise LearningError(409, "OPERATION_IN_PROGRESS", "批改进行中，暂时不能继续作答")
        if attempt.get("completion_status") == "completed":
            updated = {**attempt, "completion_status": "in-progress", "completed_at": None, "status": "in-progress", "updated_at": self._now()}
            self._replace(subject["id"], "attempts", attempt_id, updated)
            return updated
        if attempt["status"] == "submitted" and attempt.get("grading_status") in {"completed", "failed", "stale"}:
            updated = {**attempt, "status": "in-progress", "updated_at": self._now()}
            self._replace(subject["id"], "attempts", attempt_id, updated)
            return updated
        if attempt["status"] != "paused":
            raise LearningError(409, "ATTEMPT_STATE_CONFLICT", "当前作答不在暂停状态")
        updated = {**attempt, "status": "in-progress", "updated_at": self._now()}
        self._replace(subject["id"], "attempts", attempt_id, updated)
        return updated

    def complete_attempt(self, attempt_id: str) -> dict:
        subject, attempt = self.learning._find_owned("attempts", attempt_id)
        if attempt.get("completion_status") == "completed":
            raise LearningError(409, "ATTEMPT_ALREADY_COMPLETED", "作答已经标记完成")
        if attempt["status"] not in {"in-progress", "paused"}:
            raise LearningError(409, "ATTEMPT_STATE_CONFLICT", "当前状态不能标记完成")
        timestamp = self._now()
        updated = {
            **attempt,
            "completion_status": "completed",
            "completed_at": timestamp,
            "unanswered_question_ids": self._unanswered_question_ids(attempt),
            "updated_at": timestamp,
        }
        self._replace(subject["id"], "attempts", attempt_id, updated)
        return updated

    def submit_attempt(self, attempt_id: str) -> dict:
        subject, attempt = self.learning._find_owned("attempts", attempt_id)
        if attempt["status"] not in {"in-progress", "paused"} or attempt.get("grading_status") in {"queued", "grading"}:
            raise LearningError(409, "ATTEMPT_STATE_CONFLICT", "当前作答不能提交")
        if any(
            self.operations.has_active("feedback", f"feedback-{attempt_id}-{question['id']}")
            for question in self._version_document(subject, attempt["exam_id"], attempt["exam_version_id"])["questions"]
        ):
            raise LearningError(409, "OPERATION_IN_PROGRESS", "请等待当前题目反馈完成后再提交")
        grading = {**attempt, "status": "grading", "grading_status": "grading", "grading_error": None, "feedback": [], "updated_at": self._now()}
        self._replace(subject["id"], "attempts", attempt_id, grading)
        resource = {"type": "attempt", "id": attempt_id}

        async def worker():
            try:
                current = self.get_attempt(attempt_id)
                document = self._version_document(subject, current["exam_id"], current["exam_version_id"])
                feedback = []
                objective_started_at = self._now()
                objective_started = time.perf_counter()
                objective_count = 0
                for question in document["questions"]:
                    answer = next((item for item in current["answers"] if item["question_id"] == question["id"]), None)
                    if not answer:
                        continue
                    if question["type"] in {"single-choice", "multiple-choice", "fill-blank", "true-false"}:
                        feedback.append(self._objective_feedback(current, question, answer))
                        objective_count += 1
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
                if objective_count:
                    self.operations.record_stage(
                        "structure-validation",
                        started_at=objective_started_at,
                        completed_at=self._now(),
                        outer_elapsed_ms=max(0, round((time.perf_counter() - objective_started) * 1000)),
                        counters={},
                    )
                timestamp = self._now()
                submitted = {**current, "status": "submitted", "grading_status": "completed", "feedback": feedback, "updated_at": timestamp, "submitted_at": timestamp}
                self._replace(subject["id"], "attempts", attempt_id, submitted)
                return resource
            except asyncio.CancelledError:
                current = self.get_attempt(attempt_id)
                restored = {
                    **current,
                    "status": attempt["status"],
                    "grading_status": "failed",
                    "grading_error": {"code": "MODEL_CONNECTION_FAILED", "message": "批改已取消或失败", "retryable": True, "details": {}},
                    "feedback": attempt["feedback"],
                    "updated_at": self._now(),
                }
                self._replace(subject["id"], "attempts", attempt_id, restored)
                raise
            except Exception as exc:
                current = self.get_attempt(attempt_id)
                failed = {
                    **current,
                    "status": attempt["status"],
                    "grading_status": "failed",
                    "grading_error": {"code": getattr(exc, "code", "INTERNAL_ERROR"), "message": "批改失败，请重试", "retryable": True, "details": {}},
                    "feedback": attempt["feedback"],
                    "updated_at": self._now(),
                }
                self._replace(subject["id"], "attempts", attempt_id, failed)
                raise

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

    def list_revision_proposals(self, exam_id: str) -> list[dict]:
        subject, _ = self.learning._find_owned("exams", exam_id)
        return [
            item
            for item in subject.get("data", {}).get("revision_proposals", [])
            if item["exam_id"] == exam_id
        ]

    def get_revision_proposal(self, proposal_id: str) -> dict:
        return self.learning._find_owned("revision_proposals", proposal_id)[1]

    def create_revision_proposal(self, exam_id: str, payload: dict) -> dict:
        subject, exam = self.learning._find_owned("exams", exam_id)
        if payload["base_version_id"] != exam["current_version_id"]:
            raise LearningError(
                409,
                "EXAM_VERSION_CONFLICT",
                "试卷版本已变化，请基于最新版本重试",
                retryable=True,
                details={"current_version_id": exam["current_version_id"]},
            )
        base_document = self._version_document(subject, exam_id, payload["base_version_id"])
        self._validate_revision_scope(base_document, payload["scope"])
        if payload.get("selection"):
            selection = payload["selection"]
            if (
                selection["document_kind"] != "exam"
                or selection["document_id"] != exam_id
                or selection["version_id"] != payload["base_version_id"]
            ):
                raise LearningError(422, "VALIDATION_FAILED", "修改选区必须属于当前试卷版本")
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
                        "path 使用 JSON Pointer；move 操作的 before 填源路径，path 填目标路径。不要直接应用修改。\n\n"
                        f"修改范围：{json.dumps(payload['scope'], ensure_ascii=False)}\n"
                        f"选区上下文：{json.dumps(payload.get('selection'), ensure_ascii=False)}\n"
                        f"试卷：{json.dumps(base_document, ensure_ascii=False)}\n\n指令：{payload['instruction']}"
                    ),
                }])
                validation_started_at = self._now()
                validation_started = time.perf_counter()
                try:
                    raw_changes = json.loads(response["text"])["changes"]
                    changes = [ExamChange.model_validate(item).model_dump() for item in raw_changes]
                    if not isinstance(changes, list) or not changes:
                        raise ValueError("changes is required")
                    self._validate_revision_changes(base_document, payload["scope"], changes)
                    self._apply_revision_changes(base_document, changes)
                except (LearningError, ValidationError, JsonPatchException, JsonPointerException, ValueError, KeyError, TypeError, json.JSONDecodeError):
                    self._record_structure_stage(validation_started_at, validation_started, "failed")
                    raise
                self._record_structure_stage(validation_started_at, validation_started, "succeeded")
                ready = {**proposal, "status": "ready", "changes": changes, "updated_at": self._now()}
                self._replace(subject["id"], "revision_proposals", proposal_id, ready)
                return resource
            except asyncio.CancelledError:
                canceled = {
                    **proposal,
                    "status": "failed",
                    "error": {"code": "REVISION_PROPOSAL_INVALID", "message": "修改提案生成已取消", "retryable": True, "details": {}},
                    "updated_at": self._now(),
                }
                self._replace(subject["id"], "revision_proposals", proposal_id, canceled)
                raise
            except (
                LearningError,
                ModelClientError,
                ValidationError,
                JsonPatchException,
                JsonPointerException,
                ValueError,
                KeyError,
                TypeError,
                json.JSONDecodeError,
            ) as exc:
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

    def apply_revision_proposal(self, proposal_id: str) -> dict:
        subject, proposal = self.learning._find_owned("revision_proposals", proposal_id)
        if proposal["status"] != "ready":
            raise LearningError(409, "REVISION_PROPOSAL_INVALID", "当前修改提案不能应用")
        _, exam = self.learning._find_owned("exams", proposal["exam_id"])
        if exam["current_version_id"] != proposal["base_version_id"]:
            raise LearningError(
                409,
                "REVISION_PROPOSAL_STALE",
                "试卷已更新，该修改提案不再适用",
                details={"current_version_id": exam["current_version_id"]},
            )
        base_document = self._version_document(subject, exam["id"], proposal["base_version_id"])
        try:
            document = self._apply_revision_changes(base_document, proposal["changes"])
        except (LearningError, ValidationError, JsonPatchException, JsonPointerException, ValueError, KeyError, TypeError) as exc:
            raise LearningError(409, "REVISION_PROPOSAL_INVALID", "修改后的试卷结构无效") from exc
        return self._commit_exam_document(
            exam["id"],
            document,
            actor="ai",
            summary=proposal["instruction"][:500],
            model=proposal.get("model"),
            expected_version_id=proposal["base_version_id"],
            applied_proposal_id=proposal_id,
        )

    def discard_revision_proposal(self, proposal_id: str) -> None:
        subject, proposal = self.learning._find_owned("revision_proposals", proposal_id)
        if proposal["status"] not in {"ready", "failed"}:
            raise LearningError(409, "REVISION_PROPOSAL_INVALID", "当前修改提案不能放弃")
        discarded = {**proposal, "status": "discarded", "updated_at": self._now()}
        self._replace(subject["id"], "revision_proposals", proposal_id, discarded)

    def _commit_exam_document(
        self,
        exam_id: str,
        document: dict | None,
        *,
        actor: str,
        summary: str,
        model: dict | None = None,
        expected_version_id: str | None = None,
        history_action: str = "push",
        applied_proposal_id: str | None = None,
    ) -> dict:
        subject, _ = self.learning._find_owned("exams", exam_id)
        normalized = None
        version_id = self._ids("exam-version")
        timestamp = self._now()
        committed: dict[str, dict] = {}

        if document is not None:
            normalized = self._validate_exam_document(document, subject["id"])

        def update(data):
            current_exam = next((item for item in data.get("exams", []) if item["id"] == exam_id), None)
            if current_exam is None:
                raise LearningError(404, "RESOURCE_NOT_FOUND", "试卷不存在")
            if expected_version_id and current_exam["current_version_id"] != expected_version_id:
                raise LearningError(
                    409,
                    "EXAM_VERSION_CONFLICT",
                    "试卷版本已变化，请基于最新版本重试",
                    retryable=True,
                    details={"current_version_id": current_exam["current_version_id"]},
                )

            versions = [item for item in data.get("exam_versions", []) if item["exam_id"] == exam_id]
            history = next(
                (item for item in data.get("exam_histories", []) if item["exam_id"] == exam_id),
                self._rebuild_exam_history(current_exam, versions),
            )
            undo_ids = list(history.get("undo_version_ids", []))
            redo_ids = list(history.get("redo_version_ids", []))
            current_version_id = current_exam["current_version_id"]

            if history_action == "undo":
                if not undo_ids:
                    raise LearningError(409, "RESOURCE_CONFLICT", "没有可撤销的试卷修改")
                target_version_id = undo_ids.pop()
                redo_ids.append(current_version_id)
                target_document = self._document_from_versions(versions, target_version_id)
            elif history_action == "redo":
                if not redo_ids:
                    raise LearningError(409, "RESOURCE_CONFLICT", "没有可重做的试卷修改")
                target_version_id = redo_ids.pop()
                undo_ids.append(current_version_id)
                target_document = self._document_from_versions(versions, target_version_id)
            else:
                undo_ids.append(current_version_id)
                redo_ids = []
                target_document = copy.deepcopy(normalized)

            version = {
                "id": version_id,
                "exam_id": exam_id,
                "number": max((item["number"] for item in versions), default=0) + 1,
                "actor": actor,
                "summary": summary,
                "model": copy.deepcopy(model),
                "document": target_document,
                "created_at": timestamp,
            }
            updated_exam = {
                **current_exam,
                "current_version_id": version_id,
                "document": copy.deepcopy(target_document),
                "total_score": sum(item["score"] for item in target_document["questions"]),
                "can_undo": bool(undo_ids),
                "can_redo": bool(redo_ids),
                "updated_at": timestamp,
            }
            updated_history = {
                "id": exam_id,
                "exam_id": exam_id,
                "undo_version_ids": undo_ids,
                "redo_version_ids": redo_ids,
            }
            histories = [
                updated_history if item["exam_id"] == exam_id else item
                for item in data.get("exam_histories", [])
            ]
            if not any(item["exam_id"] == exam_id for item in data.get("exam_histories", [])):
                histories.append(updated_history)
            proposals = [
                {**item, "status": "applied", "updated_at": timestamp}
                if item["id"] == applied_proposal_id else item
                for item in data.get("revision_proposals", [])
            ]
            committed["exam"] = copy.deepcopy(updated_exam)
            return {
                **data,
                "exams": [updated_exam if item["id"] == exam_id else item for item in data.get("exams", [])],
                "exam_versions": [*data.get("exam_versions", []), version],
                "exam_histories": histories,
                "revision_proposals": proposals,
            }

        self.learning._mutate(subject["id"], update)
        self.operations.record_action(
            "exam-revision",
            subject_id=subject["id"],
            resource={"type": "exam", "id": exam_id},
            stage="undo" if actor == "undo" else "apply-change",
            attributes={"actor": actor},
        )
        return committed["exam"]

    def _validate_exam_document(self, document: dict, subject_id: str | None = None) -> dict:
        validated = ExamDocument.model_validate(document).model_dump()
        question_ids = [item["id"] for item in validated["questions"]]
        if len(question_ids) != len(set(question_ids)):
            raise LearningError(422, "QUESTION_STRUCTURE_INVALID", "试卷题目 ID 不能重复")
        normalized = {
            **validated,
            "questions": [self._validate_manual_question(item, item["id"]) for item in validated["questions"]],
        }
        if subject_id is not None:
            normalized["questions"] = [
                self._validate_question_resources(subject_id, item)
                for item in normalized["questions"]
            ]
        return normalized

    def _validate_revision_scope(self, document: dict, scope: dict) -> None:
        question_ids = {item["id"] for item in document["questions"]}
        block_ids = set(self._block_paths(document))
        if scope["kind"] == "questions":
            if not scope["question_ids"] or not set(scope["question_ids"]) <= question_ids:
                raise LearningError(422, "VALIDATION_FAILED", "修改范围包含不存在的题目")
        if scope["kind"] == "blocks":
            if not scope["block_ids"] or not set(scope["block_ids"]) <= block_ids:
                raise LearningError(422, "VALIDATION_FAILED", "修改范围包含不存在的内容块")

    def _validate_revision_changes(self, document: dict, scope: dict, changes: list[dict]) -> None:
        if any(not item["path"].startswith("/") for item in changes):
            raise ValueError("change path must be a JSON Pointer")
        if scope["kind"] == "whole-exam":
            return
        allowed_paths = []
        if scope["kind"] == "questions":
            allowed_ids = set(scope["question_ids"])
            allowed_paths = [
                f"/questions/{index}"
                for index, question in enumerate(document["questions"])
                if question["id"] in allowed_ids
            ]
        elif scope["kind"] == "blocks":
            paths = self._block_paths(document)
            allowed_paths = [paths[block_id] for block_id in scope["block_ids"]]
        for change in changes:
            paths = [change["path"]]
            if change["operation"] == "move" and isinstance(change["before"], str):
                paths.append(change["before"])
            if any(not any(path == allowed or path.startswith(f"{allowed}/") for allowed in allowed_paths) for path in paths):
                raise ValueError("change exceeds the requested scope")

    def _apply_revision_changes(self, document: dict, changes: list[dict]) -> dict:
        patch = []
        for change in changes:
            operation = change["operation"]
            path = change["path"]
            if operation in {"replace", "remove"}:
                current = resolve_pointer(document, path)
                if current != change["before"]:
                    raise ValueError("change preview does not match the base document")
            if operation == "move":
                if not isinstance(change["before"], str) or not change["before"].startswith("/"):
                    raise ValueError("move change requires a source JSON Pointer in before")
                patch.append({"op": "move", "from": change["before"], "path": path})
            elif operation == "remove":
                patch.append({"op": "remove", "path": path})
            else:
                patch.append({"op": operation, "path": path, "value": copy.deepcopy(change["after"])})
        candidate = JsonPatch(patch).apply(copy.deepcopy(document), in_place=False)
        return self._validate_exam_document(candidate)

    @staticmethod
    def _block_paths(value, path: str = "") -> dict[str, str]:
        paths = {}
        if isinstance(value, dict):
            if isinstance(value.get("id"), str) and value.get("type") in {"markdown", "latex", "table", "image"}:
                paths[value["id"]] = path
            for key, child in value.items():
                escaped = key.replace("~", "~0").replace("/", "~1")
                paths.update(ExamService._block_paths(child, f"{path}/{escaped}"))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                paths.update(ExamService._block_paths(child, f"{path}/{index}"))
        return paths

    @staticmethod
    def _version_view(version: dict) -> dict:
        return {key: version.get(key) for key in ("id", "exam_id", "number", "actor", "summary", "model", "created_at")}

    @staticmethod
    def _document_from_versions(versions: list[dict], version_id: str) -> dict:
        version = next((item for item in versions if item["id"] == version_id), None)
        if not version:
            raise LearningError(409, "RESOURCE_CONFLICT", "撤销历史引用的试卷版本不存在")
        return copy.deepcopy(version["document"])

    @staticmethod
    def _rebuild_exam_history(exam: dict, versions: list[dict]) -> dict:
        ordered = sorted(versions, key=lambda item: item["number"])
        current_index = next(
            (index for index, item in enumerate(ordered) if item["id"] == exam["current_version_id"]),
            len(ordered) - 1,
        )
        return {
            "id": exam["id"],
            "exam_id": exam["id"],
            "undo_version_ids": [item["id"] for item in ordered[:current_index]],
            "redo_version_ids": [],
        }

    # Selection -----------------------------------------------------------

    def resolve_selection(self, selection: dict, *, include_context: bool = False):
        kind = selection["document_kind"]
        if kind == "exam":
            subject, exam = self.learning._find_owned("exams", selection["document_id"])
            try:
                document = self._version_document(subject, exam["id"], selection["version_id"])
            except LearningError as exc:
                raise LearningError(409, "CHAT_SELECTION_INVALID", "试卷选区版本已失效") from exc
        elif kind == "exam-draft":
            subject, draft = self.learning._find_owned("exam_drafts", selection["document_id"])
            if selection["version_id"] != draft["id"]:
                raise LearningError(409, "CHAT_SELECTION_INVALID", "试卷草稿选区版本已失效")
            document = {
                "questions": [item["question"] for item in draft["questions"] if item.get("question")],
                "instructions": draft["instructions"],
            }
        else:
            subject, artifact = self.learning._find_owned("artifacts", selection["document_id"])
            if selection["version_id"] != artifact["id"]:
                raise LearningError(409, "CHAT_SELECTION_INVALID", "学习产物选区版本已失效")
            document = artifact

        questions = document.get("questions", []) if isinstance(document, dict) else []
        selected_question = None
        if selection.get("question_id"):
            selected_question = next(
                (item for item in questions if isinstance(item, dict) and item.get("id") == selection["question_id"]),
                None,
            )
            if selected_question is None:
                raise LearningError(409, "CHAT_SELECTION_INVALID", "选中的题目不属于该文档版本")

        search_root = selected_question or document
        selected_block = None
        if selection.get("block_id"):
            selected_block = self._find_content_block(search_root, selection["block_id"])
            if selected_block is None:
                raise LearningError(409, "CHAT_SELECTION_INVALID", "选中的内容块不属于所在题目或文档版本")

        if selection.get("selected_text"):
            visible_text = self._selection_text(selected_block or search_root)
            if selection["selected_text"] not in visible_text:
                raise LearningError(409, "CHAT_SELECTION_INVALID", "选中文字已不属于当前文档版本")

        asset = selection.get("image_asset")
        if asset:
            image_block = selected_block if selected_block and selected_block.get("type") == "image" else self._find_image_block(search_root, asset)
            if image_block is None or image_block.get("asset") != asset:
                raise LearningError(409, "CHAT_SELECTION_INVALID", "选中图片已不属于所在题目或文档版本")
            try:
                asset_version = self.sources.get_version(asset["source_version_id"])
                asset_source = self.sources.get_source(asset_version["source_id"])
                if asset_source["subject_id"] != subject["id"]:
                    raise SourceLibraryError(409, "CHAT_SELECTION_INVALID", "选中图片不属于当前科目")
                self.sources.get_asset(asset["source_version_id"], asset["asset_id"])
            except SourceLibraryError as exc:
                raise LearningError(409, "CHAT_SELECTION_INVALID", "选中图片已失效") from exc

        allowed_citations = {
            item.get("id")
            for item in self._walk_values(selected_question or document)
            if isinstance(item, dict) and item.get("source_version_id") and item.get("anchor_id")
        }
        for citation_id in selection.get("citation_ids", []):
            try:
                citation = self.sources.get_citation(citation_id)
                citation_version = self.sources.get_version(citation["source_version_id"])
                citation_source = self.sources.get_source(citation_version["source_id"])
            except SourceLibraryError as exc:
                raise LearningError(409, "CHAT_SELECTION_INVALID", "选区引用已失效") from exc
            if citation_id not in allowed_citations:
                raise LearningError(409, "CHAT_SELECTION_INVALID", "选区引用不属于所在题目或文档")
            if citation_source["subject_id"] != subject["id"]:
                raise LearningError(409, "CHAT_SELECTION_INVALID", "选区引用不属于当前科目")

        context = None
        if selected_question is not None:
            context = json.dumps(selected_question, ensure_ascii=False)
        elif selected_block is not None:
            context = json.dumps(selected_block, ensure_ascii=False)
        return (selection, context) if include_context else selection

    @staticmethod
    def _walk_values(value):
        yield value
        if isinstance(value, dict):
            for child in value.values():
                yield from ExamService._walk_values(child)
        elif isinstance(value, list):
            for child in value:
                yield from ExamService._walk_values(child)

    @classmethod
    def _find_content_block(cls, value, block_id: str):
        for item in cls._walk_values(value):
            if isinstance(item, dict) and item.get("id") == block_id and item.get("type") in {"markdown", "latex", "table", "image"}:
                return item
        return None

    @classmethod
    def _find_image_block(cls, value, asset: dict):
        for item in cls._walk_values(value):
            if isinstance(item, dict) and item.get("type") == "image" and item.get("asset") == asset:
                return item
        return None

    @classmethod
    def _selection_text(cls, value) -> str:
        parts = []
        for item in cls._walk_values(value):
            if not isinstance(item, dict):
                continue
            if item.get("type") == "markdown":
                parts.append(item.get("text", ""))
            elif item.get("type") == "latex":
                parts.append(item.get("latex", ""))
            elif item.get("type") == "table":
                parts.append(" | ".join(item.get("columns", [])))
                parts.extend(" | ".join(row) for row in item.get("rows", []))
            elif item.get("type") == "image":
                parts.append(item.get("alt") or item.get("caption") or "图片")
        return "\n".join(item for item in parts if item)

    # Question and grading helpers ---------------------------------------

    async def _generate_question(self, profile: dict, blueprint: dict, slot: dict) -> dict:
        query = " ".join([*blueprint.get("syllabus", []), slot["planned_type"]])
        anchors = [] if blueprint["grounding_mode"] == "general-knowledge" else self.sources.retrieve(query, blueprint["source_version_ids"], limit=5)
        if blueprint["grounding_mode"] == "strict" and not anchors:
            self._record_structure_stage(self._now(), time.perf_counter(), "failed")
            raise SourceLibraryError(409, "QUESTION_EVIDENCE_INCOMPLETE", "资料未覆盖该题目计划")
        citations = [self.sources.create_citation(anchor) for anchor in anchors]
        grounding_instruction = {
            "strict": "题干、答案和解析只能依据资料片段。",
            "supplemental": "优先依据资料片段；如需通用知识补充，必须与资料依据区分。",
            "general-knowledge": "使用通用知识生成，并将依据标为通用知识。",
        }[blueprint["grounding_mode"]]
        prompt = (
            f"生成一道 {slot['planned_type']} 题，难度 {slot['planned_difficulty']}，分值 {slot['planned_score']}。"
            "只返回 JSON，字段为 type、stem、options（选择题）、answer、explanation、knowledge_points。"
            "answer.kind 按题型使用 choice、fill-blank、true-false 或 subjective。\n"
            f"{grounding_instruction}\n\n"
            f"资料片段：\n{self.learning._anchors_text(anchors) or '无'}"
        )
        response = await self.model_client.chat(profile, [{
            "role": "user",
            "content": self.learning._grounded_content(prompt, anchors, profile),
        }])
        validation_started_at = self._now()
        validation_started = time.perf_counter()
        try:
            raw = json.loads(response["text"])
            question = self._normalize_generated_question(raw, slot, citations, blueprint["grounding_mode"])
            question = self._validate_question_resources(
                blueprint["subject_id"],
                question,
                allowed_version_ids=set(blueprint["source_version_ids"]) if blueprint["grounding_mode"] != "general-knowledge" else set(),
            )
        except (LearningError, ValidationError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            self._record_structure_stage(validation_started_at, validation_started, "failed")
            raise
        self._record_structure_stage(validation_started_at, validation_started, "succeeded")
        return question

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

    def _validate_question_resources(
        self,
        subject_id: str,
        question: dict,
        *,
        allowed_version_ids: set[str] | None = None,
    ) -> dict:
        canonical_citations = []
        for supplied in question["evidence"].get("citations", []):
            try:
                citation = self.sources.get_citation(supplied["id"])
                version = self.sources.get_version(citation["source_version_id"])
                source = self.sources.get_source(version["source_id"])
            except SourceLibraryError as exc:
                raise LearningError(422, "QUESTION_STRUCTURE_INVALID", "题目引用的资料依据不存在") from exc
            if source["subject_id"] != subject_id:
                raise LearningError(422, "QUESTION_STRUCTURE_INVALID", "题目引用了其他科目的资料")
            if allowed_version_ids is not None and citation["source_version_id"] not in allowed_version_ids:
                raise LearningError(422, "QUESTION_STRUCTURE_INVALID", "题目引用超出当前资料范围")
            canonical_citations.append(citation)

        for item in self._walk_values(question):
            if not isinstance(item, dict) or item.get("type") != "image":
                continue
            asset = item["asset"]
            try:
                version = self.sources.get_version(asset["source_version_id"])
                source = self.sources.get_source(version["source_id"])
                self.sources.get_asset(asset["source_version_id"], asset["asset_id"])
            except SourceLibraryError as exc:
                raise LearningError(422, "QUESTION_STRUCTURE_INVALID", "题目引用的图片不存在") from exc
            if source["subject_id"] != subject_id:
                raise LearningError(422, "QUESTION_STRUCTURE_INVALID", "题目引用了其他科目的图片")
            if allowed_version_ids is not None and asset["source_version_id"] not in allowed_version_ids:
                raise LearningError(422, "QUESTION_STRUCTURE_INVALID", "题目图片超出当前资料范围")

        evidence = {**question["evidence"], "citations": canonical_citations}
        if evidence["basis"] == "general-knowledge" and canonical_citations:
            raise LearningError(422, "QUESTION_STRUCTURE_INVALID", "通用知识题目不能伪装为资料依据")
        return {**question, "evidence": evidence}

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
        validation_started_at = self._now()
        validation_started = time.perf_counter()
        try:
            result = json.loads(response["text"])
            status = result.get("status", "needs-review")
            if status not in {"complete", "needs-review", "unable-to-assess"}:
                raise ValueError("feedback status is invalid")
            for field in ("matched_point_ids", "missed_point_ids", "reasoning_issues", "suggestions"):
                value = result.get(field, [])
                if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                    raise ValueError(f"{field} must be a list of strings")
            by_id = {item["id"]: item for item in points}
            matched_ids = result.get("matched_point_ids", [])
            missed_ids = result.get("missed_point_ids", [])
            if len(matched_ids) != len(set(matched_ids)) or len(missed_ids) != len(set(missed_ids)):
                raise ValueError("feedback point ids must be unique")
            if set(matched_ids) & set(missed_ids):
                raise ValueError("a scoring point cannot be both matched and missed")
            matched = [by_id[item_id] for item_id in matched_ids if item_id in by_id]
            missed = [by_id[item_id] for item_id in missed_ids if item_id in by_id]
            covered = {item["id"] for item in [*matched, *missed]}
            if status != "unable-to-assess" and covered != set(by_id):
                status = "needs-review"
            suggested_score = result.get("suggested_score")
            if suggested_score is not None:
                if isinstance(suggested_score, bool) or not isinstance(suggested_score, (int, float)):
                    raise ValueError("suggested_score must be a number")
                if not 0 <= float(suggested_score) <= question["score"]:
                    status = "needs-review"
                    suggested_score = None
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            self._record_structure_stage(validation_started_at, validation_started, "failed")
            raise
        self._record_structure_stage(validation_started_at, validation_started, "succeeded")
        feedback = {
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
        return QuestionFeedback.model_validate(feedback).model_dump()

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
        if expected == "choice":
            option_ids = {item["id"] for item in question.get("options", [])}
            if not set(answer["option_ids"]) <= option_ids:
                raise LearningError(422, "ANSWER_TYPE_MISMATCH", "答案引用了不存在的选项")
            if question["type"] == "single-choice" and len(answer["option_ids"]) > 1:
                raise LearningError(422, "ANSWER_TYPE_MISMATCH", "单选题最多选择一个选项")
        elif expected == "fill-blank":
            blank_ids = {item["id"] for item in question["answer"]["blanks"]}
            if not {item["blank_id"] for item in answer["blanks"]} <= blank_ids:
                raise LearningError(422, "ANSWER_TYPE_MISMATCH", "答案引用了不存在的填空")

    def _attempt_question(self, subject: dict, attempt: dict, question_id: str) -> dict:
        document = self._version_document(subject, attempt["exam_id"], attempt["exam_version_id"])
        question = next((item for item in document["questions"] if item["id"] == question_id), None)
        if not question:
            raise LearningError(404, "RESOURCE_NOT_FOUND", "题目不存在")
        return question

    @staticmethod
    def _unanswered_question_ids(attempt: dict, answers: list[dict] | None = None) -> list[str]:
        answered_ids = {
            answer["question_id"]
            for answer in (answers if answers is not None else attempt.get("answers", []))
        }
        return [
            question["id"]
            for question in attempt["paper"]["questions"]
            if question["id"] not in answered_ids
        ]

    def _version_document(self, subject: dict, exam_id: str, version_id: str) -> dict:
        version = next(
            (item for item in subject.get("data", {}).get("exam_versions", []) if item["exam_id"] == exam_id and item["id"] == version_id),
            None,
        )
        if not version:
            raise LearningError(404, "RESOURCE_NOT_FOUND", "试卷版本不存在")
        return copy.deepcopy(version["document"])

    def _selected_model(self, subject_id: str, model_id: str | None) -> dict:
        selected = (
            model_id
            or self.learning.workspace_service.snapshot().get("current_model_id")
            or self.learning.get_chat(subject_id).get("active_model_id")
        )
        if not selected:
            raise LearningError(409, "CHAT_MODEL_NOT_SELECTED", "请先选择模型服务")
        return self.learning._model(selected)

    def _save_feedback(self, subject_id: str, attempt_id: str, feedback: dict) -> None:
        _, attempt = self.learning._find_owned("attempts", attempt_id)
        current_answer = next(
            (item for item in attempt["answers"] if item["question_id"] == feedback["question_id"]),
            None,
        )
        if current_answer is None or current_answer["answer"] != feedback["answer_snapshot"]:
            raise LearningError(409, "ATTEMPT_STATE_CONFLICT", "答案已更新，请重新请求反馈")
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

    def _record_structure_stage(self, started_at: int, started: float, status: str) -> None:
        self.operations.record_stage(
            "structure-validation",
            status=status,
            started_at=started_at,
            completed_at=self._now(),
            outer_elapsed_ms=max(0, round((time.perf_counter() - started) * 1000)),
            counters={"validation_failures": int(status == "failed")},
        )

    @staticmethod
    def _normalize_plan(item: dict) -> dict:
        return BlueprintQuestionPlan.model_validate(item).model_dump()

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
        return sum(
            (item.get("question") or {}).get("score", item.get("planned_score", 0))
            for item in questions
        )

    def _cancel_draft_generation(self, subject_id: str, draft_id: str) -> None:
        _, draft = self.learning._find_owned("exam_drafts", draft_id)
        timestamp = self._now()
        questions = [
            {
                **item,
                "status": "failed",
                "error": {
                    "code": "QUESTION_GENERATION_FAILED",
                    "message": "题目生成已取消",
                    "retryable": True,
                    "details": {},
                },
                "updated_at": timestamp,
            }
            if item["status"] in {"queued", "generating"} else item
            for item in draft["questions"]
        ]
        status = "editable" if any(item.get("question") for item in questions) else "failed"
        self._replace(subject_id, "exam_drafts", draft_id, {
            **draft,
            "status": status,
            "questions": questions,
            "updated_at": timestamp,
        })

    def _ensure_draft_operation_idle(self, draft: dict, question_id: str | None = None) -> None:
        if self.operations.has_active("exam-draft", draft["id"]):
            raise LearningError(409, "OPERATION_IN_PROGRESS", "试卷草稿仍有生成任务")
        if question_id and self.operations.has_active("question", question_id):
            raise LearningError(409, "OPERATION_IN_PROGRESS", "该题仍有生成任务")

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
