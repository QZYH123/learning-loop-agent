"""Contract-oriented subject, model, grounded chat, and artifact services."""
from __future__ import annotations

import asyncio
import base64
import json
import time
import uuid

import httpx
from pydantic import ValidationError

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
from .api_models import LearningArtifact
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
        self.selection_resolver = None
        self.attachments = None

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
            except asyncio.CancelledError:
                self.workspace_service.dispatch({
                    "type": MODEL_SET_VALIDATION,
                    "model_id": model_id,
                    "validation": {"status": "unknown", "message": "模型服务验证已取消"},
                })
                raise
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

    def get_current_model(self) -> dict | None:
        model_id = self.workspace_service.snapshot().get("current_model_id")
        if not model_id:
            return None
        try:
            return self.get_model(model_id)
        except LearningError:
            self.workspace_service.update_workspace(lambda workspace: {**workspace, "current_model_id": None})
            return None

    def select_current_model(self, model_id: str) -> dict:
        model = self._model(model_id)
        self.workspace_service.update_workspace(lambda workspace: {**workspace, "current_model_id": model_id})
        return self._model_view(model)

    def discover_models(self, payload: dict) -> dict:
        provider = payload["provider"]
        base_url = payload["base_url"].rstrip("/")
        if provider == "ollama":
            url = base_url if base_url.endswith("/api/tags") else f"{base_url}/api/tags"
        else:
            url = base_url if base_url.endswith("/models") else f"{base_url}/models"
        headers = {}
        if payload.get("api_key"):
            headers["Authorization"] = f"Bearer {payload['api_key']}"
        try:
            response = httpx.get(url, headers=headers, timeout=8.0)
            response.raise_for_status()
            raw = response.json()
            entries = raw.get("models", []) if provider == "ollama" else raw.get("data", [])
            models = []
            for item in entries:
                name = item.get("name") or item.get("id")
                if not name:
                    continue
                models.append({"name": name, "capabilities": {"text": True, "vision": False}})
            return {"provider": provider, "models": models, "manual_model_allowed": True, "error": None}
        except (httpx.HTTPError, ValueError, TypeError):
            return {
                "provider": provider,
                "models": [],
                "manual_model_allowed": True,
                "error": {"code": "MODEL_DISCOVERY_FAILED", "message": "无法获取模型列表，可手动填写模型名", "retryable": True, "details": {}},
            }

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
        goal_changed = "goal" in patch and patch.get("goal") != chat.get("goal")
        if learning_mode == "socratic" and (updated.get("socratic_state") is None or goal_changed):
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
        self.workspace_service.update_workspace(lambda workspace: {**workspace, "current_model_id": model_id})
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
        if chat["learning_mode"] == "socratic":
            self._validate_socratic_intent(chat.get("socratic_state"), intent)

        model_id = payload.get("model_id") or self.workspace_service.snapshot().get("current_model_id") or chat.get("active_model_id")
        if not model_id:
            raise LearningError(409, "CHAT_MODEL_NOT_SELECTED", "请先选择模型服务")
        profile = self._model(model_id)
        source_ids = payload.get("source_version_ids", chat["source_version_ids"])
        grounding_mode = payload.get("grounding_mode", chat["grounding_mode"])
        if payload.get("only_use_specified_sources"):
            source_ids = list(payload.get("source_version_ids") or payload.get("focused_source_version_ids") or [])
            if not source_ids:
                raise LearningError(422, "VALIDATION_FAILED", "仅使用指定资料时必须提供资料版本")
        self._validate_source_scope(subject_id, source_ids, grounding_mode)
        focused_ids = [item for item in payload.get("focused_source_version_ids") or [] if item in source_ids]
        if payload.get("focused_source_version_ids") and len(focused_ids) != len(payload["focused_source_version_ids"]):
            raise LearningError(409, "SOURCE_VERSION_MISMATCH", "重点资料必须属于当前会话资料范围")
        attachment_ids = list(payload.get("attachment_ids") or [])
        attachment_inputs = self._attachment_inputs(subject_id, attachment_ids, profile)
        selection = payload.get("selection")
        selection_context = None
        if selection:
            if self.selection_resolver is None:
                raise LearningError(409, "CHAT_SELECTION_INVALID", "选区问答服务尚未就绪")
            resolved = self.selection_resolver(selection, include_context=True)
            if isinstance(resolved, tuple):
                selection, selection_context = resolved
            else:
                selection = resolved
            payload = {**payload, "selection": selection}
        if selection and selection.get("image_asset") and not profile.get("capabilities", {}).get("vision"):
            raise LearningError(409, "IMAGE_INPUT_UNSUPPORTED", "当前模型不支持图片输入，请更换具备视觉能力的模型")
        if not profile.get("capabilities", {}).get("vision"):
            image_only = any(
                self.source_library.get_source(self.source_library.get_version(version_id)["source_id"])["media_kind"] == "image"
                for version_id in source_ids
            )
            if image_only:
                raise LearningError(409, "IMAGE_INPUT_UNSUPPORTED", "选定资料是图片，请更换具备视觉能力的模型")

        timestamp = self._now()
        content = payload.get("content") or self._intent_label(intent)
        source_context = {
            "source_version_ids": source_ids,
            "focused_source_version_ids": focused_ids,
            "only_use_specified_sources": bool(payload.get("only_use_specified_sources")),
            "grounding_mode": grounding_mode,
            "selection": selection,
            "attachment_ids": attachment_ids,
            "citations": [],
        }
        user_message = {
            "id": self._ids("message"),
            "role": "user",
            "intent": intent,
            "content": [self._markdown_block(content)],
            "status": "complete",
            "grounding_mode": grounding_mode,
            "grounding_result": None,
            "citations": [],
            "source_context": source_context,
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
            "source_context": source_context,
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
                retrieval_ids = [*focused_ids, *[item for item in source_ids if item not in focused_ids]]
                anchors = [] if grounding_mode == "general-knowledge" else self.source_library.retrieve(
                    query,
                    retrieval_ids,
                    priority_version_ids=focused_ids,
                )
                selected_citations = [
                    self.source_library.get_citation(citation_id)
                    for citation_id in (selection or {}).get("citation_ids", [])
                ]
                has_selection_context = bool((selection or {}).get("selected_text") or (selection or {}).get("image_asset"))
                if grounding_mode == "strict" and not anchors and not selected_citations and not has_selection_context and not attachment_inputs:
                    self._complete_message(
                        subject_id,
                        assistant_id,
                        "选定资料未覆盖这个问题，我无法仅依据资料回答。",
                        "not-covered",
                        [],
                        intent,
                    )
                    return {"type": "chat-message", "id": assistant_id}
                citations = self._citations_for_anchors(anchors, selected_citations)
                messages = self._grounded_messages(
                    chat,
                    payload,
                    anchors,
                    grounding_mode,
                    profile,
                    selection_context,
                    attachment_inputs,
                )
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

    # Multi-session chat -------------------------------------------------

    def list_sessions(self, subject_id: str) -> dict:
        subject = self._subject(subject_id)
        data = subject.get("data", {})
        sessions = [self._session_view(item, subject_id) for item in data.get("sessions", [])]
        return {"items": sessions, "active_session_id": data.get("active_session_id")}

    def create_session(self, subject_id: str, payload: dict) -> dict:
        subject = self._subject(subject_id)
        source_version_ids = list(payload.get("source_version_ids") or [])
        self._validate_source_scope(subject_id, source_version_ids, "strict" if source_version_ids else "general-knowledge")
        timestamp = self._now()
        session = {
            "id": self._ids("session"),
            "subject_id": subject_id,
            "title": payload.get("title") or "新会话",
            "source_version_ids": source_version_ids,
            "messages": [],
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        self._mutate(subject_id, lambda data: {
            **data,
            "sessions": [*data.get("sessions", []), session],
            "active_session_id": session["id"],
        })
        return self._session_view(session, subject_id, active=True)

    def get_session(self, session_id: str) -> dict:
        subject, session = self._find_session(session_id)
        return self._session_view(session, subject["id"])

    def update_session(self, session_id: str, patch: dict) -> dict:
        subject, session = self._find_session(session_id)
        title = (patch.get("title") or "").strip()
        if not title:
            raise LearningError(422, "VALIDATION_FAILED", "会话标题不能为空")
        siblings = subject.get("data", {}).get("sessions", [])
        if any(item["id"] != session_id and item.get("title", "").casefold() == title.casefold() for item in siblings):
            raise LearningError(409, "SESSION_NAME_DUPLICATE", "当前科目已有同名会话")
        updated = {**session, "title": title, "updated_at": self._now()}
        self._replace_session(subject["id"], session_id, updated)
        return self._session_view(updated, subject["id"])

    def delete_session(self, session_id: str) -> None:
        subject, session = self._find_session(session_id)
        message_ids = {item["id"] for item in session.get("messages", [])}
        if self.operations.has_active("session", session_id) or any(
            self.operations.has_active("chat-message", message_id)
            for message_id in message_ids
        ):
            raise LearningError(409, "OPERATION_IN_PROGRESS", "会话仍有任务在运行")
        data = subject.get("data", {})
        remaining = [item for item in data.get("sessions", []) if item["id"] != session_id]
        active_id = data.get("active_session_id")
        if active_id == session_id:
            active_id = remaining[-1]["id"] if remaining else None
        self._mutate(subject["id"], lambda current: {**current, "sessions": remaining, "active_session_id": active_id})

    def activate_session(self, session_id: str) -> dict:
        subject, session = self._find_session(session_id)
        self._mutate(subject["id"], lambda data: {**data, "active_session_id": session_id})
        return self._session_view(session, subject["id"], active=True)

    def list_session_sources(self, session_id: str) -> dict:
        subject, session = self._find_session(session_id)
        return {"items": [self._session_source_view(version_id) for version_id in session.get("source_version_ids", [])]}

    def add_session_source(self, session_id: str, version_id: str) -> dict:
        subject, session = self._find_session(session_id)
        self._validate_source_scope(subject["id"], [version_id], "strict")
        if version_id in session.get("source_version_ids", []):
            raise LearningError(409, "SESSION_SOURCE_CONFLICT", "资料版本已在当前会话中")
        self._replace_session(subject["id"], session_id, {**session, "source_version_ids": [*session.get("source_version_ids", []), version_id], "updated_at": self._now()})
        return self._session_source_view(version_id)

    def update_session_source(self, session_id: str, old_version_id: str, new_version_id: str) -> dict:
        subject, session = self._find_session(session_id)
        if old_version_id not in session.get("source_version_ids", []):
            raise LearningError(404, "RESOURCE_NOT_FOUND", "会话资料版本不存在")
        self._validate_source_scope(subject["id"], [new_version_id], "strict")
        ids = [new_version_id if item == old_version_id else item for item in session["source_version_ids"]]
        if len(ids) != len(set(ids)):
            raise LearningError(409, "SESSION_SOURCE_CONFLICT", "目标资料版本已在当前会话中")
        self._replace_session(subject["id"], session_id, {**session, "source_version_ids": ids, "updated_at": self._now()})
        return self._session_source_view(new_version_id)

    def remove_session_source(self, session_id: str, version_id: str) -> None:
        subject, session = self._find_session(session_id)
        if version_id not in session.get("source_version_ids", []):
            raise LearningError(404, "RESOURCE_NOT_FOUND", "会话资料版本不存在")
        self._replace_session(subject["id"], session_id, {**session, "source_version_ids": [item for item in session["source_version_ids"] if item != version_id], "updated_at": self._now()})

    def create_session_message(self, session_id: str, payload: dict) -> dict:
        subject, session = self._find_session(session_id)
        model_id = payload.get("model_id") or self.workspace_service.snapshot().get("current_model_id")
        if not model_id:
            raise LearningError(409, "CHAT_MODEL_NOT_SELECTED", "请先选择模型服务")
        profile = self._model(model_id)
        session_source_ids = list(session.get("source_version_ids", []))
        requested_ids = list(payload.get("source_version_ids") or [])
        if not set(requested_ids) <= set(session_source_ids):
            raise LearningError(409, "SOURCE_VERSION_MISMATCH", "消息资料必须属于当前会话资料范围")
        selected_ids = session_source_ids
        if payload.get("only_use_specified_sources"):
            selected_ids = list(requested_ids or payload.get("focused_source_version_ids") or [])
            if not selected_ids:
                raise LearningError(422, "VALIDATION_FAILED", "仅使用指定资料时必须提供资料版本")
        if not set(selected_ids) <= set(session_source_ids):
            raise LearningError(409, "SOURCE_VERSION_MISMATCH", "消息资料必须属于当前会话资料范围")
        grounding_mode = payload.get("grounding_mode") or ("strict" if selected_ids else "general-knowledge")
        focused_ids = [item for item in payload.get("focused_source_version_ids") or [] if item in selected_ids]
        if payload.get("focused_source_version_ids") and len(focused_ids) != len(payload["focused_source_version_ids"]):
            raise LearningError(409, "SOURCE_VERSION_MISMATCH", "重点资料必须属于当前会话资料范围")
        attachment_ids = list(payload.get("attachment_ids") or [])
        attachment_inputs = self._attachment_inputs(subject["id"], attachment_ids, profile)
        selection = payload.get("selection")
        selection_context = None
        if selection:
            if self.selection_resolver is None:
                raise LearningError(409, "CHAT_SELECTION_INVALID", "选区问答服务尚未就绪")
            resolved = self.selection_resolver(selection, include_context=True)
            if isinstance(resolved, tuple):
                selection, selection_context = resolved
            else:
                selection = resolved
            payload = {**payload, "selection": selection}
        if selection and selection.get("image_asset") and not profile.get("capabilities", {}).get("vision"):
            raise LearningError(409, "IMAGE_INPUT_UNSUPPORTED", "当前模型不支持图片输入，请更换具备视觉能力的模型")
        if selected_ids:
            self._validate_source_scope(subject["id"], selected_ids, grounding_mode)
        elif grounding_mode in {"strict", "supplemental"} and not attachment_inputs and not selection:
            raise LearningError(409, "GROUNDING_SOURCE_REQUIRED", "当前依据模式需要资料、选区或临时附件")
        timestamp = self._now()
        context = {
            "source_version_ids": selected_ids,
            "focused_source_version_ids": focused_ids,
            "only_use_specified_sources": bool(payload.get("only_use_specified_sources")),
            "grounding_mode": grounding_mode,
            "selection": selection,
            "attachment_ids": attachment_ids,
            "citations": [],
        }
        content = payload.get("content") or self._intent_label(payload["intent"])
        user_message = {"id": self._ids("message"), "role": "user", "intent": payload["intent"], "content": [self._markdown_block(content)], "status": "complete", "grounding_mode": context["grounding_mode"], "grounding_result": None, "citations": [], "source_context": context, "selection": selection, "model": None, "error": None, "created_at": timestamp, "updated_at": timestamp, "completed_at": timestamp}
        assistant_id = self._ids("message")
        assistant = {"id": assistant_id, "role": "assistant", "intent": payload["intent"], "content": [], "status": "queued", "grounding_mode": context["grounding_mode"], "grounding_result": None, "citations": [], "source_context": context, "selection": selection, "model": self._model_snapshot(profile), "error": None, "created_at": timestamp, "updated_at": timestamp, "completed_at": None}
        updated_session = {**session, "messages": [*session.get("messages", []), user_message, assistant], "updated_at": timestamp}
        if len(updated_session["messages"]) == 2 and session.get("title") == "新会话":
            updated_session["title"] = content[:60]
        self._replace_session(subject["id"], session_id, updated_session)

        async def worker():
            self._update_session_message(subject["id"], session_id, assistant_id, {"status": "generating", "updated_at": self._now()})
            try:
                query_ids = [*focused_ids, *[item for item in selected_ids if item not in focused_ids]]
                anchors = (
                    self.source_library.retrieve(
                        content,
                        query_ids,
                        priority_version_ids=focused_ids,
                    )
                    if query_ids and grounding_mode != "general-knowledge" else []
                )
                selected_citations = [
                    self.source_library.get_citation(citation_id)
                    for citation_id in (selection or {}).get("citation_ids", [])
                ]
                has_selection_context = bool((selection or {}).get("selected_text") or (selection or {}).get("image_asset"))
                if grounding_mode == "strict" and not anchors and not selected_citations and not has_selection_context and not attachment_inputs:
                    text = "选定资料未覆盖这个问题，我无法仅依据资料回答。"
                    self._update_session_message(subject["id"], session_id, assistant_id, {"status": "complete", "content": [self._markdown_block(text)], "grounding_result": "not-covered", "completed_at": self._now(), "updated_at": self._now()})
                    return {"type": "chat-message", "id": assistant_id}
                citations = self._citations_for_anchors(anchors, selected_citations)
                messages = self._grounded_messages(
                    {"messages": session.get("messages", []), "learning_mode": "chat"},
                    payload,
                    anchors,
                    grounding_mode,
                    profile,
                    selection_context,
                    attachment_inputs,
                )
                response = await self.model_client.chat(profile, messages)
                final_context = {**context, "citations": citations}
                result = (
                    "general-knowledge"
                    if context["grounding_mode"] == "general-knowledge"
                    else "supplemental" if context["grounding_mode"] == "supplemental" else "covered"
                )
                self._update_session_message(subject["id"], session_id, assistant_id, {"status": "complete", "content": [self._markdown_block(response.get("text") or "")], "grounding_result": result, "citations": citations, "source_context": final_context, "completed_at": self._now(), "updated_at": self._now()})
                return {"type": "chat-message", "id": assistant_id}
            except asyncio.CancelledError:
                self._update_session_message(subject["id"], session_id, assistant_id, {"status": "stopped", "completed_at": self._now(), "updated_at": self._now()})
                raise
            except (LearningError, SourceLibraryError, ModelClientError) as exc:
                self._update_session_message(subject["id"], session_id, assistant_id, {"status": "error", "error": {"code": getattr(exc, "code", "MODEL_INVALID_RESPONSE"), "message": str(exc), "retryable": False, "details": {}}, "completed_at": self._now(), "updated_at": self._now()})
                raise OperationFailure(getattr(exc, "code", "MODEL_INVALID_RESPONSE"), str(exc)) from exc

        resource = {"type": "chat-message", "id": assistant_id}
        operation = self.operations.start("chat-generation", worker, subject_id=subject["id"], resource=resource)
        return {"operation": operation, "resource": resource}

    # Crash course artifacts ---------------------------------------------

    def generate_crash_course(self, subject_id: str, payload: dict) -> dict:
        self._subject(subject_id)
        self._validate_source_scope(subject_id, payload["source_version_ids"], payload["grounding_mode"])
        chat = self.get_chat(subject_id)
        model_id = payload.get("model_id") or self.workspace_service.snapshot().get("current_model_id") or chat.get("active_model_id")
        if not model_id:
            raise LearningError(409, "CHAT_MODEL_NOT_SELECTED", "请先选择模型服务")
        profile = self._model(model_id)
        artifact_id = self._ids("artifact")
        resource = {"type": "learning-artifact", "id": artifact_id}

        async def worker():
            try:
                grounding_mode = payload["grounding_mode"]
                anchors = [] if grounding_mode == "general-knowledge" else self.source_library.retrieve(
                    payload["goal"], payload["source_version_ids"], limit=20
                )
                if grounding_mode == "strict" and not anchors:
                    self._record_structure_stage(self._now(), time.perf_counter(), "failed")
                    raise OperationFailure("GROUNDING_SOURCE_REQUIRED", "选定资料未覆盖该学习目标")
                citations = [self.source_library.create_citation(anchor) for anchor in anchors]
                instruction = {
                    "strict": "请严格根据以下资料生成章节速成目录，只返回 JSON；资料未覆盖的内容不要补全。",
                    "supplemental": "请先依据资料生成章节速成目录；资料未覆盖处可以补充通用知识，并明确标注补充内容。",
                    "general-knowledge": "请使用通用知识生成章节速成目录，并明确说明未依据用户资料。",
                }[grounding_mode]
                prompt = (
                    f"{instruction}\n"
                    '{"title":"...","knowledge_points":[{"title":"...","explanation":"...",'
                    '"key_points":["..."],"self_test":{"prompt":"...","answer":"..."}}]}。\n\n'
                    f"学习目标：{payload['goal']}\n\n资料片段：\n{self._anchors_text(anchors) or '无'}"
                )
                response = await self.model_client.chat(profile, [{
                    "role": "user",
                    "content": self._grounded_content(prompt, anchors, profile),
                }])
                validation_started_at = self._now()
                validation_started = time.perf_counter()
                try:
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
                    artifact = LearningArtifact.model_validate(artifact).model_dump()
                except (ValidationError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                    self._record_structure_stage(validation_started_at, validation_started, "failed")
                    raise
                self._record_structure_stage(validation_started_at, validation_started, "succeeded")
                self._append_artifact(subject_id, artifact)
                return resource
            except (LearningError, ModelClientError, SourceLibraryError, ValueError, KeyError, json.JSONDecodeError) as exc:
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

    def _find_session(self, session_id: str) -> tuple[dict, dict]:
        snapshot = self.workspace_service.snapshot()
        for subject in snapshot.get("subjects", []):
            session = next((item for item in subject.get("data", {}).get("sessions", []) if item.get("id") == session_id), None)
            if session:
                return subject, session
        raise LearningError(404, "SESSION_NOT_FOUND", "学习会话不存在")

    def _session_view(self, session: dict, subject_id: str, active: bool | None = None) -> dict:
        snapshot = self.workspace_service.snapshot()
        subject = self._subject(subject_id, snapshot)
        is_active = snapshot.get("active_subject_id") == subject_id and subject.get("data", {}).get("active_session_id") == session["id"]
        if active is not None:
            is_active = active
        return {**session, "active": is_active, "messages": session.get("messages", [])}

    def _replace_session(self, subject_id: str, session_id: str, replacement: dict) -> None:
        self._mutate(subject_id, lambda data: {
            **data,
            "sessions": [replacement if item.get("id") == session_id else item for item in data.get("sessions", [])],
        })

    def _update_session_message(self, subject_id: str, session_id: str, message_id: str, changes: dict) -> None:
        _, session = self._find_session(session_id)
        updated = {**session, "messages": [{**message, **changes} if message.get("id") == message_id else message for message in session.get("messages", [])], "updated_at": self._now()}
        self._replace_session(subject_id, session_id, updated)

    def _session_source_view(self, version_id: str) -> dict:
        try:
            version = self.source_library.get_version(version_id)
            source = self.source_library.get_source(version["source_id"])
        except SourceLibraryError as exc:
            raise LearningError(exc.status_code, exc.code, str(exc)) from exc
        return {"source_version_id": version_id, "source_id": version["source_id"], "source_name": source["display_name"], "version_number": version["number"], "status": version["status"], "added_at": version.get("created_at", self._now())}

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
            "active_model_id": self.workspace_service.snapshot().get("current_model_id"),
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
                if version["status"] != "ready":
                    raise LearningError(409, "SOURCE_UNAVAILABLE", "选定资料尚不可用于检索")
                source = self.source_library.get_source(version["source_id"])
            except SourceLibraryError as exc:
                raise LearningError(exc.status_code, exc.code, str(exc)) from exc
            if source["subject_id"] != subject_id:
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
                    "source_context": {**(message.get("source_context") or {}), "citations": citations},
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

    def _grounded_messages(
        self,
        chat: dict,
        payload: dict,
        anchors: list[dict],
        grounding_mode: str,
        profile: dict,
        selection_context: str | None = None,
        attachments: list[dict] | None = None,
    ) -> list[dict]:
        intent = payload["intent"]
        instruction = self._grounding_instruction(grounding_mode)
        if chat["learning_mode"] == "socratic":
            instruction += self._socratic_instruction(intent, chat.get("socratic_state"))
        context = self._anchors_text(anchors)
        question = payload.get("content") or self._intent_label(intent)
        selection = payload.get("selection") or {}
        selected_text = selection.get("selected_text") or ""
        citation_context = []
        for citation_id in selection.get("citation_ids", []):
            citation = self.source_library.get_citation(citation_id)
            citation_context.append(f"[{citation['location']['label']}] {citation.get('excerpt') or ''}")
        text = (
            f"{instruction}\n\n资料片段：\n{context or '无'}"
            f"\n\n选区：\n{selected_text or '无'}"
            f"\n\n所在题目或文档上下文：\n{selection_context or '无'}"
            f"\n\n选区来源：\n{'\n'.join(citation_context) or '无'}"
            f"\n\n用户输入：{question}"
        )
        content = self._grounded_content(text, anchors, profile, selection, attachments)
        return [*self._conversation_messages(chat), {"role": "user", "content": content}]

    def _grounded_content(
        self,
        text: str,
        anchors: list[dict],
        profile: dict,
        selection: dict | None = None,
        attachments: list[dict] | None = None,
    ) -> str | list[dict]:
        attachment_parts = []
        attachment_text = []
        for attachment in attachments or []:
            raw = attachment["content"]
            mime_type = attachment["mime_type"]
            if mime_type.startswith("text/"):
                attachment_text.append(
                    f"[{attachment['file_name']}]\n{raw.decode('utf-8', errors='replace')}"
                )
                continue
            encoded = base64.b64encode(raw).decode("ascii")
            data_url = f"data:{mime_type};base64,{encoded}"
            if mime_type.startswith("image/"):
                attachment_parts.append({"type": "image_url", "image_url": {"url": data_url}})
            elif mime_type == "application/pdf":
                attachment_parts.append({
                    "type": "file",
                    "file": {"filename": attachment["file_name"], "file_data": data_url},
                })
        if attachment_text:
            text += f"\n\n临时附件：\n{'\n\n'.join(attachment_text)}"

        content: str | list[dict] = text
        image_blocks = [
            block
            for anchor in anchors
            for block in anchor.get("content", [])
            if block.get("type") == "image"
        ]
        if selection and selection.get("image_asset"):
            image_blocks.append({"asset": selection["image_asset"]})
        has_image_input = bool(image_blocks) or any(
            part["type"] == "image_url"
            for part in attachment_parts
        )
        if has_image_input and not profile.get("capabilities", {}).get("vision"):
            raise LearningError(409, "IMAGE_INPUT_UNSUPPORTED", "当前模型不支持图片输入")
        if image_blocks or attachment_parts:
            parts = [{"type": "text", "text": text}]
            parts.extend(attachment_parts)
            for block in image_blocks:
                asset = block["asset"]
                raw, mime_type = self.source_library.get_asset(asset["source_version_id"], asset["asset_id"])
                encoded = base64.b64encode(raw).decode("ascii")
                parts.append({"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}})
            content = parts
        return content

    def _attachment_inputs(self, subject_id: str, attachment_ids: list[str], profile: dict) -> list[dict]:
        if attachment_ids and self.attachments is None:
            raise LearningError(404, "ATTACHMENT_NOT_FOUND", "临时附件服务不可用")
        result = []
        for attachment_id in attachment_ids:
            attachment = self.attachments.require(subject_id, attachment_id)
            if attachment.get("vision_required") and not profile.get("capabilities", {}).get("vision"):
                raise LearningError(409, "IMAGE_INPUT_UNSUPPORTED", "当前模型不支持图片附件，请更换具备视觉能力的模型")
            raw, mime_type = self.attachments.file(attachment_id)
            result.append({**attachment, "content": raw, "mime_type": mime_type})
        return result

    @staticmethod
    def _grounding_instruction(grounding_mode: str) -> str:
        if grounding_mode == "strict":
            return "只能依据提供的资料片段和临时附件回答，不要补充资料之外的知识。"
        if grounding_mode == "supplemental":
            return "资料优先；可以补充通用知识，但必须把资料外内容明确标为“补充通用知识”。"
        return "请回答用户问题。"

    def _conversation_messages(self, chat: dict) -> list[dict]:
        messages = chat.get("messages", [])
        if len(messages) >= 2 and messages[-1].get("role") == "assistant" and messages[-1].get("status") in {"queued", "generating"}:
            messages = messages[:-2]
        result = []
        for message in messages:
            if message.get("role") not in {"user", "assistant", "system"}:
                continue
            if message.get("status") not in {"complete", "stopped"}:
                continue
            text = self._content_text(message.get("content", []))
            if text:
                result.append({"role": message["role"], "content": text})
        return result

    @staticmethod
    def _content_text(blocks: list[dict]) -> str:
        parts = []
        for block in blocks or []:
            kind = block.get("type")
            if kind == "markdown":
                parts.append(block.get("text", ""))
            elif kind == "latex":
                parts.append(block.get("latex", ""))
            elif kind == "table":
                parts.append(" | ".join(block.get("columns", [])))
                parts.extend(" | ".join(row) for row in block.get("rows", []))
            elif kind == "image":
                parts.append(block.get("alt") or block.get("caption") or "[图片]")
        return "\n".join(item for item in parts if item)

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

    def _citations_for_anchors(
        self,
        anchors: list[dict],
        existing: list[dict] | None = None,
    ) -> list[dict]:
        citations = list(existing or [])
        for anchor in anchors:
            citations.append(self.source_library.create_citation(anchor))
            for upstream in anchor.get("_upstream_citations", []):
                try:
                    citations.append(self.source_library.get_citation(upstream["id"]))
                except SourceLibraryError:
                    citations.append({**upstream, "available": False})
        return list({citation["id"]: citation for citation in citations}.values())

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
    def _validate_socratic_intent(state: dict | None, intent: str) -> None:
        stage = (state or {}).get("stage", "awaiting-attempt")
        allowed = {
            "awaiting-attempt": {"start", "attempt", "request-hint", "request-explanation"},
            "hinting": {"attempt", "request-hint", "request-explanation"},
            "correcting": {"restate", "request-explanation", "request-hint"},
            "awaiting-restate": {"restate", "request-self-test", "request-explanation"},
            "self-testing": {"self-test-answer"},
            "completed": {"start"},
        }
        if intent not in allowed.get(stage, set()):
            raise LearningError(409, "RESOURCE_CONFLICT", "当前苏格拉底学习阶段不支持该动作")

    @staticmethod
    def _next_socratic_state(state: dict | None, intent: str) -> dict:
        current = state or {"stage": "awaiting-attempt", "hint_level": 0, "answer_revealed": False}
        if intent == "start":
            return {"stage": "awaiting-attempt", "hint_level": 0, "answer_revealed": False}
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
        elif code in {
            "SUBJECT_NAME_REQUIRED",
            "SUBJECT_NAME_TOO_LONG",
            "MODEL_BASE_URL_REQUIRED",
            "MODEL_BASE_URL_INVALID",
            "MODEL_PROVIDER_REQUIRED",
            "MODEL_PROVIDER_TOO_LONG",
            "MODEL_NAME_REQUIRED",
            "MODEL_NAME_TOO_LONG",
            "MODEL_API_KEY_INVALID",
            "MODEL_VALIDATION_INVALID",
        }:
            status = 422
            code = "VALIDATION_FAILED"
        else:
            status = 409
        raise LearningError(status, code, error.get("message", "操作失败"))
