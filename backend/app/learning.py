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
    DEFAULT_API_FORMAT,
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
from .subject_transfer import (
    CONFLICT_MESSAGE,
    TransferError,
    build_export_zip,
    collect_source_entries,
    content_disposition,
    export_zip_filename,
    imported_subject_name,
    parse_export_zip,
    write_source_entries,
)

SESSION_AGENT_TOOL_ROUNDS = 4


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
        self.exams = None
        self.documents = None

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

    def export_subject(self, subject_id: str) -> dict:
        snapshot = self.workspace_service.snapshot()
        subject = self._subject(subject_id, snapshot)
        node = {
            "id": subject["id"],
            "name": subject["name"],
            "created_at": subject["created_at"],
            "updated_at": subject["updated_at"],
            "data": subject.get("data") or {},
        }
        version_ids = {
            item.get("id")
            for item in node["data"].get("source_versions", [])
            if isinstance(item, dict) and item.get("id")
        }
        citations = [
            item
            for item in self.source_library.list_citations()
            if item.get("source_version_id") in version_ids
        ]
        source_entries = collect_source_entries(self.source_library, node["data"].get("source_versions", []))
        content = build_export_zip(
            subject=node,
            citations=citations,
            source_entries=source_entries,
            exported_at=self._now(),
        )
        file_name = export_zip_filename(subject["name"])
        return {
            "content": content,
            "file_name": file_name,
            "content_type": "application/zip",
            "content_disposition": content_disposition(file_name),
        }

    def import_subject(self, zip_bytes: bytes) -> dict:
        try:
            parsed = parse_export_zip(zip_bytes)
        except TransferError as exc:
            raise LearningError(exc.status_code, exc.code, str(exc)) from exc
        subject = parsed["subject"]
        snapshot = self.workspace_service.snapshot()
        existing_subject_ids = {item.get("id") for item in snapshot.get("subjects", [])}
        existing_version_ids = {
            version.get("id")
            for item in snapshot.get("subjects", [])
            for version in item.get("data", {}).get("source_versions", [])
            if isinstance(version, dict) and version.get("id")
        }
        incoming_version_ids = {
            version.get("id")
            for version in subject.get("data", {}).get("source_versions", [])
            if isinstance(version, dict) and version.get("id")
        }
        if subject["id"] in existing_subject_ids or incoming_version_ids & existing_version_ids:
            raise LearningError(409, "RESOURCE_CONFLICT", CONFLICT_MESSAGE)
        existing_names = {item.get("name") for item in snapshot.get("subjects", [])}
        imported = {
            **subject,
            "name": imported_subject_name(subject["name"], existing_names),
            "data": subject.get("data") or {},
        }
        try:
            write_source_entries(self.source_library, parsed["source_entries"])
        except TransferError as exc:
            raise LearningError(exc.status_code, exc.code, str(exc)) from exc
        self.source_library.merge_citations(parsed["citations"])

        def update(workspace):
            return {
                **workspace,
                "subjects": [*workspace.get("subjects", []), imported],
                "active_subject_id": imported["id"],
            }

        self.workspace_service.update_workspace(update)
        if self.workspace_service.last_storage_error:
            raise LearningError(500, "STORAGE_WRITE_FAILED", "无法保存本地数据", retryable=True)
        return self.get_subject(imported["id"])

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
            "api_format": patch.get("api_format", existing.get("api_format", DEFAULT_API_FORMAT)),
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
        api_format = payload["api_format"]
        url = self._discovery_url(api_format, payload["base_url"])
        headers = {
            "Accept": "application/json",
            "HTTP-Referer": "http://127.0.0.1:4173",
            "X-Title": "Stilldesk",
        }
        if payload.get("api_key"):
            headers["Authorization"] = f"Bearer {payload['api_key']}"
            headers["X-Api-Key"] = payload["api_key"]
        try:
            response = httpx.get(url, headers=headers, timeout=15.0, follow_redirects=True)
            response.raise_for_status()
            models = self._parse_discovered_models(api_format, response.json())
            return {"api_format": api_format, "models": models, "manual_model_allowed": True, "error": None}
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            provider_message = self._discovery_error_text(exc.response)
            if status in {401, 403}:
                message = provider_message or "模型列表请求被拒绝，请检查 API Key"
            elif status == 404:
                message = provider_message or "发现地址不存在，请检查 Base URL 和 API 格式"
            else:
                message = provider_message or "无法获取模型列表，可手动填写模型名"
            return {
                "api_format": api_format,
                "models": [],
                "manual_model_allowed": True,
                "error": {
                    "code": "MODEL_DISCOVERY_FAILED",
                    "message": message,
                    "retryable": True,
                    "details": {"status": status},
                },
            }
        except (httpx.HTTPError, ValueError, TypeError):
            return {
                "api_format": api_format,
                "models": [],
                "manual_model_allowed": True,
                "error": {"code": "MODEL_DISCOVERY_FAILED", "message": "无法连接模型服务，请检查 Base URL 和网络", "retryable": True, "details": {}},
            }

    @staticmethod
    def _discovery_error_text(response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict) and isinstance(error.get("message"), str) and error["message"].strip():
                return error["message"].strip()[:300]
            if isinstance(payload.get("message"), str) and payload["message"].strip():
                return payload["message"].strip()[:300]
        text = (getattr(response, "text", "") or "").strip().replace("\n", " ")
        return text[:300] if text else ""

    @staticmethod
    def _discovery_url(api_format: str, base_url: str) -> str:
        base = (base_url or "").rstrip("/")
        for suffix in ("/chat/completions", "/completions", "/responses", "/api/chat", "/api/tags"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        if api_format == "ollama":
            if base.endswith("/api/tags"):
                return base
            if base.endswith("/api"):
                return f"{base}/tags"
            return f"{base}/api/tags"
        return base if base.endswith("/models") else f"{base}/models"

    @staticmethod
    def _parse_discovered_models(api_format: str, raw) -> list[dict]:
        if isinstance(raw, list):
            entries = raw
        elif isinstance(raw, dict):
            if api_format == "ollama" and isinstance(raw.get("models"), list):
                entries = raw["models"]
            elif isinstance(raw.get("data"), list):
                entries = raw["data"]
            elif isinstance(raw.get("models"), list):
                entries = raw["models"]
            else:
                entries = []
        else:
            entries = []
        models = []
        for item in entries:
            if isinstance(item, str):
                name = item
            elif isinstance(item, dict):
                name = item.get("name") or item.get("id") or item.get("model")
            else:
                continue
            if name:
                models.append({"name": str(name), "capabilities": {"text": True, "vision": False}})
        return models

    # Chat ----------------------------------------------------------------

    def get_chat(self, subject_id: str) -> dict:
        subject = self._subject(subject_id)
        chat = subject.get("data", {}).get("learning_chat")
        if chat:
            style = self._stored_chat_style(chat)
            return {
                **chat,
                "learning_mode": self._legacy_learning_mode(style),
                "chat_style": style,
                "socratic_state": None,
            }
        chat = self._new_chat(subject)
        self._set_chat(subject_id, chat)
        return chat

    def configure_chat(self, subject_id: str, patch: dict) -> dict:
        chat = self.get_chat(subject_id)
        source_ids = patch.get("source_version_ids", chat["source_version_ids"])
        grounding_mode = patch.get("grounding_mode", chat["grounding_mode"])
        self._validate_source_scope(subject_id, source_ids, grounding_mode)
        style = self._requested_chat_style(patch, self._stored_chat_style(chat))
        updated = {
            **chat,
            **patch,
            "learning_mode": self._legacy_learning_mode(style),
            "chat_style": style,
            "socratic_state": None,
            "source_version_ids": source_ids,
            "updated_at": self._now(),
        }
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
        chat_style = self._requested_chat_style(payload, self._stored_chat_style(chat))

        model_id = payload.get("model_id") or self.workspace_service.snapshot().get("current_model_id") or chat.get("active_model_id")
        if not model_id:
            raise LearningError(409, "CHAT_MODEL_NOT_SELECTED", "请先选择模型服务")
        profile = self._model(model_id)
        source_ids = list(payload.get("source_version_ids", chat.get("source_version_ids") or []))
        if not source_ids:
            source_ids = self._ready_source_version_ids(subject_id)
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
        workspace = self._workspace_context(payload.get("workspace_context"))
        selection, selection_context = self._resolve_selection(
            payload.get("selection"),
            profile,
            redact_answers=self._selection_should_hide_answers(workspace),
        )
        if selection:
            payload = {**payload, "selection": selection}
        if not profile.get("capabilities", {}).get("vision"):
            image_only = any(
                self.source_library.get_source(self.source_library.get_version(version_id)["source_id"])["media_kind"] == "image"
                for version_id in source_ids
            )
            if image_only:
                raise LearningError(409, "IMAGE_INPUT_UNSUPPORTED", "选定资料是图片，请更换具备视觉能力的模型")

        timestamp = self._now()
        content = payload.get("content") or self._intent_label(intent)
        user_id = self._ids("message")
        if attachment_ids:
            self.attachments.claim(subject_id, attachment_ids, user_id)
        source_context = self._source_context(
            source_ids,
            focused_ids,
            payload,
            grounding_mode,
            selection,
            attachment_ids,
            workspace_context=workspace,
        )
        user_message, assistant = self._chat_turn_messages(
            intent=intent,
            chat_style=chat_style,
            content=content,
            grounding_mode=grounding_mode,
            source_context=source_context,
            selection=selection,
            profile=profile,
            timestamp=timestamp,
            user_id=user_id,
        )
        assistant_id = assistant["id"]
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
                    {**chat, "chat_style": chat_style},
                    {**payload, "chat_style": chat_style},
                    anchors,
                    grounding_mode,
                    profile,
                    selection_context,
                    attachment_inputs,
                )
                response = await self.model_client.chat(profile, messages)
                text = response.get("text") or ""
                result = self._grounding_result(grounding_mode)
                self._complete_message(
                    subject_id,
                    assistant_id,
                    text,
                    result,
                    citations,
                    intent,
                )
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
        chat_style = self._requested_chat_style(payload, "default")
        session = {
            "id": self._ids("session"),
            "subject_id": subject_id,
            "title": payload.get("title") or "新会话",
            "chat_style": chat_style,
            "learning_mode": self._legacy_learning_mode(chat_style),
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
        title = session["title"]
        if "title" in patch:
            title = (patch.get("title") or "").strip()
            if not title:
                raise LearningError(422, "VALIDATION_FAILED", "会话标题不能为空")
            siblings = subject.get("data", {}).get("sessions", [])
            if any(item["id"] != session_id and item.get("title", "").casefold() == title.casefold() for item in siblings):
                raise LearningError(409, "SESSION_NAME_DUPLICATE", "当前科目已有同名会话")
        chat_style = self._requested_chat_style(patch, self._stored_chat_style(session))
        updated = {
            **session,
            "title": title,
            "chat_style": chat_style,
            "learning_mode": self._legacy_learning_mode(chat_style),
            "updated_at": self._now(),
        }
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

    def append_session_note(self, session_id: str, payload: dict) -> dict:
        subject, session = self._find_session(session_id)
        role = payload.get("role")
        raw_content = payload.get("content")
        content = raw_content.strip() if isinstance(raw_content, str) else ""
        if role not in {"user", "system"}:
            raise LearningError(422, "VALIDATION_FAILED", "笔记角色必须是 user 或 system")
        if not content:
            raise LearningError(422, "VALIDATION_FAILED", "笔记内容不能为空")
        timestamp = self._now()
        message = {
            "id": self._ids("message"),
            "role": role,
            "intent": "ask",
            "chat_style": self._stored_chat_style(session),
            "content": [self._markdown_block(content)],
            "status": "complete",
            "grounding_mode": None,
            "grounding_result": None,
            "citations": [],
            "source_context": {
                "source_version_ids": [],
                "focused_source_version_ids": [],
                "only_use_specified_sources": False,
                "grounding_mode": "general-knowledge",
                "selection": None,
                "attachment_ids": [],
                "citations": [],
            },
            "selection": None,
            "model": None,
            "error": None,
            "created_at": timestamp,
            "updated_at": timestamp,
            "completed_at": timestamp,
        }
        self._replace_session(
            subject["id"],
            session_id,
            {**session, "messages": [*session.get("messages", []), message], "updated_at": timestamp},
        )
        return message

    def create_session_message(self, session_id: str, payload: dict) -> dict:
        subject, session = self._find_session(session_id)
        chat_style = self._requested_chat_style(payload, self._stored_chat_style(session))
        model_id = payload.get("model_id") or self.workspace_service.snapshot().get("current_model_id")
        if not model_id:
            raise LearningError(409, "CHAT_MODEL_NOT_SELECTED", "请先选择模型服务")
        profile = self._model(model_id)
        session_pins = list(session.get("source_version_ids") or [])
        scope_ids = session_pins or self._ready_source_version_ids(subject["id"])
        requested_ids = list(payload.get("source_version_ids") or [])
        if requested_ids and not set(requested_ids) <= set(scope_ids):
            raise LearningError(409, "SOURCE_VERSION_MISMATCH", "消息资料必须属于当前会话资料范围")
        selected_ids = list(scope_ids)
        if payload.get("only_use_specified_sources"):
            selected_ids = list(requested_ids or payload.get("focused_source_version_ids") or [])
            if not selected_ids:
                raise LearningError(422, "VALIDATION_FAILED", "仅使用指定资料时必须提供资料版本")
            if not set(selected_ids) <= set(scope_ids):
                raise LearningError(409, "SOURCE_VERSION_MISMATCH", "消息资料必须属于当前会话资料范围")
        grounding_mode = payload.get("grounding_mode") or ("supplemental" if selected_ids else "general-knowledge")
        focused_ids = [item for item in payload.get("focused_source_version_ids") or [] if item in selected_ids]
        if payload.get("focused_source_version_ids") and len(focused_ids) != len(payload["focused_source_version_ids"]):
            raise LearningError(409, "SOURCE_VERSION_MISMATCH", "重点资料必须属于当前会话资料范围")
        attachment_ids = list(payload.get("attachment_ids") or [])
        attachment_inputs = self._attachment_inputs(subject["id"], attachment_ids, profile)
        workspace = self._workspace_context(payload.get("workspace_context"))
        selection, selection_context = self._resolve_selection(
            payload.get("selection"),
            profile,
            redact_answers=self._selection_should_hide_answers(workspace),
        )
        if selection:
            payload = {**payload, "selection": selection}
        if selected_ids:
            self._validate_source_scope(subject["id"], selected_ids, grounding_mode)
        elif grounding_mode in {"strict", "supplemental"} and not attachment_inputs and not selection:
            raise LearningError(409, "GROUNDING_SOURCE_REQUIRED", "当前依据模式需要资料、选区或临时附件")
        timestamp = self._now()
        context = self._source_context(
            selected_ids,
            focused_ids,
            payload,
            grounding_mode,
            selection,
            attachment_ids,
            workspace_context=workspace,
        )
        content = payload.get("content") or self._intent_label(payload["intent"])
        user_id = self._ids("message")
        if attachment_ids:
            self.attachments.claim(subject["id"], attachment_ids, user_id)
        user_message, assistant = self._chat_turn_messages(
            intent=payload["intent"],
            chat_style=chat_style,
            content=content,
            grounding_mode=context["grounding_mode"],
            source_context=context,
            selection=selection,
            profile=profile,
            timestamp=timestamp,
            user_id=user_id,
            extra_assistant={"tool_events": []},
        )
        assistant_id = assistant["id"]
        updated_session = {**session, "messages": [*session.get("messages", []), user_message, assistant], "updated_at": timestamp}
        if len(updated_session["messages"]) == 2 and session.get("title") == "新会话":
            updated_session["title"] = content[:60]
        self._replace_session(subject["id"], session_id, updated_session)

        async def worker():
            return await self._generate_session_assistant(
                subject_id=subject["id"],
                session_id=session_id,
                assistant_id=assistant_id,
                profile=profile,
                payload={**payload, "chat_style": chat_style},
                context=context,
                chat_style=chat_style,
                selection_context=selection_context,
                attachment_inputs=attachment_inputs,
            )

        resource = {"type": "chat-message", "id": assistant_id}
        operation = self.operations.start("chat-generation", worker, subject_id=subject["id"], resource=resource)
        return {"operation": operation, "resource": resource}

    def retry_session_message(self, session_id: str, message_id: str, payload: dict) -> dict:
        subject, session = self._find_session(session_id)
        if self.operations.active_for_subject(subject["id"], "chat-generation"):
            raise LearningError(409, "OPERATION_IN_PROGRESS", "已有回答正在生成")
        messages = session.get("messages", [])
        assistant_index = next((index for index, item in enumerate(messages) if item.get("id") == message_id), None)
        if assistant_index is None:
            raise LearningError(404, "RESOURCE_NOT_FOUND", "消息不存在")
        assistant = messages[assistant_index]
        if assistant.get("role") != "assistant" or assistant.get("status") not in {"error", "stopped"}:
            raise LearningError(409, "RESOURCE_CONFLICT", "只能重试失败或已停止的回答")
        user_message = next(
            (item for item in reversed(messages[:assistant_index]) if item.get("role") == "user"),
            None,
        )
        if not user_message:
            raise LearningError(422, "VALIDATION_FAILED", "找不到对应的用户消息")
        model_id = (
            payload.get("model_id")
            or self.workspace_service.snapshot().get("current_model_id")
            or (assistant.get("model") or {}).get("id")
        )
        if not model_id:
            raise LearningError(409, "CHAT_MODEL_NOT_SELECTED", "请先选择模型服务")
        profile = self._model(model_id)
        context = dict(assistant.get("source_context") or user_message.get("source_context") or {})
        chat_style = assistant.get("chat_style") or user_message.get("chat_style") or self._stored_chat_style(session)
        selection = user_message.get("selection")
        selection_context = None
        if selection and self.selection_resolver is not None:
            selection, selection_context = self._resolve_selection(
                selection,
                profile,
                redact_answers=self._selection_should_hide_answers((context or {}).get("workspace_context")),
            )
        attachment_ids = list(context.get("attachment_ids") or [])
        attachment_inputs = self._attachment_inputs(subject["id"], attachment_ids, profile) if attachment_ids else []
        content = self._content_text(user_message.get("content", []))
        retry_payload = {
            "intent": user_message.get("intent", "ask"),
            "content": content,
            "chat_style": chat_style,
            "grounding_mode": user_message.get("grounding_mode") or context.get("grounding_mode"),
            "selection": selection,
        }
        timestamp = self._now()
        self._update_session_message(
            subject["id"],
            session_id,
            message_id,
            {
                "status": "queued",
                "content": [],
                "error": None,
                "grounding_result": None,
                "citations": [],
                "tool_events": [],
                "completed_at": None,
                "updated_at": timestamp,
                "model": self._model_snapshot(profile),
            },
        )

        async def worker():
            return await self._generate_session_assistant(
                subject_id=subject["id"],
                session_id=session_id,
                assistant_id=message_id,
                profile=profile,
                payload=retry_payload,
                context=context,
                chat_style=chat_style,
                selection_context=selection_context,
                attachment_inputs=attachment_inputs,
            )

        resource = {"type": "chat-message", "id": message_id}
        operation = self.operations.start("chat-generation", worker, subject_id=subject["id"], resource=resource)
        return {"operation": operation, "resource": resource}

    async def _generate_session_assistant(
        self,
        *,
        subject_id: str,
        session_id: str,
        assistant_id: str,
        profile: dict,
        payload: dict,
        context: dict,
        chat_style: str,
        selection_context=None,
        attachment_inputs=None,
    ) -> dict:
        _, session = self._find_session(session_id)
        content = payload.get("content") or self._intent_label(payload.get("intent", "ask"))
        selected_ids = list(context.get("source_version_ids") or [])
        focused_ids = list(context.get("focused_source_version_ids") or [])
        grounding_mode = context.get("grounding_mode") or "general-knowledge"
        selection = payload.get("selection") or context.get("selection")
        attachment_inputs = attachment_inputs or []

        self._update_session_message(subject_id, session_id, assistant_id, {"status": "generating", "updated_at": self._now()})
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
                self._update_session_message(
                    subject_id,
                    session_id,
                    assistant_id,
                    {
                        "status": "complete",
                        "content": [self._markdown_block(text)],
                        "grounding_result": "not-covered",
                        "completed_at": self._now(),
                        "updated_at": self._now(),
                    },
                )
                await self._maybe_name_new_session(session_id, profile, content, text)
                return {"type": "chat-message", "id": assistant_id}
            citations = self._citations_for_anchors(anchors, selected_citations)
            tools = self._session_assistant_tools(grounding_mode, selected_ids)
            messages = self._grounded_messages(
                {"messages": session.get("messages", []), "chat_style": chat_style},
                {**payload, "chat_style": chat_style},
                anchors,
                grounding_mode,
                profile,
                selection_context,
                attachment_inputs,
                extra_instruction=self._tool_use_instruction(tools),
            )
            assistant_text, tool_anchors = await self._run_session_assistant_loop(
                subject_id=subject_id,
                session_id=session_id,
                assistant_id=assistant_id,
                profile=profile,
                messages=messages,
                tools=tools,
                selected_ids=selected_ids,
                focused_ids=focused_ids,
                grounding_mode=grounding_mode,
                workspace_context=context.get("workspace_context"),
                model_id=profile["id"],
            )
            if tool_anchors:
                citations = self._citations_for_anchors(tool_anchors, citations)
            final_context = {**context, "citations": citations}
            result = self._grounding_result(context["grounding_mode"])
            _, session = self._find_session(session_id)
            current = next((item for item in session.get("messages", []) if item.get("id") == assistant_id), {})
            self._update_session_message(
                subject_id,
                session_id,
                assistant_id,
                {
                    "status": "complete",
                    "content": [self._markdown_block(assistant_text)],
                    "grounding_result": result,
                    "citations": citations,
                    "source_context": final_context,
                    "tool_events": list(current.get("tool_events") or []),
                    "completed_at": self._now(),
                    "updated_at": self._now(),
                },
            )
            await self._maybe_name_new_session(session_id, profile, content, assistant_text)
            return {"type": "chat-message", "id": assistant_id}
        except asyncio.CancelledError:
            self._update_session_message(
                subject_id,
                session_id,
                assistant_id,
                {"status": "stopped", "completed_at": self._now(), "updated_at": self._now()},
            )
            raise
        except (LearningError, SourceLibraryError, ModelClientError) as exc:
            self._update_session_message(
                subject_id,
                session_id,
                assistant_id,
                {
                    "status": "error",
                    "error": {
                        "code": getattr(exc, "code", "MODEL_INVALID_RESPONSE"),
                        "message": str(exc),
                        "retryable": False,
                        "details": {},
                    },
                    "completed_at": self._now(),
                    "updated_at": self._now(),
                },
            )
            raise OperationFailure(getattr(exc, "code", "MODEL_INVALID_RESPONSE"), str(exc)) from exc

    async def _maybe_name_new_session(self, session_id: str, profile: dict, user_content: str, assistant_text: str) -> None:
        fallback = (user_content or "")[:60]
        try:
            _, session = self._find_session(session_id)
            if len(session.get("messages", [])) != 2:
                return
            if session.get("title") != fallback:
                return
            response = await self.model_client.chat(
                profile,
                [{
                    "role": "user",
                    "content": (
                        "为这段学习对话起一个不超过12个字的中文标题，只输出标题本身，不要引号：\n"
                        f"用户：{(user_content or '')[:200]}\n"
                        f"AI：{(assistant_text or '')[:200]}"
                    ),
                }],
                max_tokens=24,
            )
            title = self._clean_session_title(response.get("text") or "")
            if not title:
                return
            subject, session = self._find_session(session_id)
            if session.get("title") != fallback:
                return
            self._replace_session(
                subject["id"],
                session_id,
                {**session, "title": title, "updated_at": self._now()},
            )
        except Exception:
            return

    @staticmethod
    def _clean_session_title(text: str) -> str:
        title = (text or "").replace("\r", "").replace("\n", "").strip()
        for mark in ('"', "'", "“", "”", "‘", "’", "「", "」"):
            title = title.replace(mark, "")
        return title.strip()[:24]

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
        style = self._stored_chat_style(session)
        return {
            **session,
            "active": is_active,
            "chat_style": style,
            "learning_mode": self._legacy_learning_mode(style),
            "messages": session.get("messages", []),
        }

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
            "api_format": model.get("api_format", DEFAULT_API_FORMAT),
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

    def _ready_source_version_ids(self, subject_id: str) -> list[str]:
        subject = self._subject(subject_id)
        return [
            item["current_version"]["id"]
            for item in subject.get("data", {}).get("sources", [])
            if item.get("status") == "ready" and (item.get("current_version") or {}).get("id")
        ]

    def _new_chat(self, subject: dict) -> dict:
        timestamp = self._now()
        source_ids = self._ready_source_version_ids(subject["id"])
        return {
            "id": self._ids("chat"),
            "subject_id": subject["id"],
            "learning_mode": "chat",
            "chat_style": "default",
            "goal": None,
            "grounding_mode": "supplemental" if source_ids else "general-knowledge",
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

    def _selection_should_hide_answers(self, workspace_context) -> bool:
        attempt_id = (workspace_context or {}).get("attempt_id") if isinstance(workspace_context, dict) else None
        if not attempt_id or self.exams is None:
            return False
        try:
            _subject, attempt = self._find_owned("attempts", attempt_id)
        except LearningError:
            return False
        return attempt.get("mode") == "exam" and attempt.get("completion_status") != "completed"

    def _resolve_selection(self, selection, profile: dict, *, redact_answers: bool = False) -> tuple[dict | None, dict | None]:
        if not selection:
            return None, None
        if self.selection_resolver is None:
            raise LearningError(409, "CHAT_SELECTION_INVALID", "选区问答服务尚未就绪")
        resolved = self.selection_resolver(selection, include_context=True, redact_answers=redact_answers)
        if isinstance(resolved, tuple):
            selection, selection_context = resolved
        else:
            selection, selection_context = resolved, None
        if selection and selection.get("image_asset") and not profile.get("capabilities", {}).get("vision"):
            raise LearningError(409, "IMAGE_INPUT_UNSUPPORTED", "当前模型不支持图片输入，请更换具备视觉能力的模型")
        return selection, selection_context

    def _source_context(
        self,
        source_ids: list[str],
        focused_ids: list[str],
        payload: dict,
        grounding_mode: str,
        selection,
        attachment_ids: list[str],
        *,
        workspace_context=None,
    ) -> dict:
        context = {
            "source_version_ids": source_ids,
            "focused_source_version_ids": focused_ids,
            "only_use_specified_sources": bool(payload.get("only_use_specified_sources")),
            "grounding_mode": grounding_mode,
            "selection": selection,
            "attachment_ids": attachment_ids,
            "citations": [],
        }
        if workspace_context is not None:
            context["workspace_context"] = workspace_context
        return context

    def _chat_turn_messages(
        self,
        *,
        intent: str,
        chat_style: str,
        content: str,
        grounding_mode: str,
        source_context: dict,
        selection,
        profile: dict,
        timestamp: int,
        user_id: str | None = None,
        extra_assistant: dict | None = None,
    ) -> tuple[dict, dict]:
        user_id = user_id or self._ids("message")
        user_message = {
            "id": user_id,
            "role": "user",
            "intent": intent,
            "chat_style": chat_style,
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
        assistant = {
            "id": self._ids("message"),
            "role": "assistant",
            "intent": intent,
            "chat_style": chat_style,
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
        if extra_assistant:
            assistant = {**assistant, **extra_assistant}
        return user_message, assistant

    @staticmethod
    def _grounding_result(mode: str) -> str:
        if mode == "general-knowledge":
            return "general-knowledge"
        if mode == "supplemental":
            return "supplemental"
        return "covered"

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

    def _complete_message(
        self,
        subject_id: str,
        message_id: str,
        text: str,
        result: str,
        citations: list[dict],
        intent: str,
    ) -> None:
        timestamp = self._now()
        chat = self.get_chat(subject_id)
        updated = {
            **chat,
            "socratic_state": None,
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

    async def _run_session_assistant_loop(
        self,
        *,
        subject_id: str,
        session_id: str,
        assistant_id: str,
        profile: dict,
        messages: list[dict],
        tools: list[dict],
        selected_ids: list[str],
        focused_ids: list[str],
        grounding_mode: str,
        workspace_context: dict | None = None,
        model_id: str | None = None,
    ) -> tuple[str, list[dict]]:
        conversation = list(messages)
        available_tools = list(tools)
        collected_anchors: list[dict] = []
        tool_round = 0
        while True:
            use_tools = bool(available_tools) and tool_round < SESSION_AGENT_TOOL_ROUNDS
            if not use_tools and tool_round:
                conversation.append({"role": "user", "content": "请根据已有工具结果直接回答，不要再调用工具。"})
            _, session = self._find_session(session_id)
            current = next((item for item in session.get("messages", []) if item.get("id") == assistant_id), {})
            content_before = list(current.get("content") or [])
            accumulated = ""
            last_persist = 0.0

            def on_delta(chunk: str) -> None:
                nonlocal accumulated, last_persist
                if not isinstance(chunk, str) or not chunk:
                    return
                accumulated += chunk
                now = time.perf_counter()
                if last_persist and now - last_persist < 0.3:
                    return
                self._update_session_message(
                    subject_id,
                    session_id,
                    assistant_id,
                    {
                        "status": "generating",
                        "content": [self._markdown_block(accumulated)],
                        "updated_at": self._now(),
                    },
                )
                last_persist = now

            response = await self.model_client.chat(
                profile,
                conversation,
                tools=available_tools if use_tools else None,
                on_delta=on_delta,
            )
            if response.get("tools_unsupported") and use_tools:
                self._append_session_tool_event(
                    subject_id,
                    session_id,
                    assistant_id,
                    {
                        "id": self._ids("tool-event"),
                        "name": "tools-unsupported",
                        "status": "failed",
                        "summary": "当前模型不支持工具调用，已按普通问答回复",
                        "resource": None,
                        "arguments": None,
                    },
                )
                available_tools = []
                text = response.get("text") or ""
                if text:
                    return text, collected_anchors
                continue
            tool_calls = response.get("tool_calls") or []
            text = response.get("text") or ""
            if tool_calls and use_tools:
                self._update_session_message(
                    subject_id,
                    session_id,
                    assistant_id,
                    {"status": "generating", "content": content_before, "updated_at": self._now()},
                )
            if not tool_calls:
                return text, collected_anchors
            if not use_tools:
                return text or "我已经根据目前掌握的信息作答。", collected_anchors
            conversation.append({
                "role": "assistant",
                "content": text,
                "tool_calls": tool_calls,
            })
            for call in tool_calls:
                result_text, anchors = self._execute_session_tool(
                    subject_id=subject_id,
                    session_id=session_id,
                    assistant_id=assistant_id,
                    call=call,
                    selected_ids=selected_ids,
                    focused_ids=focused_ids,
                    grounding_mode=grounding_mode,
                    workspace_context=workspace_context,
                    model_id=model_id,
                )
                collected_anchors.extend(anchors)
                conversation.append({
                    "role": "tool",
                    "tool_call_id": call.get("id") or "",
                    "name": call.get("name") or "",
                    "content": result_text,
                })
            tool_round += 1

    def _session_assistant_tools(self, grounding_mode: str, selected_ids: list[str]) -> list[dict]:
        tools = []
        if grounding_mode != "general-knowledge" and selected_ids:
            tools.append({
                "name": "search_sources",
                "description": "在当前会话已选资料范围内检索相关片段。需要核对出处、补充依据或用户问到资料细节时使用；不要编造资料外内容。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "检索关键词或问题"},
                    },
                    "required": ["query"],
                },
            })
        tools.append({
            "name": "get_study_state",
            "description": "读取当前科目的学习状态摘要：最近蓝图、草稿、试卷、最近一次作答进度，以及最近错点。需要结合学习进度或错点时使用。",
            "parameters": {"type": "object", "properties": {}},
        })
        tools.append({
            "name": "propose_exam_blueprint",
            "description": "根据组卷要求创建一份待确认的组卷蓝图。只创建不确认；用户需到组卷区确认题型后再组题。",
            "parameters": {
                "type": "object",
                "properties": {
                    "requirements": {"type": "string", "description": "组卷要求或题目安排说明"},
                },
                "required": ["requirements"],
            },
        })
        tools.append({
            "name": "propose_revision",
            "description": "针对当前工作区选中的草稿、试卷或 AI 文档创建修改提案。只产生待确认差异，不应用。没有选中对象时不要假装已修改。",
            "parameters": {
                "type": "object",
                "properties": {
                    "instruction": {"type": "string", "description": "修改要求"},
                },
                "required": ["instruction"],
            },
        })
        tools.append({
            "name": "create_ai_document",
            "description": "根据说明创建一份 AI 资料文档。文档异步生成，用户需到资料区查看确认。不要替用户改已有文档。",
            "parameters": {
                "type": "object",
                "properties": {
                    "instruction": {"type": "string", "description": "文档主题或写作要求"},
                },
                "required": ["instruction"],
            },
        })
        return tools

    @staticmethod
    def _tool_use_instruction(tools: list[dict]) -> str:
        if not tools:
            return ""
        names = "、".join(item["name"] for item in tools)
        proposal_names = {"propose_exam_blueprint", "propose_revision", "create_ai_document"}
        text = (
            f" 你可以使用工具（{names}）。"
            "需要核对资料出处或当前学习状态时再调用只读工具；能直接回答就不要调用。"
        )
        if any(item["name"] in proposal_names for item in tools):
            text += (
                " 提案工具每次回复最多使用一个；创建后告诉用户去哪个区确认；"
                "不要替用户确认或应用提案。"
            )
        return text

    @staticmethod
    def _workspace_context(value) -> dict | None:
        if not isinstance(value, dict) or not value.get("workspace"):
            return None
        allowed = ("workspace", "blueprint_id", "draft_id", "exam_id", "ai_document_id", "attempt_id")
        cleaned = {key: value[key] for key in allowed if value.get(key)}
        return cleaned or None

    def _execute_session_tool(
        self,
        *,
        subject_id: str,
        session_id: str,
        assistant_id: str,
        call: dict,
        selected_ids: list[str],
        focused_ids: list[str],
        grounding_mode: str,
        workspace_context: dict | None = None,
        model_id: str | None = None,
    ) -> tuple[str, list[dict]]:
        started_at = self._now()
        started = time.perf_counter()
        name = call.get("name") or ""
        arguments = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
        event = {
            "id": self._ids("tool-event"),
            "name": name or "unknown",
            "status": "failed",
            "summary": "",
            "resource": None,
            "arguments": None,
        }
        anchors: list[dict] = []
        result_text = ""
        try:
            if name == "search_sources":
                query = arguments.get("query") if isinstance(arguments.get("query"), str) else ""
                event["arguments"] = {"query": query[:200]}
                if grounding_mode == "general-knowledge" or not selected_ids:
                    raise ValueError("当前对话不能检索资料")
                anchors = self.source_library.retrieve(query, selected_ids, priority_version_ids=focused_ids)
                result_text = self._anchors_text(anchors) or "未检索到相关资料片段。"
                event["status"] = "succeeded"
                event["summary"] = f"已检索资料：{query[:40]}" if query.strip() else "已检索资料"
            elif name == "get_study_state":
                event["arguments"] = {}
                result_text = self._tool_get_study_state(subject_id)
                event["status"] = "succeeded"
                event["summary"] = "已读取学习进度与最近错点"
            elif name == "propose_exam_blueprint":
                requirements = arguments.get("requirements") if isinstance(arguments.get("requirements"), str) else ""
                event["arguments"] = {"requirements": requirements[:200]}
                result_text, event["resource"], event["summary"] = self._tool_propose_exam_blueprint(
                    subject_id,
                    requirements,
                    grounding_mode,
                    selected_ids,
                    model_id,
                )
                event["status"] = "succeeded"
            elif name == "propose_revision":
                instruction = arguments.get("instruction") if isinstance(arguments.get("instruction"), str) else ""
                event["arguments"] = {"instruction": instruction[:200]}
                result_text, event["resource"], event["summary"] = self._tool_propose_revision(
                    instruction,
                    workspace_context,
                    model_id,
                )
                event["status"] = "succeeded"
            elif name == "create_ai_document":
                instruction = arguments.get("instruction") if isinstance(arguments.get("instruction"), str) else ""
                event["arguments"] = {"instruction": instruction[:200]}
                result_text, event["resource"], event["summary"] = self._tool_create_ai_document(
                    subject_id,
                    instruction,
                    grounding_mode,
                    selected_ids,
                    model_id,
                )
                event["status"] = "succeeded"
            else:
                result_text = f"未知工具：{name or '未命名'}"
                event["summary"] = result_text
        except LearningError as exc:
            result_text = str(exc)
            event["status"] = "failed"
            event["summary"] = str(exc) or f"{name or '工具'}执行失败"
        except Exception as exc:
            result_text = f"工具执行失败：{exc}"
            event["status"] = "failed"
            event["summary"] = f"{name or '工具'}执行失败"
        self.operations.record_stage(
            "tool-call",
            status=event["status"],
            started_at=started_at,
            completed_at=self._now(),
            outer_elapsed_ms=max(0, round((time.perf_counter() - started) * 1000)),
            counters={"model_calls": 1},
            attributes={"tool": name or "unknown"},
        )
        self._append_session_tool_event(subject_id, session_id, assistant_id, event)
        return result_text, anchors

    def _tool_propose_exam_blueprint(
        self,
        subject_id: str,
        requirements: str,
        grounding_mode: str,
        selected_ids: list[str],
        model_id: str | None,
    ) -> tuple[str, dict, str]:
        if self.exams is None:
            raise RuntimeError("组卷服务尚未就绪")
        accepted = self.exams.parse_blueprint(subject_id, {
            "prompt": requirements,
            "grounding_mode": grounding_mode,
            "source_version_ids": list(selected_ids),
            "model_id": model_id,
        })
        resource = accepted["resource"]
        summary = "已创建蓝图，正在解析"
        return self._proposal_tool_result(resource, f"{summary}，请到组卷区确认"), resource, summary

    def _tool_propose_revision(
        self,
        instruction: str,
        workspace_context: dict | None,
        model_id: str | None,
    ) -> tuple[str, dict | None, str]:
        context = workspace_context if isinstance(workspace_context, dict) else {}
        workspace = context.get("workspace")
        draft_id = context.get("draft_id")
        exam_id = context.get("exam_id")
        ai_document_id = context.get("ai_document_id")
        if workspace == "sources":
            draft_id = None
            exam_id = None
        elif workspace == "exam":
            ai_document_id = None
            if draft_id:
                exam_id = None
        elif workspace in {"learn", "attempt"}:
            draft_id = exam_id = ai_document_id = None
        if draft_id:
            if self.exams is None:
                raise RuntimeError("组卷服务尚未就绪")
            accepted = self.exams.create_draft_revision_proposal(draft_id, {
                "instruction": instruction,
                "scope": {"kind": "whole-exam", "question_ids": [], "block_ids": []},
                "model_id": model_id,
            })
            resource = accepted["resource"]
            summary = "已创建草稿修改提案"
            return self._proposal_tool_result(resource, f"{summary}，请到组卷区确认"), resource, summary
        if exam_id:
            if self.exams is None:
                raise RuntimeError("组卷服务尚未就绪")
            _, exam = self._find_owned("exams", exam_id)
            accepted = self.exams.create_revision_proposal(exam_id, {
                "base_version_id": exam["current_version_id"],
                "instruction": instruction,
                "scope": {"kind": "whole-exam", "question_ids": [], "block_ids": []},
                "model_id": model_id,
            })
            resource = accepted["resource"]
            summary = "已创建试卷修改提案"
            return self._proposal_tool_result(resource, f"{summary}，请到组卷区确认"), resource, summary
        if ai_document_id:
            if self.documents is None:
                raise RuntimeError("文档服务尚未就绪")
            document = self.documents.get_document(ai_document_id)
            accepted = self.documents.create_proposal(ai_document_id, {
                "base_version_id": document["current_version_id"],
                "instruction": instruction,
                "model_id": model_id,
            })
            resource = accepted["resource"]
            summary = "已创建文档修改提案"
            return self._proposal_tool_result(resource, f"{summary}，请到资料区确认"), resource, summary
        summary = "当前没有选中可修改的对象"
        return summary, None, summary

    def _tool_create_ai_document(
        self,
        subject_id: str,
        instruction: str,
        grounding_mode: str,
        selected_ids: list[str],
        model_id: str | None,
    ) -> tuple[str, dict, str]:
        if self.documents is None:
            raise RuntimeError("文档服务尚未就绪")
        accepted = self.documents.create_document(subject_id, {
            "instruction": instruction,
            "source_version_ids": list(selected_ids),
            "grounding_mode": grounding_mode,
            "model_id": model_id,
        })
        resource = accepted["resource"]
        summary = "已创建 AI 文档，正在生成"
        return self._proposal_tool_result(resource, f"{summary}，请到资料区查看"), resource, summary

    @staticmethod
    def _proposal_tool_result(resource: dict | None, summary: str) -> str:
        return json.dumps({"resource": resource, "message": summary}, ensure_ascii=False)

    def _tool_get_study_state(self, subject_id: str) -> str:
        if self.exams is None:
            payload = {
                "blueprints": [],
                "drafts": [],
                "exams": [],
                "latest_attempt": None,
                "missed_knowledge_points": [],
            }
            return json.dumps(payload, ensure_ascii=False)
        blueprints = self.exams.list_blueprints(subject_id)
        drafts = self.exams.list_drafts(subject_id)
        papers = self.exams.list_exams(subject_id)
        attempts = self._subject(subject_id).get("data", {}).get("attempts", [])

        def recent(items, count=3):
            return sorted(items, key=lambda item: item.get("updated_at") or item.get("created_at") or 0, reverse=True)[:count]

        latest_attempt = None
        if attempts:
            attempt = max(attempts, key=lambda item: item.get("updated_at") or 0)
            exam = next((item for item in papers if item.get("id") == attempt.get("exam_id")), None)
            title = ((exam or {}).get("document") or {}).get("title") or (attempt.get("paper") or {}).get("title")
            questions = (attempt.get("paper") or {}).get("questions") or []
            latest_attempt = {
                "exam_title": title,
                "mode": attempt.get("mode"),
                "status": attempt.get("completion_status") or attempt.get("status"),
                "progress": f"{len(attempt.get('answers') or [])}/{len(questions)}",
            }
        payload = {
            "blueprints": [{"title": item.get("title"), "status": item.get("status")} for item in recent(blueprints)],
            "drafts": [{"title": item.get("title"), "status": item.get("status")} for item in recent(drafts)],
            "exams": [
                {"title": (item.get("document") or {}).get("title") or item.get("title"), "status": "published"}
                for item in recent(papers)
            ],
            "latest_attempt": latest_attempt,
            "missed_knowledge_points": self.exams._recent_missed_knowledge_points(subject_id),
        }
        return json.dumps(payload, ensure_ascii=False)

    def _append_session_tool_event(self, subject_id: str, session_id: str, assistant_id: str, event: dict) -> None:
        _, session = self._find_session(session_id)
        current = next((item for item in session.get("messages", []) if item.get("id") == assistant_id), {})
        events = [*(current.get("tool_events") or []), event]
        self._update_session_message(
            subject_id,
            session_id,
            assistant_id,
            {"tool_events": events, "updated_at": self._now()},
        )

    def _grounded_messages(
        self,
        chat: dict,
        payload: dict,
        anchors: list[dict],
        grounding_mode: str,
        profile: dict,
        selection_context: str | None = None,
        attachments: list[dict] | None = None,
        extra_instruction: str = "",
    ) -> list[dict]:
        intent = payload["intent"]
        instruction = self._grounding_instruction(grounding_mode)
        chat_style = self._requested_chat_style(payload, self._stored_chat_style(chat))
        instruction += self._chat_style_instruction(chat_style)
        if extra_instruction:
            instruction += extra_instruction
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
    def _stored_chat_style(value: dict) -> str:
        style = value.get("chat_style")
        if style in {"default", "socratic", "crash-course"}:
            return style
        legacy = value.get("learning_mode")
        return legacy if legacy in {"socratic", "crash-course"} else "default"

    @classmethod
    def _requested_chat_style(cls, payload: dict, fallback: str) -> str:
        if payload.get("chat_style") in {"default", "socratic", "crash-course"}:
            return payload["chat_style"]
        if payload.get("learning_mode") in {"chat", "socratic", "crash-course"}:
            return "default" if payload["learning_mode"] == "chat" else payload["learning_mode"]
        return fallback

    @staticmethod
    def _legacy_learning_mode(chat_style: str) -> str:
        return "chat" if chat_style == "default" else chat_style

    @staticmethod
    def _chat_style_instruction(chat_style: str) -> str:
        if chat_style == "socratic":
            return (
                " 使用苏格拉底式交流：默认先让学习者尝试作答或解释，不要直接给出完整答案或把知识点讲完。"
                "优先用问题帮助学习者自己推理，鼓励先尝试并追问理由，发现误解时清楚纠正。"
                "这是交流风格，不要输出阶段、提示层级或教学状态 JSON。"
                "只有学习者明确要求直接讲解、给答案、跳过引导或只要标准答案时，才完整作答。"
            )
        if chat_style == "crash-course":
            return (
                " 使用章节速成风格：需要时先确认学习范围、可用时间和目标，"
                "再按章节或主题快速讲重点。允许用户跳过内容或只问某一部分，不强制返回目录 JSON。"
            )
        return ""

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
            "api_format": profile.get("api_format", DEFAULT_API_FORMAT),
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
            "MODEL_API_FORMAT_UNSUPPORTED",
            "MODEL_VALIDATION_INVALID",
        }:
            status = 422
            code = "VALIDATION_FAILED"
        else:
            status = 409
        raise LearningError(status, code, error.get("message", "操作失败"))
