"""Contract-oriented subject, model, grounded chat, and artifact services."""
from __future__ import annotations

import asyncio
import base64
import json
import time
import uuid

from .domain import (
    MODEL_ADD,
    MODEL_CHECKING,
    MODEL_DELETE,
    MODEL_OK,
    MODEL_SET_VALIDATION,
    MODEL_UPDATE,
    SUBJECT_CREATE,
    SUBJECT_DELETE,
    SUBJECT_RENAME,
    SUBJECT_SWITCH,
)
from .model_client import ModelClientError
from .operations import OperationFailure
from .sources import SourceLibraryError


class LearningError(Exception):
    def __init__(self, status_code: int, code: str, message: str, *, retryable: bool = False, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.retryable = retryable
        self.details = details or {}


class LearningService:
    def __init__(self, workspace_service, source_library, operations, model_client, now=None, id_factory=None):
        self.workspace_service = workspace_service
        self.source_library = source_library
        self.operations = operations
        self.model_client = model_client
        self._now = now or (lambda: int(time.time() * 1000))
        self._ids = id_factory or (lambda prefix: f"{prefix}-{uuid.uuid4().hex}")

    # Subjects and models -------------------------------------------------

    def workspace(self) -> dict:
        snapshot = self.workspace_service.snapshot()
        return {
            "schema_version": snapshot["schema_version"],
            "active_subject_id": snapshot.get("active_subject_id"),
            "subjects": [self._subject_view(item, snapshot) for item in snapshot.get("subjects", [])],
            "models": [self._model_view(item) for item in snapshot.get("models", [])],
            "load_issue": self.workspace_service.store.last_load_issue,
        }

    def list_subjects(self) -> list[dict]:
        snapshot = self.workspace_service.snapshot()
        return [self._subject_view(item, snapshot) for item in snapshot.get("subjects", [])]

    def get_subject(self, subject_id: str) -> dict:
        snapshot = self.workspace_service.snapshot()
        return self._subject_view(self._subject(subject_id, snapshot), snapshot)

    def create_subject(self, name: str) -> dict:
        result = self.workspace_service.dispatch({"type": SUBJECT_CREATE, "name": name})
        self._require_dispatch(result, duplicate_status=409)
        return self.get_subject(result["subject_id"])

    def update_subject(self, subject_id: str, name: str) -> dict:
        result = self.workspace_service.dispatch({"type": SUBJECT_RENAME, "subject_id": subject_id, "name": name})
        self._require_dispatch(result, not_found_codes={"SUBJECT_NOT_FOUND"})
        return self.get_subject(subject_id)

    def activate_subject(self, subject_id: str) -> dict:
        result = self.workspace_service.dispatch({"type": SUBJECT_SWITCH, "subject_id": subject_id})
        self._require_dispatch(result, not_found_codes={"SUBJECT_NOT_FOUND"})
        return self.workspace()

    def delete_subject(self, subject_id: str) -> None:
        if self.operations.has_active_for_subject(subject_id):
            raise LearningError(409, "SUBJECT_DELETE_BLOCKED", "该科目仍有异步任务在运行")
        result = self.workspace_service.dispatch({"type": SUBJECT_DELETE, "subject_id": subject_id})
        self._require_dispatch(result, not_found_codes={"SUBJECT_NOT_FOUND"})

    def list_models(self) -> list[dict]:
        return [self._model_view(item) for item in self.workspace_service.snapshot().get("models", [])]

    def get_model(self, model_id: str) -> dict:
        return self._model_view(self._model(model_id))

    def create_model(self, payload: dict) -> dict:
        result = self.workspace_service.dispatch({"type": MODEL_ADD, **payload})
        self._require_dispatch(result, duplicate_status=409)
        return self.get_model(result["model_id"])

    def update_model(self, model_id: str, patch: dict) -> dict:
        existing = self._model(model_id)
        action = {
            "type": MODEL_UPDATE,
            "model_id": model_id,
            "provider": patch.get("provider", existing["provider"]),
            "model": patch.get("model", existing["model"]),
            "base_url": patch.get("base_url", existing["base_url"]),
            "api_key": existing.get("api_key", "") if "api_key" not in patch else (patch["api_key"] or ""),
            "capabilities": patch.get("capabilities", existing.get("capabilities")),
        }
        result = self.workspace_service.dispatch(action)
        self._require_dispatch(result, duplicate_status=409, not_found_codes={"MODEL_SERVICE_NOT_FOUND"})
        return self.get_model(model_id)

    def delete_model(self, model_id: str) -> None:
        self._model(model_id)
        if self.operations.has_active("model", model_id):
            raise LearningError(409, "OPERATION_IN_PROGRESS", "模型服务仍有验证任务在运行")
        result = self.workspace_service.dispatch({"type": MODEL_DELETE, "model_id": model_id})
        self._require_dispatch(result, not_found_codes={"MODEL_SERVICE_NOT_FOUND"})

    def verify_model(self, model_id: str) -> dict:
        profile = self._model(model_id)
        if self.operations.has_active("model", model_id):
            raise LearningError(409, "OPERATION_IN_PROGRESS", "模型服务正在验证")
        self.workspace_service.dispatch({
            "type": MODEL_SET_VALIDATION,
            "model_id": model_id,
            "validation": {"status": MODEL_CHECKING},
        })

        async def worker():
            try:
                response = await self.model_client.validate(profile)
            except ModelClientError as exc:
                self.workspace_service.dispatch({
                    "type": MODEL_SET_VALIDATION,
                    "model_id": model_id,
                    "validation": {"status": "error", "message": str(exc)},
                })
                raise OperationFailure(exc.code, str(exc), retryable=exc.code == "MODEL_CONNECTION_FAILED") from exc
            self.workspace_service.dispatch({
                "type": MODEL_SET_VALIDATION,
                "model_id": model_id,
                "validation": {
                    "status": MODEL_OK,
                    "message": f"验证通过：{response.get('provider')} / {response.get('model')}",
                },
            })
            return {"type": "model", "id": model_id}

        resource = {"type": "model", "id": model_id}
        operation = self.operations.start("model-verification", worker, resource=resource)
        return {"operation": operation, "resource": resource}

    # Chat ----------------------------------------------------------------

    def get_chat(self, subject_id: str) -> dict:
        subject = self._subject(subject_id)
        chat = subject.get("data", {}).get("learning_chat")
        if chat:
            return chat
        chat = self._new_chat(subject)
        self._set_chat(subject_id, chat)
        return chat

    def configure_chat(self, subject_id: str, patch: dict) -> dict:
        chat = self.get_chat(subject_id)
        source_ids = patch.get("source_version_ids", chat["source_version_ids"])
        grounding_mode = patch.get("grounding_mode", chat["grounding_mode"])
        self._validate_source_scope(subject_id, source_ids, grounding_mode)
        updated = {**chat, **patch, "source_version_ids": source_ids, "updated_at": self._now()}
        learning_mode = updated["learning_mode"]
        if learning_mode == "socratic" and updated.get("socratic_state") is None:
            updated["socratic_state"] = {"stage": "awaiting-attempt", "hint_level": 0, "answer_revealed": False}
        elif learning_mode != "socratic":
            updated["socratic_state"] = None
        self._set_chat(subject_id, updated)
        return updated

    def switch_chat_model(self, subject_id: str, model_id: str) -> dict:
        self._subject(subject_id)
        self._model(model_id)
        chat = {**self.get_chat(subject_id), "active_model_id": model_id, "updated_at": self._now()}
        self._set_chat(subject_id, chat)
        return chat

    def clear_chat(self, subject_id: str) -> None:
        active = self.operations.active_for_subject(subject_id, "chat-generation")
        if active:
            raise LearningError(409, "CHAT_GENERATION_IN_PROGRESS", "回答正在生成，请先停止")
        chat = self.get_chat(subject_id)
        self._set_chat(subject_id, {**chat, "messages": [], "updated_at": self._now()})

    def create_chat_message(self, subject_id: str, payload: dict) -> dict:
        if self.operations.active_for_subject(subject_id, "chat-generation"):
            raise LearningError(409, "CHAT_GENERATION_IN_PROGRESS", "已有回答正在生成")
        chat = self.get_chat(subject_id)
        intent = payload["intent"]
        if chat["learning_mode"] != "socratic" and intent not in {"ask"}:
            raise LearningError(409, "RESOURCE_CONFLICT", "当前学习方式不支持该学习动作")
        if chat["learning_mode"] == "socratic" and intent == "start" and not chat.get("goal"):
            raise LearningError(409, "RESOURCE_CONFLICT", "请先配置苏格拉底式学习目标")

        model_id = payload.get("model_id") or chat.get("active_model_id")
        if not model_id:
            raise LearningError(409, "CHAT_MODEL_NOT_SELECTED", "请先选择模型服务")
        profile = self._model(model_id)
        source_ids = payload.get("source_version_ids", chat["source_version_ids"])
        grounding_mode = payload.get("grounding_mode", chat["grounding_mode"])
        self._validate_source_scope(subject_id, source_ids, grounding_mode)
        selection = payload.get("selection")
        if selection and selection.get("image_asset") and not profile.get("capabilities", {}).get("vision"):
            raise LearningError(409, "IMAGE_INPUT_UNSUPPORTED", "当前模型不支持图片输入，请更换具备视觉能力的模型")
        if not profile.get("capabilities", {}).get("vision") and any(
            self.source_library.get_version(version_id).get("assets")
            for version_id in source_ids
        ):
            raise LearningError(409, "IMAGE_INPUT_UNSUPPORTED", "选定资料包含图片，请更换具备视觉能力的模型")

        timestamp = self._now()
        content = payload.get("content") or self._intent_label(intent)
        user_message = {
            "id": self._ids("message"),
            "role": "user",
            "intent": intent,
            "content": [self._markdown_block(content)],
            "status": "complete",
            "grounding_mode": grounding_mode,
            "grounding_result": None,
            "citations": [],
            "selection": selection,
            "model": None,
            "error": None,
            "created_at": timestamp,
            "updated_at": timestamp,
            "completed_at": timestamp,
        }
        assistant_id = self._ids("message")
        assistant = {
            "id": assistant_id,
            "role": "assistant",
            "intent": intent,
            "content": [],
            "status": "queued",
            "grounding_mode": grounding_mode,
            "grounding_result": None,
            "citations": [],
            "selection": selection,
            "model": self._model_snapshot(profile),
            "error": None,
            "created_at": timestamp,
            "updated_at": timestamp,
            "completed_at": None,
        }
        chat = {
            **chat,
            "active_model_id": model_id,
            "messages": [*chat["messages"], user_message, assistant],
            "updated_at": timestamp,
        }
        self._set_chat(subject_id, chat)

        async def worker():
            self._update_message(subject_id, assistant_id, {"status": "generating", "updated_at": self._now()})
            query = payload.get("content") or chat.get("goal") or "学习目标"
            try:
                anchors = [] if grounding_mode == "general-knowledge" else self.source_library.retrieve(query, source_ids)
                if grounding_mode == "strict" and not anchors:
                    self._complete_message(
                        subject_id,
                        assistant_id,
                        "选定资料未覆盖这个问题，我无法仅依据资料回答。",
                        "not-covered",
                        [],
                        intent,
                    )
                    return {"type": "chat-message", "id": assistant_id}
                citations = [self.source_library.create_citation(anchor) for anchor in anchors]
                messages = self._grounded_messages(chat, payload, anchors, grounding_mode, profile)
                response = await self.model_client.chat(profile, messages)
                result = (
                    "general-knowledge"
                    if grounding_mode == "general-knowledge"
                    else "supplemental" if grounding_mode == "supplemental" else "covered"
                )
                self._complete_message(subject_id, assistant_id, response.get("text") or "", result, citations, intent)
                return {"type": "chat-message", "id": assistant_id}
            except asyncio.CancelledError:
                self._update_message(subject_id, assistant_id, {
                    "status": "stopped",
                    "updated_at": self._now(),
                    "completed_at": self._now(),
                })
                raise
            except (LearningError, ModelClientError, SourceLibraryError) as exc:
                code = getattr(exc, "code", "MODEL_INVALID_RESPONSE")
                self._fail_message(subject_id, assistant_id, code, str(exc))
                raise OperationFailure(code, str(exc), retryable=getattr(exc, "retryable", False)) from exc

        resource = {"type": "chat-message", "id": assistant_id}
        operation = self.operations.start(
            "chat-generation",
            worker,
            subject_id=subject_id,
            resource=resource,
        )
        return {"operation": operation, "resource": resource}

    def stop_chat(self, subject_id: str) -> dict:
        self._subject(subject_id)
        operation = self.operations.active_for_subject(subject_id, "chat-generation")
        if not operation:
            raise LearningError(404, "RESOURCE_NOT_FOUND", "当前没有正在生成的回答")
        operation = self.operations.cancel(operation["id"])
        return {"operation": operation, "resource": operation.get("resource")}

    # Crash course artifacts ---------------------------------------------

    def generate_crash_course(self, subject_id: str, payload: dict) -> dict:
        self._subject(subject_id)
        self._validate_source_scope(subject_id, payload["source_version_ids"], payload["grounding_mode"])
        chat = self.get_chat(subject_id)
        model_id = payload.get("model_id") or chat.get("active_model_id")
        if not model_id:
            raise LearningError(409, "CHAT_MODEL_NOT_SELECTED", "请先选择模型服务")
        profile = self._model(model_id)
        artifact_id = self._ids("artifact")
        resource = {"type": "learning-artifact", "id": artifact_id}

        async def worker():
            try:
                anchors = self.source_library.retrieve(payload["goal"], payload["source_version_ids"], limit=20)
                if not anchors:
                    raise OperationFailure("GROUNDING_SOURCE_REQUIRED", "选定资料未覆盖该学习目标")
                citations = [self.source_library.create_citation(anchor) for anchor in anchors]
                context = self._anchors_text(anchors)
                response = await self.model_client.chat(profile, [{
                    "role": "user",
                    "content": (
                        "请严格根据以下资料生成章节速成目录，只返回 JSON："
                        '{"title":"...","knowledge_points":[{"title":"...","explanation":"...",'
                        '"key_points":["..."],"self_test":{"prompt":"...","answer":"..."}}]}。\n\n'
                        f"学习目标：{payload['goal']}\n\n资料片段：\n{context}"
                    ),
                }])
                result = json.loads(response["text"])
                points = result["knowledge_points"]
                if not isinstance(points, list) or not points:
                    raise ValueError("knowledge_points is required")
                timestamp = self._now()
                artifact = {
                    "id": artifact_id,
                    "subject_id": subject_id,
                    "type": "crash-course-outline",
                    "title": result.get("title") or payload["goal"],
                    "chat_id": chat["id"],
                    "source_version_ids": payload["source_version_ids"],
                    "grounding_mode": payload["grounding_mode"],
                    "knowledge_points": [
                        {
                            "id": self._ids("knowledge-point"),
                            "title": point["title"],
                            "explanation": [self._markdown_block(point["explanation"])],
                            "key_points": point["key_points"],
                            "citations": citations,
                            "self_test": {
                                "prompt": [self._markdown_block(point["self_test"]["prompt"])],
                                "answer": [self._markdown_block(point["self_test"]["answer"])],
                            },
                        }
                        for point in points
                    ],
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
                self._append_artifact(subject_id, artifact)
                return resource
            except (ModelClientError, SourceLibraryError, ValueError, KeyError, json.JSONDecodeError) as exc:
                code = getattr(exc, "code", "MODEL_INVALID_RESPONSE")
                raise OperationFailure(code, str(exc)) from exc

        operation = self.operations.start(
            "crash-course-generation",
            worker,
            subject_id=subject_id,
            resource=resource,
        )
        return {"operation": operation, "resource": resource}

    def list_artifacts(self, subject_id: str) -> list[dict]:
        subject = self._subject(subject_id)
        return subject.get("data", {}).get("artifacts", [])

    def get_artifact(self, artifact_id: str) -> dict:
        _, artifact = self._find_owned("artifacts", artifact_id)
        return artifact

    def delete_artifact(self, artifact_id: str) -> None:
        subject, _ = self._find_owned("artifacts", artifact_id)
        self._mutate(subject["id"], lambda data: {
            **data,
            "artifacts": [item for item in data.get("artifacts", []) if item["id"] != artifact_id],
        })

    # Internal helpers ----------------------------------------------------

    def _subject(self, subject_id: str, snapshot: dict | None = None) -> dict:
        workspace = snapshot or self.workspace_service.snapshot()
        subject = next((item for item in workspace.get("subjects", []) if item["id"] == subject_id), None)
        if not subject:
            raise LearningError(404, "RESOURCE_NOT_FOUND", "科目空间不存在")
        return subject

    def _model(self, model_id: str) -> dict:
        model = next((item for item in self.workspace_service.snapshot().get("models", []) if item["id"] == model_id), None)
        if not model:
            raise LearningError(404, "RESOURCE_NOT_FOUND", "模型服务不存在")
        return model

    def _subject_view(self, subject: dict, snapshot: dict) -> dict:
        data = subject.get("data", {})
        return {
            "id": subject["id"],
            "name": subject["name"],
            "active": snapshot.get("active_subject_id") == subject["id"],
            "counts": {
                "sources": len(data.get("sources", [])),
                "artifacts": len(data.get("artifacts", [])),
                "exam_blueprints": len(data.get("exam_blueprints", [])),
                "exam_drafts": len(data.get("exam_drafts", [])),
                "exams": len(data.get("exams", [])),
            },
            "created_at": subject["created_at"],
            "updated_at": subject["updated_at"],
        }

    @staticmethod
    def _model_view(model: dict) -> dict:
        validation = model.get("last_validation") or {"status": "unknown", "checked_at": None, "message": None}
        capabilities = model.get("capabilities") or {}
        return {
            "id": model["id"],
            "provider": model["provider"],
            "model": model["model"],
            "base_url": model["base_url"],
            "has_api_key": bool(model.get("api_key")),
            "capabilities": {
                "text": True,
                "vision": bool(capabilities.get("vision")),
                "source": capabilities.get("source", "configured"),
            },
            "validation": validation,
            "created_at": model["created_at"],
            "updated_at": model["updated_at"],
        }

    def _new_chat(self, subject: dict) -> dict:
        timestamp = self._now()
        source_ids = [
            item["current_version"]["id"]
            for item in subject.get("data", {}).get("sources", [])
            if item.get("status") == "ready" and item.get("current_version")
        ]
        return {
            "id": self._ids("chat"),
            "subject_id": subject["id"],
            "learning_mode": "chat",
            "goal": None,
            "grounding_mode": "strict" if source_ids else "general-knowledge",
            "source_version_ids": source_ids,
            "active_model_id": None,
            "socratic_state": None,
            "messages": [],
            "artifact_ids": [],
            "created_at": timestamp,
            "updated_at": timestamp,
        }

    def _validate_source_scope(self, subject_id: str, version_ids: list[str], grounding_mode: str) -> None:
        if grounding_mode in {"strict", "supplemental"} and not version_ids:
            raise LearningError(409, "GROUNDING_SOURCE_REQUIRED", "当前依据模式需要至少选择一份资料")
        for version_id in version_ids:
            try:
                version = self.source_library.get_version(version_id)
                source = self.source_library.get_source(version["source_id"])
            except SourceLibraryError as exc:
                raise LearningError(exc.status_code, exc.code, str(exc)) from exc
            if source["subject_id"] != subject_id or version["status"] != "ready":
                raise LearningError(409, "SOURCE_UNAVAILABLE", "选定资料不属于当前科目或尚不可用")

    def _set_chat(self, subject_id: str, chat: dict) -> None:
        self._mutate(subject_id, lambda data: {**data, "learning_chat": chat})

    def _update_message(self, subject_id: str, message_id: str, changes: dict) -> None:
        chat = self.get_chat(subject_id)
        updated = {
            **chat,
            "messages": [
                {**message, **changes} if message["id"] == message_id else message
                for message in chat["messages"]
            ],
            "updated_at": self._now(),
        }
        self._set_chat(subject_id, updated)

    def _complete_message(self, subject_id: str, message_id: str, text: str, result: str, citations: list[dict], intent: str) -> None:
        timestamp = self._now()
        chat = self.get_chat(subject_id)
        state = self._next_socratic_state(chat.get("socratic_state"), intent) if chat["learning_mode"] == "socratic" else None
        updated = {
            **chat,
            "socratic_state": state,
            "messages": [
                {
                    **message,
                    "content": [self._markdown_block(text)],
                    "status": "complete",
                    "grounding_result": result,
                    "citations": citations,
                    "updated_at": timestamp,
                    "completed_at": timestamp,
                }
                if message["id"] == message_id else message
                for message in chat["messages"]
            ],
            "updated_at": timestamp,
        }
        self._set_chat(subject_id, updated)

    def _fail_message(self, subject_id: str, message_id: str, code: str, message: str) -> None:
        timestamp = self._now()
        self._update_message(subject_id, message_id, {
            "status": "error",
            "error": {"code": code, "message": message, "retryable": False, "details": {}},
            "updated_at": timestamp,
            "completed_at": timestamp,
        })

    def _grounded_messages(self, chat: dict, payload: dict, anchors: list[dict], grounding_mode: str, profile: dict) -> list[dict]:
        intent = payload["intent"]
        instruction = "请回答用户问题。"
        if grounding_mode == "strict":
            instruction = "只能依据提供的资料片段回答，不要补充片段之外的知识。"
        elif grounding_mode == "supplemental":
            instruction = "先明确说明资料依据，再把资料外补充内容单独标为“补充通用知识”。"
        if chat["learning_mode"] == "socratic":
            instruction += self._socratic_instruction(intent, chat.get("socratic_state"))
        context = self._anchors_text(anchors)
        question = payload.get("content") or self._intent_label(intent)
        text = f"{instruction}\n\n资料片段：\n{context or '无'}\n\n用户输入：{question}"
        content: str | list[dict] = text
        image_blocks = [
            block
            for anchor in anchors
            for block in anchor.get("content", [])
            if block.get("type") == "image"
        ]
        selection = payload.get("selection") or {}
        if selection.get("image_asset"):
            image_blocks.append({"asset": selection["image_asset"]})
        if image_blocks:
            if not profile.get("capabilities", {}).get("vision"):
                raise LearningError(409, "IMAGE_INPUT_UNSUPPORTED", "当前模型不支持图片输入")
            parts = [{"type": "text", "text": text}]
            for block in image_blocks:
                asset = block["asset"]
                raw, mime_type = self.source_library.get_asset(asset["source_version_id"], asset["asset_id"])
                encoded = base64.b64encode(raw).decode("ascii")
                parts.append({"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}})
            content = parts
        return [{"role": "user", "content": content}]

    @staticmethod
    def _anchors_text(anchors: list[dict]) -> str:
        parts = []
        for anchor in anchors:
            text = []
            for block in anchor.get("content", []):
                if block.get("type") == "markdown":
                    text.append(block.get("text", ""))
                elif block.get("type") == "table":
                    text.append(" | ".join(block.get("columns", [])))
                    text.extend(" | ".join(row) for row in block.get("rows", []))
            if text:
                parts.append(f"[{anchor['location']['label']}]\n" + "\n".join(text))
        return "\n\n".join(parts)

    @staticmethod
    def _socratic_instruction(intent: str, state: dict | None) -> str:
        if intent == "request-explanation":
            return " 用户明确要求直接解释，可以展示完整解释，随后要求复述。"
        if intent == "request-hint":
            level = min((state or {}).get("hint_level", 0) + 1, 3)
            return f" 只给第 {level} 层提示，不直接泄漏完整答案，并要求用户继续尝试。"
        if intent in {"start", "attempt"}:
            return " 一次只推进一个学习动作，先让用户尝试；纠错需指出错误点、资料依据和下一步。"
        if intent == "restate":
            return " 检查用户复述，随后给一个短变式自测。"
        return " 一次只推进一个需要用户回应的学习动作。"

    @staticmethod
    def _next_socratic_state(state: dict | None, intent: str) -> dict:
        current = state or {"stage": "awaiting-attempt", "hint_level": 0, "answer_revealed": False}
        if intent == "request-hint":
            return {**current, "stage": "hinting", "hint_level": min(current["hint_level"] + 1, 3)}
        if intent == "request-explanation":
            return {**current, "stage": "awaiting-restate", "answer_revealed": True}
        if intent == "attempt":
            return {**current, "stage": "correcting"}
        if intent == "restate" or intent == "request-self-test":
            return {**current, "stage": "self-testing"}
        if intent == "self-test-answer":
            return {**current, "stage": "completed"}
        return {**current, "stage": "awaiting-attempt"}

    def _append_artifact(self, subject_id: str, artifact: dict) -> None:
        def update(data):
            chat = data["learning_chat"]
            return {
                **data,
                "artifacts": [*data.get("artifacts", []), artifact],
                "learning_chat": {
                    **chat,
                    "artifact_ids": [*chat.get("artifact_ids", []), artifact["id"]],
                    "updated_at": self._now(),
                },
            }
        self._mutate(subject_id, update)

    def _find_owned(self, collection: str, resource_id: str) -> tuple[dict, dict]:
        for subject in self.workspace_service.snapshot().get("subjects", []):
            resource = next(
                (item for item in subject.get("data", {}).get(collection, []) if item.get("id") == resource_id),
                None,
            )
            if resource:
                return subject, resource
        raise LearningError(404, "RESOURCE_NOT_FOUND", "资源不存在")

    def _mutate(self, subject_id: str, update) -> dict:
        data = self.workspace_service.update_subject_data(subject_id, update)
        if data is None:
            raise LearningError(404, "RESOURCE_NOT_FOUND", "科目空间不存在")
        if self.workspace_service.last_storage_error:
            raise LearningError(500, "STORAGE_WRITE_FAILED", "无法保存本地数据", retryable=True)
        return data

    def _model_snapshot(self, profile: dict) -> dict:
        return {
            "model_id": profile["id"],
            "provider": profile["provider"],
            "model": profile["model"],
            "base_url": profile["base_url"],
            "capabilities": self._model_view(profile)["capabilities"],
        }

    def _markdown_block(self, text: str) -> dict:
        return {"id": self._ids("block"), "type": "markdown", "text": text}

    @staticmethod
    def _intent_label(intent: str) -> str:
        return {
            "start": "开始学习",
            "request-hint": "请给我一个提示",
            "request-explanation": "请直接解释",
            "request-self-test": "请给我一个变式自测",
        }.get(intent, intent)

    @staticmethod
    def _require_dispatch(result: dict, *, duplicate_status: int = 400, not_found_codes: set[str] | None = None) -> None:
        if result.get("ok"):
            if result.get("persisted") is False:
                raise LearningError(500, "STORAGE_WRITE_FAILED", "无法保存本地数据", retryable=True)
            return
        error = result.get("error") or {}
        code = error.get("code", "RESOURCE_CONFLICT")
        if code in (not_found_codes or set()):
            status = 404
            code = "RESOURCE_NOT_FOUND"
        elif code.endswith("DUPLICATE"):
            status = duplicate_status
        else:
            status = 409
        raise LearningError(status, code, error.get("message", "操作失败"))
