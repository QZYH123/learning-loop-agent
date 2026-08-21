"""Exam blueprint, draft generation, attempts, and feedback services."""
from __future__ import annotations

import asyncio
import copy
import json
import math
import re
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
        timestamp = self._now()
        blueprint_id = self._ids("blueprint")
        seed = self._default_blueprint_fields(subject_id, payload)
        blueprint = {
            "id": blueprint_id,
            "subject_id": subject_id,
            "prompt": payload["prompt"],
            "title": seed["title"] if payload.get("use_defaults") else "正在解析组卷要求",
            "status": "parsing",
            "syllabus": seed["syllabus"] if payload.get("use_defaults") else [],
            "source_version_ids": source_ids,
            "grounding_mode": payload["grounding_mode"],
            "question_plan": seed["question_plan"] if payload.get("use_defaults") else [],
            "total_score": seed["total_score"] if payload.get("use_defaults") else 1.0,
            "duration_minutes": seed["duration_minutes"] if payload.get("use_defaults") else None,
            "issues": [],
            "confirmed_at": None,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        self._append(subject_id, "exam_blueprints", blueprint)
        resource = {"type": "exam-blueprint", "id": blueprint_id}

        async def worker():
            if payload.get("use_defaults"):
                self._commit_blueprint_draft(subject_id, blueprint, seed)
                return resource
            try:
                profile = self._selected_model(subject_id, payload.get("model_id"))
                anchors = [] if payload["grounding_mode"] == "general-knowledge" else self.sources.retrieve(payload["prompt"], source_ids, limit=12)
                if payload["grounding_mode"] == "strict" and not anchors:
                    self._record_structure_stage(self._now(), time.perf_counter(), "failed")
                    raise OperationFailure("GROUNDING_SOURCE_REQUIRED", "选定资料未覆盖组卷要求")
                grounding_instruction = {
                    "strict": "只使用相关资料中的内容组卷。",
                    "supplemental": "优先使用相关资料，资料外的补充内容需要与资料依据区分。",
                    "general-knowledge": "使用通用知识组卷，并明确该蓝图未依据用户资料。",
                }[payload["grounding_mode"]]
                missed_points = self._recent_missed_knowledge_points(subject_id)
                missed_section = ""
                if missed_points:
                    missed_section = (
                        "\n\n参考错点（仅当用户表达复习、巩固、再出一套等意图时才纳入考纲，否则忽略）："
                        + "、".join(missed_points)
                    )
                prompt = (
                    "把组卷要求解析为 JSON，只返回："
                    '{"title":"...","syllabus":["..."],"question_plan":['
                    '{"type":"single-choice","count":1,"difficulty":"medium","score_each":5}],'
                    '"total_score":5,"duration_minutes":30}。题型可用 single-choice、multiple-choice、fill-blank、'
                    "true-false、short-answer、argumentation、extended-response。"
                    "用户没写明题型、题量或分值时，用一份适合练习的默认套卷补全，不要省略 question_plan。\n"
                    f"{grounding_instruction}\n\n"
                    f"用户要求：{payload['prompt']}\n\n相关资料：\n{self.learning._anchors_text(anchors) or '无'}"
                    f"{missed_section}"
                )
                response = await self.model_client.chat(profile, [{
                    "role": "user",
                    "content": self.learning._grounded_content(prompt, anchors, profile),
                }])
                validation_started_at = self._now()
                validation_started = time.perf_counter()
                try:
                    parsed = self._coerce_blueprint_parse(response["text"], seed)
                except (ValueError, KeyError, TypeError, json.JSONDecodeError, ValidationError):
                    self._record_structure_stage(validation_started_at, validation_started, "failed")
                    parsed = {
                        **seed,
                        "issues": list(seed.get("issues") or []) + [self._default_blueprint_issue()],
                    }
                else:
                    self._record_structure_stage(validation_started_at, validation_started, "succeeded")
                self._commit_blueprint_draft(subject_id, blueprint, parsed)
                return resource
            except asyncio.CancelledError:
                self._fail_blueprint(subject_id, blueprint, "组卷蓝图解析已取消")
                raise
            except OperationFailure:
                self._fail_blueprint(subject_id, blueprint, "选定资料未覆盖组卷要求")
                raise
            except LearningError as exc:
                if exc.code == "CHAT_MODEL_NOT_SELECTED":
                    self._fail_blueprint(subject_id, blueprint, "请先选择模型服务，或点「新建蓝图」用默认题型")
                    raise
                self._commit_blueprint_draft(subject_id, blueprint, {
                    **seed,
                    "issues": [{
                        "code": "BLUEPRINT_USED_DEFAULTS",
                        "severity": "warning",
                        "path": "question_plan",
                        "message": "题型题量使用了默认套卷，可在确认前修改",
                    }],
                })
                return resource
            except (ModelClientError, SourceLibraryError, ValidationError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                self._commit_blueprint_draft(subject_id, blueprint, {
                    **seed,
                    "issues": [{
                        "code": "BLUEPRINT_USED_DEFAULTS",
                        "severity": "warning",
                        "path": "question_plan",
                        "message": "题型题量使用了默认套卷，可在确认前修改",
                    }],
                })
                return resource

        operation = self.operations.start("blueprint-parsing", worker, subject_id=subject_id, resource=resource)
        return {"operation": operation, "resource": resource}

    def update_blueprint(self, blueprint_id: str, patch: dict) -> dict:
        subject, blueprint = self.learning._find_owned("exam_blueprints", blueprint_id)
        if blueprint["status"] == "parsing":
            raise LearningError(409, "OPERATION_IN_PROGRESS", "组卷蓝图仍在解析，暂不能编辑")
        if "title" in patch:
            title = str(patch.get("title") or "").strip()
            if not title:
                raise LearningError(422, "VALIDATION_FAILED", "蓝图标题不能为空")
            patch = {**patch, "title": title}
        if set(patch) <= {"title"}:
            updated = {**blueprint, "title": patch["title"], "updated_at": self._now()}
            validated = ExamBlueprint.model_validate(updated).model_dump()
            self._replace(subject["id"], "exam_blueprints", blueprint_id, validated)
            return validated
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
                bundle = await self._generate_exam_bundle(profile, blueprint, slots)
                known_briefs = {
                    slot_id: self._question_brief(question, next(
                        (item["ordinal"] for item in slots if item["id"] == slot_id),
                        None,
                    ))
                    for slot_id, question in bundle.items()
                }
                for slot in slots:
                    self._update_slot(subject["id"], draft_id, slot["id"], {"status": "generating", "updated_at": self._now()})
                    try:
                        packed = bundle.get(slot["id"])
                        question = packed or await self._generate_question(
                            profile,
                            blueprint,
                            slot,
                            avoid=[brief for item_id, brief in known_briefs.items() if item_id != slot["id"]],
                        )
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
                                "message": self._structure_error_message(exc),
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
                    else:
                        known_briefs[slot["id"]] = self._question_brief(question, slot["ordinal"])
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
        repair_hint = (slot.get("error") or {}).get("message")
        avoid = [
            self._question_brief(item["question"], item.get("ordinal"))
            for item in draft["questions"]
            if item["id"] != question_id and item.get("question")
        ]
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
                question = await self._generate_question(
                    profile,
                    blueprint,
                    slot,
                    repair_hint=repair_hint,
                    avoid=avoid,
                )
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
                    "error": {"code": "QUESTION_STRUCTURE_INVALID", "message": self._structure_error_message(exc), "retryable": True, "details": {}},
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

    def list_draft_revision_proposals(self, draft_id: str) -> list[dict]:
        subject, _ = self.learning._find_owned("exam_drafts", draft_id)
        return [
            item
            for item in subject.get("data", {}).get("draft_revision_proposals", [])
            if item.get("draft_id") == draft_id
        ]

    def create_draft_revision_proposal(self, draft_id: str, payload: dict) -> dict:
        subject, draft = self.learning._find_owned("exam_drafts", draft_id)
        if draft["status"] != "editable":
            raise LearningError(409, "RESOURCE_CONFLICT", "当前试卷草稿不可修改")
        if self.operations.active_for_subject(subject["id"], "exam-revision"):
            raise LearningError(409, "OPERATION_IN_PROGRESS", "已有修改正在生成，请稍候")
        questions = [copy.deepcopy(item["question"]) for item in draft["questions"] if item.get("question")]
        if not questions:
            raise LearningError(409, "QUESTION_STRUCTURE_INVALID", "草稿还没有可修改的题目")
        document = {
            "title": draft["title"],
            "instructions": draft.get("instructions") or [],
            "questions": questions,
        }
        scope = payload.get("scope") or {"kind": "whole-exam", "question_ids": [], "block_ids": []}
        self._validate_revision_scope(document, scope)
        profile = self._selected_model(subject["id"], payload.get("model_id"))
        timestamp = self._now()
        proposal_id = self._ids("draft-revision-proposal")
        proposal = {
            "id": proposal_id,
            "draft_id": draft_id,
            "instruction": payload["instruction"],
            "scope": scope,
            "status": "generating",
            "changes": [],
            "model": self.learning._model_snapshot(profile),
            "error": None,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        self._append(subject["id"], "draft_revision_proposals", proposal)
        resource = {"type": "draft-revision-proposal", "id": proposal_id}

        async def worker():
            try:
                response = await self.model_client.chat(profile, [{
                    "role": "user",
                    "content": (
                        "根据修改指令生成结构化差异预览，只返回 JSON："
                        '{"changes":[{"path":"/title","operation":"replace","summary":"...","before":"...","after":"..."}]}。'
                        "path 使用 JSON Pointer；move 操作的 before 填源路径，path 填目标路径。不要直接应用修改。\n\n"
                        f"修改范围：{json.dumps(scope, ensure_ascii=False)}\n"
                        f"试卷：{json.dumps(document, ensure_ascii=False)}\n\n指令：{payload['instruction']}"
                    ),
                }])
                parsed = self._parse_model_json(response["text"])
                if not isinstance(parsed, dict):
                    raise ValueError("changes is required")
                raw_changes = parsed.get("changes")
                changes = [ExamChange.model_validate(item).model_dump() for item in raw_changes]
                if not isinstance(changes, list) or not changes:
                    raise ValueError("changes is required")
                self._validate_revision_changes(document, proposal["scope"], changes)
                self._apply_revision_changes(copy.deepcopy(document), changes)
                ready = {**proposal, "status": "ready", "changes": changes, "updated_at": self._now()}
                self._replace(subject["id"], "draft_revision_proposals", proposal_id, ready)
                return resource
            except asyncio.CancelledError:
                canceled = {
                    **proposal,
                    "status": "failed",
                    "error": {"code": "REVISION_PROPOSAL_INVALID", "message": "修改提案生成已取消", "retryable": True, "details": {}},
                    "updated_at": self._now(),
                }
                self._replace(subject["id"], "draft_revision_proposals", proposal_id, canceled)
                raise
            except Exception as exc:
                failed = {
                    **proposal,
                    "status": "failed",
                    "error": {"code": "REVISION_PROPOSAL_INVALID", "message": self._structure_error_message(exc), "retryable": True, "details": {}},
                    "updated_at": self._now(),
                }
                self._replace(subject["id"], "draft_revision_proposals", proposal_id, failed)
                raise OperationFailure("REVISION_PROPOSAL_INVALID", "修改提案无效", retryable=True) from exc

        operation = self.operations.start("exam-revision", worker, subject_id=subject["id"], resource=resource)
        return {"operation": operation, "resource": resource}

    def apply_draft_revision_proposal(self, proposal_id: str) -> dict:
        subject, proposal = self.learning._find_owned("draft_revision_proposals", proposal_id)
        if proposal["status"] != "ready":
            raise LearningError(409, "RESOURCE_CONFLICT", "只能应用已就绪的修改预览")
        _, draft = self.learning._find_owned("exam_drafts", proposal["draft_id"])
        if draft["status"] != "editable":
            raise LearningError(409, "RESOURCE_CONFLICT", "当前试卷草稿不可修改")
        original_questions = [copy.deepcopy(item["question"]) for item in draft["questions"] if item.get("question")]
        original_ids = [item["id"] for item in original_questions]
        document = {
            "title": draft["title"],
            "instructions": draft.get("instructions") or [],
            "questions": original_questions,
        }
        try:
            updated_document = self._apply_revision_changes(document, proposal["changes"])
        except (LearningError, ValidationError, JsonPatchException, JsonPointerException, ValueError, KeyError, TypeError) as exc:
            message = str(exc or "")
            if "does not match the base document" in message or "not found" in message.lower():
                raise LearningError(409, "REVISION_PROPOSAL_STALE", "试卷已更新，该修改预览已失效") from exc
            raise LearningError(409, "REVISION_PROPOSAL_INVALID", "修改后的试卷结构无效") from exc
        restored_questions = []
        for index, question in enumerate(updated_document["questions"]):
            if index < len(original_ids) and question.get("id") != original_ids[index]:
                question = {**question, "id": original_ids[index]}
            restored_questions.append(question)
        updated_document = {**updated_document, "questions": restored_questions}
        questions_by_id = {item["id"]: item for item in updated_document["questions"]}
        slots = []
        for slot in draft["questions"]:
            question = questions_by_id.get(slot["id"], slot.get("question"))
            if question is None:
                slots.append(slot)
                continue
            slots.append({
                **slot,
                "question": question,
                "planned_type": question.get("type", slot.get("planned_type")),
                "status": "complete" if question.get("reliability") == "reliable" else "needs-review",
                "error": None,
                "updated_at": self._now(),
            })
        updated_draft = {
            **draft,
            "title": updated_document.get("title") or draft["title"],
            "instructions": updated_document.get("instructions", draft.get("instructions") or []),
            "questions": slots,
            "total_score": self._draft_score(slots),
            "updated_at": self._now(),
        }
        applied = {**proposal, "status": "applied", "updated_at": self._now()}
        self._replace(subject["id"], "exam_drafts", draft["id"], updated_draft)
        self._replace(subject["id"], "draft_revision_proposals", proposal_id, applied)
        for item in self.list_draft_revision_proposals(draft["id"]):
            if item["id"] != proposal_id and item["status"] == "ready":
                self.discard_draft_revision_proposal(item["id"])
        return self._draft_view(updated_draft)

    def discard_draft_revision_proposal(self, proposal_id: str) -> None:
        subject, proposal = self.learning._find_owned("draft_revision_proposals", proposal_id)
        discarded = {**proposal, "status": "discarded", "updated_at": self._now()}
        self._replace(subject["id"], "draft_revision_proposals", proposal_id, discarded)

    # Exams and attempts --------------------------------------------------

    def list_exams(self, subject_id: str) -> list[dict]:
        return self.learning._subject(subject_id).get("data", {}).get("exams", [])

    def get_exam(self, exam_id: str) -> dict:
        return self.learning._find_owned("exams", exam_id)[1]

    def update_exam(self, exam_id: str, patch: dict) -> dict:
        subject, exam = self.learning._find_owned("exams", exam_id)
        title = str(patch.get("title") or "").strip()
        if not title:
            raise LearningError(422, "VALIDATION_FAILED", "试卷标题不能为空")
        if title == (exam.get("document") or {}).get("title"):
            return exam
        timestamp = self._now()

        def update(data):
            current = next((item for item in data.get("exams", []) if item["id"] == exam_id), None)
            if current is None:
                raise LearningError(404, "RESOURCE_NOT_FOUND", "试卷不存在")
            document = {**copy.deepcopy(current["document"]), "title": title}
            updated_exam = {**current, "document": document, "updated_at": timestamp}
            version_id = current["current_version_id"]
            versions = []
            for item in data.get("exam_versions", []):
                if item["id"] == version_id:
                    version_document = copy.deepcopy(item.get("document") or document)
                    version_document["title"] = title
                    versions.append({**item, "document": version_document})
                else:
                    versions.append(item)
            return {
                **data,
                "exams": [updated_exam if item["id"] == exam_id else item for item in data.get("exams", [])],
                "exam_versions": versions,
            }

        self.learning._mutate(subject["id"], update)
        return self.get_exam(exam_id)

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

        def update(data):
            return {
                **data,
                "exams": [item for item in data.get("exams", []) if item["id"] != exam_id],
                "exam_versions": [item for item in data.get("exam_versions", []) if item["exam_id"] != exam_id],
                "exam_histories": [item for item in data.get("exam_histories", []) if item["exam_id"] != exam_id],
                "revision_proposals": [item for item in data.get("revision_proposals", []) if item["exam_id"] != exam_id],
                "attempts": [item for item in data.get("attempts", []) if item.get("exam_id") != exam_id],
                "exam_exports": [item for item in data.get("exam_exports", []) if item.get("exam_id") != exam_id],
            }

        self.learning._mutate(subject["id"], update)

    def list_exam_attempts(self, exam_id: str) -> list[dict]:
        subject, _ = self.learning._find_owned("exams", exam_id)
        items = [
            item
            for item in subject.get("data", {}).get("attempts", [])
            if item.get("exam_id") == exam_id
        ]
        items.sort(key=lambda item: item.get("updated_at", 0), reverse=True)
        return [self._attempt_summary(item) for item in items]

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
            "elapsed_ms": 0,
            "timing_started_at": timestamp,
            "created_at": timestamp,
            "updated_at": timestamp,
            "submitted_at": None,
            "completed_at": None,
            "grading_error": None,
        }
        self._append(subject["id"], "attempts", attempt)
        return self._attempt_view(attempt)

    def get_attempt(self, attempt_id: str) -> dict:
        return self._attempt_view(self.learning._find_owned("attempts", attempt_id)[1])

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
        return self._attempt_view(updated)

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
        if attempt["mode"] == "exam" and attempt.get("completion_status") != "completed":
            raise LearningError(409, "ANSWER_NOT_AVAILABLE", "考试模式标记完成前不能查看反馈")
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
        timestamp = self._now()
        updated = {
            **attempt,
            **self._apply_timing(attempt, running=False, timestamp=timestamp),
            "status": "paused",
            "updated_at": timestamp,
        }
        self._replace(subject["id"], "attempts", attempt_id, updated)
        return self._attempt_view(updated)

    def resume_attempt(self, attempt_id: str) -> dict:
        subject, attempt = self.learning._find_owned("attempts", attempt_id)
        if attempt.get("grading_status") in {"queued", "grading"}:
            raise LearningError(409, "OPERATION_IN_PROGRESS", "批改进行中，暂时不能继续作答")
        timestamp = self._now()
        timing = self._apply_timing(attempt, running=True, timestamp=timestamp)
        if attempt.get("completion_status") == "completed":
            updated = {
                **attempt,
                **timing,
                "completion_status": "in-progress",
                "completed_at": None,
                "status": "in-progress",
                "updated_at": timestamp,
            }
            self._replace(subject["id"], "attempts", attempt_id, updated)
            return self._attempt_view(updated)
        if attempt["status"] == "submitted" and attempt.get("grading_status") in {"completed", "failed", "stale"}:
            updated = {**attempt, **timing, "status": "in-progress", "updated_at": timestamp}
            self._replace(subject["id"], "attempts", attempt_id, updated)
            return self._attempt_view(updated)
        if attempt["status"] != "paused":
            raise LearningError(409, "ATTEMPT_STATE_CONFLICT", "当前作答不在暂停状态")
        updated = {**attempt, **timing, "status": "in-progress", "updated_at": timestamp}
        self._replace(subject["id"], "attempts", attempt_id, updated)
        return self._attempt_view(updated)

    def complete_attempt(self, attempt_id: str) -> dict:
        subject, attempt = self.learning._find_owned("attempts", attempt_id)
        if attempt.get("completion_status") == "completed":
            raise LearningError(409, "ATTEMPT_ALREADY_COMPLETED", "作答已经标记完成")
        if attempt["status"] not in {"in-progress", "paused"}:
            raise LearningError(409, "ATTEMPT_STATE_CONFLICT", "当前状态不能标记完成")
        timestamp = self._now()
        updated = {
            **attempt,
            **self._apply_timing(attempt, running=False, timestamp=timestamp),
            "completion_status": "completed",
            "completed_at": timestamp,
            "unanswered_question_ids": self._unanswered_question_ids(attempt),
            "updated_at": timestamp,
        }
        self._replace(subject["id"], "attempts", attempt_id, updated)
        return self._attempt_view(updated)

    def submit_attempt(self, attempt_id: str, complete: bool = False) -> dict:
        subject, attempt = self.learning._find_owned("attempts", attempt_id)
        if complete and attempt.get("completion_status") != "completed":
            attempt = self.complete_attempt(attempt_id)
        if attempt["status"] not in {"in-progress", "paused"} or attempt.get("grading_status") in {"queued", "grading"}:
            raise LearningError(409, "ATTEMPT_STATE_CONFLICT", "当前作答不能提交")
        if any(
            self.operations.has_active("feedback", f"feedback-{attempt_id}-{question['id']}")
            for question in self._version_document(subject, attempt["exam_id"], attempt["exam_version_id"])["questions"]
        ):
            raise LearningError(409, "OPERATION_IN_PROGRESS", "请等待当前题目反馈完成后再提交")
        timestamp = self._now()
        grading = {
            **attempt,
            **self._apply_timing(attempt, running=False, timestamp=timestamp),
            "status": "grading",
            "grading_status": "grading",
            "grading_error": None,
            "feedback": [],
            "updated_at": timestamp,
        }
        self._replace(subject["id"], "attempts", attempt_id, grading)
        resource = {"type": "attempt", "id": attempt_id}

        async def worker():
            try:
                current = self.learning._find_owned("attempts", attempt_id)[1]
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
                        profile = self._selected_model(subject["id"], None)
                        feedback.append(await self._subjective_feedback(
                            current,
                            question,
                            answer,
                            profile,
                            current["show_suggested_score"],
                            self._ids("feedback"),
                        ))
                if objective_count:
                    self.operations.record_stage(
                        "structure-validation",
                        started_at=objective_started_at,
                        completed_at=self._now(),
                        outer_elapsed_ms=max(0, round((time.perf_counter() - objective_started) * 1000)),
                        counters={},
                    )
                timestamp = self._now()
                submitted = {
                    **current,
                    "status": "submitted" if current.get("completion_status") == "completed" else attempt["status"],
                    "grading_status": "completed",
                    "feedback": feedback,
                    "updated_at": timestamp,
                    "submitted_at": timestamp,
                }
                self._replace(subject["id"], "attempts", attempt_id, submitted)
                return resource
            except asyncio.CancelledError:
                current = self.learning._find_owned("attempts", attempt_id)[1]
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
                current = self.learning._find_owned("attempts", attempt_id)[1]
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
        if attempt["mode"] == "exam" and attempt.get("completion_status") != "completed":
            raise LearningError(409, "ANSWER_NOT_AVAILABLE", "考试模式标记完成前不能查看答案和解析")
        document = self._version_document(subject, attempt["exam_id"], attempt["exam_version_id"])
        feedback_by_question = {item["question_id"]: item for item in attempt["feedback"]}
        answers = {item["question_id"]: item for item in attempt["answers"]}
        questions = document["questions"]
        if attempt["mode"] == "practice" and attempt.get("completion_status") != "completed":
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
                    parsed = self._parse_model_json(response["text"])
                    if not isinstance(parsed, dict):
                        raise ValueError("changes is required")
                    raw_changes = parsed.get("changes")
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

    async def _generate_exam_bundle(self, profile: dict, blueprint: dict, slots: list[dict]) -> dict[str, dict]:
        query = " ".join(blueprint.get("syllabus") or []) or (slots[0]["planned_type"] if slots else "")
        anchors = [] if blueprint["grounding_mode"] == "general-knowledge" else self.sources.retrieve(query, blueprint["source_version_ids"], limit=12)
        if blueprint["grounding_mode"] == "strict" and not anchors:
            return {}
        citations = [self.sources.create_citation(anchor) for anchor in anchors]
        slot_plan = [
            {
                "id": slot["id"],
                "ordinal": slot["ordinal"],
                "type": slot["planned_type"],
                "difficulty": slot["planned_difficulty"],
                "score": slot["planned_score"],
            }
            for slot in slots
        ]
        grounding_instruction = {
            "strict": "题干、答案和解析只能依据资料片段。",
            "supplemental": "优先依据资料片段；如需通用知识补充，必须与资料依据区分。",
            "general-knowledge": "使用通用知识生成，并将依据标为通用知识。",
        }[blueprint["grounding_mode"]]
        syllabus_focus = "、".join(blueprint.get("syllabus") or []) or "无"
        prompt = (
            "一次生成整张试卷的全部题目，只返回 JSON："
            '{"questions":[{"id":"槽位id","type":"...","stem":"...","options":[{"id":"A","content":"..."}],'
            '"answer":{},"explanation":"...","knowledge_points":["..."]}]}。'
            "questions 的 id、type、顺序必须与槽位一致。各题考查点、题干和选项不得重复。\n"
            f"槽位：{json.dumps(slot_plan, ensure_ascii=False)}\n"
            f"考纲重点：{syllabus_focus}\n"
            f"{grounding_instruction}\n\n"
            f"资料片段：\n{self.learning._anchors_text(anchors) or '无'}"
        )
        try:
            response = await self.model_client.chat(profile, [{
                "role": "user",
                "content": self.learning._grounded_content(prompt, anchors, profile),
            }])
            parsed = self._parse_model_json(response["text"])
            raw_questions = parsed.get("questions") if isinstance(parsed, dict) else parsed
            if not isinstance(raw_questions, list):
                return {}
            slots_by_id = {slot["id"]: slot for slot in slots}
            packed = {}
            for item in raw_questions:
                if not isinstance(item, dict):
                    continue
                slot = slots_by_id.get(item.get("id"))
                if slot is None:
                    try:
                        ordinal = int(item.get("ordinal"))
                    except (TypeError, ValueError):
                        ordinal = None
                    slot = next((row for row in slots if row["ordinal"] == ordinal), None)
                if slot is None or slot["id"] in packed:
                    continue
                try:
                    question = self._normalize_generated_question(item, slot, citations, blueprint["grounding_mode"])
                    question = self._validate_question_resources(
                        blueprint["subject_id"],
                        question,
                        allowed_version_ids=set(blueprint["source_version_ids"]) if blueprint["grounding_mode"] != "general-knowledge" else set(),
                    )
                except (LearningError, ValidationError, ValueError, KeyError, TypeError):
                    continue
                packed[slot["id"]] = question
            return packed
        except (ModelClientError, SourceLibraryError, ValidationError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return {}

    def _question_brief(self, question: dict, ordinal=None) -> dict:
        stem = ""
        for block in question.get("stem") or []:
            if isinstance(block, dict) and block.get("text"):
                stem = block["text"]
                break
            if isinstance(block, str) and block.strip():
                stem = block
                break
        return {
            "ordinal": ordinal,
            "type": question.get("type"),
            "stem": stem[:160],
            "knowledge_points": question.get("knowledge_points") or [],
        }

    def _brief_conflicts(self, question: dict, briefs: list[dict]) -> bool:
        current = self._question_brief(question)
        return any(self._stems_too_similar(current.get("stem"), brief.get("stem")) for brief in briefs)

    @staticmethod
    def _stems_too_similar(left: str | None, right: str | None) -> bool:
        compact = lambda text: re.sub(r"\s+", "", str(text or "").lower())
        first, second = compact(left), compact(right)
        if not first or not second:
            return False
        if first == second or first in second or second in first:
            return True
        return len(first) >= 12 and len(second) >= 12 and first[:12] == second[:12]

    async def _generate_question(
        self,
        profile: dict,
        blueprint: dict,
        slot: dict,
        *,
        repair_hint: str | None = None,
        avoid: list[dict] | None = None,
    ) -> dict:
        query = " ".join(item for item in [*blueprint.get("syllabus", []), slot["planned_type"]] if item)
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
        syllabus_focus = "、".join(blueprint.get("syllabus") or []) or "无"
        repair = f"上一轮失败：{repair_hint}。请按示例补全缺失字段后重新输出。\n" if repair_hint else ""
        avoid_section = ""
        if avoid:
            avoid_section = (
                "不要重复这些已有题目的题干、选项或考点：\n"
                + json.dumps(
                    [
                        {
                            "ordinal": item.get("ordinal"),
                            "stem": item.get("stem"),
                            "knowledge_points": item.get("knowledge_points") or [],
                        }
                        for item in avoid
                        if item.get("stem")
                    ],
                    ensure_ascii=False,
                )
                + "\n"
            )
        prompt = (
            f"生成一道 {slot['planned_type']} 题，难度 {slot['planned_difficulty']}，分值 {slot['planned_score']}。"
            "只返回一个 JSON 对象，不要 markdown 代码块，不要额外说明。"
            "必填字段：type、stem、answer、explanation、knowledge_points；选择题还要 options（至少两个，id 用 A/B/C）。"
            f"type 必须是 {slot['planned_type']}。"
            f"JSON 示例：{self._question_schema_example(slot['planned_type'], slot['planned_score'])}\n"
            f"{repair}{avoid_section}"
            f"考纲重点：{syllabus_focus}\n"
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
            raw = self._parse_model_json(response["text"])
            if isinstance(raw, list) and raw:
                raw = raw[0]
            if isinstance(raw, dict) and isinstance(raw.get("question"), dict):
                raw = raw["question"]
            if not isinstance(raw, dict):
                raise ValueError("generated question is not an object")
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
        question_type = slot["planned_type"]
        options = []
        if question_type in {"single-choice", "multiple-choice"}:
            options = self._normalize_options(raw.get("options") if raw.get("options") is not None else raw.get("choices"))
            if len(options) < 2:
                raise ValueError("choice questions require at least two options")
        stem = raw.get("stem") if raw.get("stem") not in (None, "") else raw.get("content") or raw.get("question")
        explanation = raw.get("explanation") if raw.get("explanation") not in (None, "") else raw.get("analysis") or raw.get("solution") or "见参考答案。"
        knowledge_points = self._string_list(raw.get("knowledge_points") if raw.get("knowledge_points") is not None else raw.get("knowledge_point"))
        if not knowledge_points:
            knowledge_points = [item for item in (slot.get("planned_type"),) if item]
        answer = self._normalize_answer(raw.get("answer"), question_type, options, slot["planned_score"])
        complete_evidence = bool(citations) or basis == "general-knowledge"
        question = {
            "id": slot["id"],
            "type": question_type,
            "stem": self._blocks(stem),
            "options": options,
            "score": float(slot["planned_score"]),
            "answer_area": {"lines": 0 if question_type in {"single-choice", "multiple-choice", "true-false"} else 3 if question_type == "fill-blank" else 8},
            "answer": answer,
            "explanation": self._blocks(explanation),
            "knowledge_points": knowledge_points,
            "evidence": {
                "basis": basis,
                "citations": citations,
                "status": "complete" if complete_evidence else "needs-review",
                "note": None if complete_evidence else "未找到足够的资料依据",
            },
            "reliability": "reliable" if complete_evidence else "needs-review",
        }
        return self._validate_manual_question(question, slot["id"])

    def _normalize_options(self, raw_options) -> list[dict]:
        if isinstance(raw_options, dict):
            raw_options = [{"id": key, "content": value} for key, value in raw_options.items()]
        if not isinstance(raw_options, list):
            return []
        options = []
        used_ids: set[str] = set()
        for index, item in enumerate(raw_options):
            option_id = chr(65 + index)
            content = item
            if isinstance(item, dict):
                option_id = str(item.get("id") or item.get("label") or option_id)
                if len(option_id) > 1 and option_id[1] in ".、．)）":
                    option_id = option_id[0]
                content = item.get("content")
                if content is None:
                    content = item.get("text") or item.get("label") or item.get("value") or item.get("option")
                if content is None and item.get("type") in {"markdown", "latex", "table", "image"}:
                    content = item
            if option_id in used_ids:
                option_id = f"{option_id}{index + 1}"
            used_ids.add(option_id)
            options.append({"id": option_id, "content": self._blocks(content)})
        if len(options) == 1:
            filler_id = "B" if options[0]["id"] != "B" else "C"
            options.append({"id": filler_id, "content": self._blocks("以上都不对")})
        return options

    def _normalize_answer(self, answer, question_type: str, options: list[dict] | None = None, planned_score: float = 1) -> dict:
        if question_type in {"single-choice", "multiple-choice"}:
            option_ids = [item["id"] for item in options or []]
            selected = self._extract_choice_ids(answer, option_ids)
            matched = [item for item in selected if item in option_ids]
            if not matched and selected:
                content_by_id = {
                    item["id"]: "".join(
                        block.get("text") or "" for block in item.get("content") or [] if isinstance(block, dict)
                    )
                    for item in options or []
                }
                for text in selected:
                    for option_id, content in content_by_id.items():
                        if text and (text in content or content in text):
                            matched.append(option_id)
                matched = list(dict.fromkeys(matched))
            if question_type == "single-choice" and len(matched) > 1:
                matched = matched[:1]
            if not matched:
                raise ValueError("choice answer is missing")
            return {"kind": "choice", "option_ids": matched}
        if question_type == "fill-blank":
            blanks = self._extract_blanks(answer)
            if not blanks:
                raise ValueError("fill-blank answer is missing blanks")
            return {"kind": "fill-blank", "blanks": blanks}
        if question_type == "true-false":
            value = self._extract_bool(answer)
            if value is None:
                raise ValueError("true-false answer is missing")
            return {"kind": "true-false", "value": value}
        return self._extract_subjective(answer, planned_score)

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
            "suggestions": [],
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

    def _timer_running(self, attempt: dict) -> bool:
        return attempt.get("status") == "in-progress" and attempt.get("completion_status") != "completed"

    def _hydrate_timing(self, attempt: dict) -> dict:
        if "elapsed_ms" in attempt:
            return {
                **attempt,
                "elapsed_ms": int(attempt.get("elapsed_ms") or 0),
                "timing_started_at": attempt.get("timing_started_at"),
            }
        started = attempt.get("created_at") if self._timer_running(attempt) else None
        return {**attempt, "elapsed_ms": 0, "timing_started_at": attempt.get("timing_started_at", started)}

    def _apply_timing(self, attempt: dict, *, running: bool, timestamp: int | None = None) -> dict:
        now = self._now() if timestamp is None else timestamp
        current = self._hydrate_timing(attempt)
        elapsed = int(current.get("elapsed_ms") or 0)
        started = current.get("timing_started_at")
        if self._timer_running(current) and started is not None:
            elapsed += max(0, now - int(started))
        return {"elapsed_ms": elapsed, "timing_started_at": now if running else None}

    def _attempt_view(self, attempt: dict) -> dict:
        viewed = self._hydrate_timing(attempt)
        if viewed["mode"] == "exam" and viewed.get("completion_status") != "completed":
            return {**viewed, "feedback": []}
        return viewed

    def _attempt_summary(self, attempt: dict) -> dict:
        viewed = self._attempt_view(attempt)
        questions = viewed.get("paper", {}).get("questions") or []
        question_ids = {item.get("id") for item in questions if item.get("id")}
        answers = viewed.get("answers") or []
        answered_ids = {item.get("question_id") for item in answers if item.get("question_id") in question_ids}
        return {
            "id": viewed["id"],
            "exam_id": viewed["exam_id"],
            "exam_version_id": viewed["exam_version_id"],
            "mode": viewed["mode"],
            "status": viewed["status"],
            "completion_status": viewed.get("completion_status", "in-progress"),
            "answered_count": len(answered_ids),
            "question_count": len(questions),
            "has_feedback": bool(viewed.get("feedback")),
            "created_at": viewed["created_at"],
            "updated_at": viewed["updated_at"],
        }

    UNMARKED_KNOWLEDGE_POINT = "未标考点"
    MISSED_GROUP_LIMIT = 30
    MISSED_QUESTIONS_PER_GROUP = 10
    RECENT_MISSED_POINT_LIMIT = 10

    def _is_missed_feedback(self, feedback: dict) -> bool:
        return feedback.get("correct") is False or bool(feedback.get("missed_points"))

    def _stem_preview(self, question: dict) -> str:
        text = self.learning._content_text(question.get("stem") or [])
        return re.sub(r"\s+", " ", text).strip()[:80]

    def _collect_missed_questions(self, subject_id: str) -> list[dict]:
        subject = self.learning._subject(subject_id)
        attempts = [item for item in subject.get("data", {}).get("attempts", []) if item.get("feedback")]
        ranked = sorted(
            enumerate(attempts),
            key=lambda pair: (pair[1].get("updated_at", 0), pair[0]),
            reverse=True,
        )
        collected: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for _, attempt in ranked:
            try:
                document = self._version_document(subject, attempt["exam_id"], attempt["exam_version_id"])
            except LearningError:
                continue
            questions = {item["id"]: item for item in document.get("questions", [])}
            exam_title = str(document.get("title") or "").strip() or "试卷"
            for feedback in attempt.get("feedback") or []:
                if not self._is_missed_feedback(feedback):
                    continue
                question = questions.get(feedback.get("question_id"))
                if not question:
                    continue
                key = (attempt["exam_id"], question["id"])
                if key in seen:
                    continue
                seen.add(key)
                collected.append({
                    "exam_id": attempt["exam_id"],
                    "exam_version_id": attempt["exam_version_id"],
                    "exam_title": exam_title,
                    "question_id": question["id"],
                    "question_type": question.get("type"),
                    "stem_preview": self._stem_preview(question),
                    "attempt_id": attempt["id"],
                    "missed_at": feedback.get("created_at") or attempt.get("updated_at") or 0,
                    "knowledge_points": [point for point in question.get("knowledge_points") or [] if point],
                })
        return collected

    def list_missed_questions(self, subject_id: str) -> list[dict]:
        grouped: dict[str, list[dict]] = {}
        for record in self._collect_missed_questions(subject_id):
            points = record["knowledge_points"] or [self.UNMARKED_KNOWLEDGE_POINT]
            item = {key: value for key, value in record.items() if key != "knowledge_points"}
            for point in points:
                grouped.setdefault(point, []).append(item)
        groups = []
        for point, questions in grouped.items():
            ordered = sorted(questions, key=lambda item: item["missed_at"], reverse=True)
            groups.append({
                "knowledge_point": point,
                "miss_count": len(questions),
                "questions": ordered[: self.MISSED_QUESTIONS_PER_GROUP],
            })
        groups.sort(key=lambda item: (-item["miss_count"], item["knowledge_point"]))
        return groups[: self.MISSED_GROUP_LIMIT]

    def _recent_missed_knowledge_points(self, subject_id: str) -> list[str]:
        collected: list[str] = []
        seen: set[str] = set()
        for record in self._collect_missed_questions(subject_id):
            for point in record["knowledge_points"]:
                if not point or point in seen:
                    continue
                seen.add(point)
                collected.append(point)
                if len(collected) >= self.RECENT_MISSED_POINT_LIMIT:
                    return collected
        return collected

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
        if isinstance(value, dict):
            return [self._coerce_block(value)]
        if isinstance(value, list):
            if not value:
                raise ValueError("content blocks must be a string or list")
            return [
                self._coerce_block(item) if isinstance(item, dict) else self.learning._markdown_block(str(item))
                for item in value
            ]
        raise ValueError("content blocks must be a string or list")

    def _coerce_block(self, item: dict) -> dict:
        block_type = item.get("type")
        block_id = item.get("id") or self._ids("block")
        if block_type == "markdown":
            return {"id": block_id, "type": "markdown", "text": str(item.get("text") or item.get("content") or "")}
        if block_type == "latex":
            return {
                "id": block_id,
                "type": "latex",
                "latex": str(item.get("latex") or item.get("text") or ""),
                "display": bool(item.get("display", False)),
            }
        if block_type == "table":
            return {
                "id": block_id,
                "type": "table",
                "columns": item.get("columns") or [],
                "rows": item.get("rows") or [],
            }
        if block_type == "image" and isinstance(item.get("asset"), dict):
            return {
                "id": block_id,
                "type": "image",
                "asset": item["asset"],
                "alt": item.get("alt"),
                "caption": item.get("caption"),
            }
        text = item.get("text") or item.get("content") or item.get("markdown") or item.get("value") or item.get("latex")
        if text is None:
            raise ValueError("content blocks must be a string or list")
        if isinstance(text, list):
            return self._blocks(text)[0]
        return self.learning._markdown_block(str(text))

    @staticmethod
    def _parse_model_json(text: str):
        if not isinstance(text, str) or not text.strip():
            raise json.JSONDecodeError("Expecting value", text or "", 0)
        stripped = text.strip()
        candidates = [stripped]
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", stripped, re.I)
        if fence:
            candidates.append(fence.group(1).strip())
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end > start:
            candidates.append(stripped[start : end + 1])
        seen: set[str] = set()
        last_error = None
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as exc:
                last_error = exc
        raise last_error or json.JSONDecodeError("Expecting value", stripped, 0)

    @staticmethod
    def _question_schema_example(question_type: str, score: float) -> str:
        examples = {
            "single-choice": (
                '{"type":"single-choice","stem":"题干","options":[{"id":"A","content":"选项A"},'
                '{"id":"B","content":"选项B"},{"id":"C","content":"选项C"},{"id":"D","content":"选项D"}],'
                '"answer":{"kind":"choice","option_ids":["A"]},"explanation":"解析","knowledge_points":["考点"]}'
            ),
            "multiple-choice": (
                '{"type":"multiple-choice","stem":"题干","options":[{"id":"A","content":"选项A"},'
                '{"id":"B","content":"选项B"},{"id":"C","content":"选项C"}],'
                '"answer":{"kind":"choice","option_ids":["A","C"]},"explanation":"解析","knowledge_points":["考点"]}'
            ),
            "fill-blank": (
                '{"type":"fill-blank","stem":"……____……","answer":{"kind":"fill-blank",'
                '"blanks":[{"id":"blank-1","acceptable_answers":["答案"]}]},"explanation":"解析","knowledge_points":["考点"]}'
            ),
            "true-false": (
                '{"type":"true-false","stem":"题干","answer":{"kind":"true-false","value":true},'
                '"explanation":"解析","knowledge_points":["考点"]}'
            ),
        }
        if question_type in examples:
            return examples[question_type]
        return (
            f'{{"type":"{question_type}","stem":"题干","answer":{{"kind":"subjective","reference_answer":"参考答案",'
            f'"scoring_points":[{{"id":"point-1","description":"得分点","score":{float(score)}}}] }},'
            '"explanation":"解析","knowledge_points":["考点"]}'
        )

    @staticmethod
    def _string_list(value) -> list[str]:
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        if not isinstance(value, list):
            return []
        items = []
        for item in value:
            if isinstance(item, str) and item.strip():
                items.append(item.strip())
            elif isinstance(item, dict):
                text = item.get("name") or item.get("title") or item.get("text") or item.get("point")
                if text:
                    items.append(str(text).strip())
        return [item for item in items if item]

    def _extract_choice_ids(self, answer, option_ids: list[str]) -> list[str]:
        if isinstance(answer, str):
            text = answer.strip()
            if text in option_ids:
                return [text]
            letter = text[:1].upper() if text else ""
            if letter in option_ids:
                return [letter]
            return [text] if text else []
        if isinstance(answer, bool):
            return []
        if isinstance(answer, (int, float)):
            index = int(answer)
            if 0 <= index < len(option_ids):
                return [option_ids[index]]
            if 1 <= index <= len(option_ids):
                return [option_ids[index - 1]]
            return []
        if isinstance(answer, list):
            selected = []
            for item in answer:
                selected.extend(self._extract_choice_ids(item, option_ids))
            return list(dict.fromkeys(selected))
        if isinstance(answer, dict):
            for key in ("option_ids", "options", "choices", "correct", "value", "answer", "id"):
                if answer.get(key) is None:
                    continue
                found = self._extract_choice_ids(answer[key], option_ids)
                if found:
                    return found
        return []

    @staticmethod
    def _extract_bool(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"true", "t", "yes", "y", "1", "对", "正确", "是", "√", "right"}:
                return True
            if text in {"false", "f", "no", "n", "0", "错", "错误", "否", "×", "wrong"}:
                return False
        if isinstance(value, dict):
            for key in ("value", "answer", "correct", "is_true"):
                if key in value:
                    found = ExamService._extract_bool(value[key])
                    if found is not None:
                        return found
        return None

    @staticmethod
    def _blank_definition(index: int, answers: list[str], blank_id: str | None = None) -> dict:
        return {
            "id": blank_id or f"blank-{index + 1}",
            "acceptable_answers": answers,
            "normalization": {"trim": True, "case_sensitive": False, "collapse_whitespace": True},
        }

    def _extract_blanks(self, answer) -> list[dict]:
        if isinstance(answer, str) and answer.strip():
            return [self._blank_definition(0, [answer.strip()])]
        if isinstance(answer, list):
            blanks = []
            for index, item in enumerate(answer):
                if isinstance(item, str) and item.strip():
                    blanks.append(self._blank_definition(index, [item.strip()]))
                elif isinstance(item, dict):
                    raw_answers = item.get("acceptable_answers") or item.get("answers") or item.get("value") or item.get("text")
                    if isinstance(raw_answers, str):
                        raw_answers = [raw_answers]
                    answers = [str(value).strip() for value in (raw_answers or []) if str(value).strip()]
                    if answers:
                        blanks.append(self._blank_definition(index, answers, item.get("id")))
            return blanks
        if isinstance(answer, dict):
            if answer.get("blanks") is not None:
                return self._extract_blanks(answer["blanks"])
            raw_answers = answer.get("acceptable_answers") or answer.get("answers") or answer.get("value") or answer.get("text")
            if raw_answers:
                return self._extract_blanks(raw_answers)
        return []

    def _extract_subjective(self, answer, planned_score: float) -> dict:
        points = []
        reference = answer
        if isinstance(answer, dict):
            reference = answer.get("reference_answer") or answer.get("answer") or answer.get("text") or answer.get("value") or "见得分点"
            raw_points = answer.get("scoring_points") or answer.get("points") or []
            if isinstance(raw_points, list):
                for index, point in enumerate(raw_points):
                    if isinstance(point, str) and point.strip():
                        points.append({
                            "id": f"point-{index + 1}",
                            "description": point.strip(),
                            "score": float(planned_score) / max(len(raw_points), 1),
                        })
                    elif isinstance(point, dict):
                        description = str(point.get("description") or point.get("text") or point.get("point") or "").strip()
                        if not description:
                            continue
                        points.append({
                            "id": point.get("id") or f"point-{index + 1}",
                            "description": description,
                            "score": float(point["score"] if point.get("score") is not None else planned_score / max(len(raw_points), 1)),
                        })
        elif isinstance(answer, list):
            reference = "；".join(str(item) for item in answer if item)
            return self._extract_subjective({"reference_answer": reference or "见得分点", "scoring_points": answer}, planned_score)
        if isinstance(reference, (dict, list)):
            reference_blocks = self._blocks(reference)
        else:
            reference_text = str(reference or "").strip() or "见得分点"
            reference_blocks = self._blocks(reference_text)
        if not points:
            description = reference_blocks[0].get("text") if reference_blocks and isinstance(reference_blocks[0], dict) else "要点"
            points = [{"id": "point-1", "description": str(description or "要点")[:200], "score": float(planned_score)}]
        return {"kind": "subjective", "reference_answer": reference_blocks, "scoring_points": points}

    @staticmethod
    def _structure_error_message(exc: Exception) -> str:
        if isinstance(exc, LearningError):
            return str(exc)
        text = str(exc or "")
        lowered = text.lower()
        if "blank" in lowered:
            return "填空题缺少填空定义，请重试生成"
        if "scoring_point" in lowered:
            return "主观题缺少得分点，请重试生成"
        if "content block" in lowered:
            return "题目正文格式无效，请重试生成"
        if "option" in lowered and "choice" in lowered:
            return "选择题缺少选项或答案，请重试生成"
        if "json" in lowered or "expecting" in lowered:
            return "题目生成结果无法解析，请重试"
        return "题目结构不完整，请重试生成"

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

    def _commit_blueprint_draft(self, subject_id: str, blueprint: dict, fields: dict) -> dict:
        updated = {
            **blueprint,
            "title": fields.get("title") or blueprint.get("title") or "练习卷",
            "status": "draft",
            "syllabus": fields.get("syllabus") or [],
            "question_plan": fields["question_plan"],
            "total_score": fields["total_score"],
            "duration_minutes": fields.get("duration_minutes"),
            "issues": fields.get("issues") or [],
            "updated_at": self._now(),
        }
        validated = ExamBlueprint.model_validate(updated).model_dump()
        self._replace(subject_id, "exam_blueprints", blueprint["id"], validated)
        return validated

    def _default_blueprint_fields(self, subject_id: str, payload: dict) -> dict:
        subject = self.learning._subject(subject_id)
        prompt = (payload.get("prompt") or "").strip()
        name = subject.get("name") or "本科目"
        title = prompt[:40] if prompt else f"{name}练习卷"
        if title in {"出一套练习卷", f"出一套{name}练习卷"}:
            title = f"{name}练习卷"
        plan = [self._normalize_plan(item) for item in self._default_question_plan(prompt)]
        total_score = float(sum(item["count"] * item["score_each"] for item in plan))
        issues = []
        if payload.get("use_defaults"):
            issues = [self._default_blueprint_issue()]
        return {
            "title": title or f"{name}练习卷",
            "syllabus": [name] if name and name != "本科目" else [],
            "question_plan": plan,
            "total_score": total_score,
            "duration_minutes": 45,
            "issues": issues,
        }

    @staticmethod
    def _default_blueprint_issue() -> dict:
        return {
            "code": "BLUEPRINT_USED_DEFAULTS",
            "severity": "warning",
            "path": "question_plan",
            "message": "题型题量使用了默认套卷，可在确认前修改",
        }

    @staticmethod
    def _default_question_plan(prompt: str) -> list[dict]:
        text = prompt or ""
        easy = any(token in text for token in ("简单", "基础", "入门", "easy"))
        hard = any(token in text for token in ("困难", "很难", "hard"))
        choice_difficulty = "hard" if hard and not easy else "easy"
        rest_difficulty = "hard" if hard and not easy else "medium" if not easy else "easy"
        return [
            {"type": "single-choice", "count": 4, "difficulty": choice_difficulty, "score_each": 10},
            {"type": "true-false", "count": 2, "difficulty": choice_difficulty, "score_each": 10},
            {"type": "fill-blank", "count": 2, "difficulty": rest_difficulty, "score_each": 10},
            {"type": "short-answer", "count": 1, "difficulty": rest_difficulty, "score_each": 20},
        ]

    def _coerce_blueprint_parse(self, text: str, seed: dict) -> dict:
        raw = self._parse_model_json(text)
        if isinstance(raw, list) and raw and isinstance(raw[0], dict):
            raw = raw[0]
        if not isinstance(raw, dict):
            raise ValueError("blueprint is not an object")
        title = str(raw.get("title") or seed["title"]).strip()[:200] or seed["title"]
        syllabus = self._string_list(raw.get("syllabus") if raw.get("syllabus") is not None else seed.get("syllabus"))
        plan_raw = raw.get("question_plan") if raw.get("question_plan") is not None else raw.get("plan")
        used_defaults = False
        try:
            plan = [self._normalize_plan(item) for item in plan_raw] if isinstance(plan_raw, list) else []
        except (ValidationError, KeyError, TypeError, ValueError):
            plan = []
        if not plan:
            plan = copy.deepcopy(seed["question_plan"])
            used_defaults = True
        try:
            total_score = float(raw["total_score"])
            if total_score <= 0:
                raise ValueError("total_score must be positive")
        except (KeyError, TypeError, ValueError):
            total_score = float(sum(item["count"] * item["score_each"] for item in plan))
        duration = raw.get("duration_minutes", seed.get("duration_minutes"))
        try:
            duration = int(duration) if duration is not None else None
        except (TypeError, ValueError):
            duration = seed.get("duration_minutes")
        issues = self._blueprint_issues(plan, total_score)
        if used_defaults:
            issues = [*issues, self._default_blueprint_issue()]
        return {
            "title": title,
            "syllabus": syllabus or seed.get("syllabus") or [],
            "question_plan": plan,
            "total_score": total_score,
            "duration_minutes": duration,
            "issues": issues,
        }

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
