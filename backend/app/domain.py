"""Pure domain rules for the learning-loop workspace.

The workspace is a plain JSON-serializable dict.  Every user-visible action
goes through :func:`apply_action`; persistence, model IO and HTTP rendering are
adapters outside this module.
"""
from __future__ import annotations

import math
import re
import time
import uuid
from urllib.parse import urlparse

SCHEMA_VERSION = 1
SUBJECT_NAME_MAX_LENGTH = 80
CHAT_MESSAGE_MAX_LENGTH = 20_000
MODEL_PROVIDER_MAX_LENGTH = 60
MODEL_NAME_MAX_LENGTH = 120
MODEL_BASE_URL_MAX_LENGTH = 500
MODEL_API_KEY_MAX_LENGTH = 2000
DEFAULT_API_FORMAT = "openai-chat-completions"
API_FORMATS = {DEFAULT_API_FORMAT, "openai-responses", "ollama"}

SUBJECT_CREATE = "subject/create"
SUBJECT_RENAME = "subject/rename"
SUBJECT_SWITCH = "subject/switch"
SUBJECT_DELETE = "subject/delete"

MODEL_ADD = "model/add"
MODEL_UPDATE = "model/update"
MODEL_DELETE = "model/delete"
MODEL_SET_VALIDATION = "model/set-validation"

CHAT_SEND = "chat/send"
CHAT_APPEND = "chat/append-chunk"
CHAT_COMPLETE = "chat/complete"
CHAT_FAIL = "chat/fail"
CHAT_STOP = "chat/stop"
CHAT_CLEAR = "chat/clear"
CHAT_SWITCH_MODEL = "chat/switch-model"

SOURCE_CREATE = "source/create"
SOURCE_ADD_VERSION = "source/add-version"
SOURCE_COMPLETE_VERSION = "source/complete-version"
SOURCE_FAIL_VERSION = "source/fail-version"
SOURCE_DELETE = "source/delete"

MESSAGE_GENERATING = "generating"
MESSAGE_COMPLETE = "complete"
MESSAGE_STOPPED = "stopped"
MESSAGE_ERROR = "error"

MODEL_CHECKING = "checking"
MODEL_OK = "ok"
MODEL_VALIDATION_ERROR = "error"
MODEL_UNKNOWN = "unknown"


def _error(code: str, message: str) -> dict:
    return {"code": code, "message": message}


def _fail(workspace: dict, code: str, message: str) -> dict:
    return {"ok": False, "workspace": workspace, "error": _error(code, message)}


def _ok(workspace: dict, **extra) -> dict:
    return {"ok": True, "workspace": workspace, **extra}


def _now_ms(value=None) -> int:
    if value is None:
        return int(time.time() * 1000)
    if callable(value):
        value = value()
    return int(value)


def _clock(value=None):
    if callable(value):
        return value
    if value is None:
        return lambda: _now_ms()
    return lambda: value


def _ids(value=None):
    if callable(value):
        return value
    if value is None:
        return lambda: uuid.uuid4().hex
    return lambda: str(value)


def initial_workspace(now=None) -> dict:
    timestamp = _now_ms(now)
    return {
        "schema_version": SCHEMA_VERSION,
        "active_subject_id": None,
        "current_model_id": None,
        "subjects": [],
        "models": [],
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def _find_subject(workspace: dict, subject_id: str) -> dict | None:
    return next((s for s in workspace.get("subjects", []) if s["id"] == subject_id), None)


def _active_subject(workspace: dict) -> dict | None:
    return _find_subject(workspace, workspace.get("active_subject_id"))


def _find_model(workspace: dict, model_id: str) -> dict | None:
    return next((m for m in workspace.get("models", []) if m["id"] == model_id), None)


def _normalize_name(value) -> str | None:
    if not isinstance(value, str):
        return None
    source = value.strip()
    if re.search(r"[\u0000-\u001f\u007f]", source):
        return None
    name = re.sub(r"\s+", " ", source)
    return name or None


def _validate_subject_name(workspace: dict, value, except_subject_id=None) -> tuple[str | None, dict | None]:
    name = _normalize_name(value)
    if name is None:
        return None, _error("SUBJECT_NAME_REQUIRED", "请输入科目名称")
    if len(name) > SUBJECT_NAME_MAX_LENGTH:
        return None, _error("SUBJECT_NAME_TOO_LONG", f"科目名称不能超过 {SUBJECT_NAME_MAX_LENGTH} 个字符")
    normalized = name.casefold()
    for subject in workspace.get("subjects", []):
        if subject["id"] == except_subject_id:
            continue
        if (_normalize_name(subject.get("name", "")) or "").casefold() == normalized:
            return None, _error("SUBJECT_NAME_DUPLICATE", f"已存在同名科目空间「{name}」")
    return name, None


def _normalize_base_url(value: str | None) -> tuple[str | None, dict | None]:
    if not isinstance(value, str) or not value.strip():
        return None, _error("MODEL_BASE_URL_REQUIRED", "请输入模型服务 Base URL")
    candidate = value.strip()
    if len(candidate) > MODEL_BASE_URL_MAX_LENGTH:
        return None, _error("MODEL_BASE_URL_INVALID", "Base URL 过长")
    try:
        parsed = urlparse(candidate)
    except ValueError:
        parsed = None
    if not parsed or parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None, _error("MODEL_BASE_URL_INVALID", "Base URL 必须是有效的 http(s) 地址")
    return candidate.rstrip("/"), None


def _validate_model_input(workspace: dict, action: dict, except_model_id=None) -> tuple[dict | None, dict | None]:
    provider = _normalize_name(action.get("provider"))
    if not provider:
        return None, _error("MODEL_PROVIDER_REQUIRED", "请输入服务商名称")
    if len(provider) > MODEL_PROVIDER_MAX_LENGTH:
        return None, _error("MODEL_PROVIDER_TOO_LONG", f"服务商名称不能超过 {MODEL_PROVIDER_MAX_LENGTH} 个字符")

    api_format = action.get("api_format", DEFAULT_API_FORMAT)
    if api_format not in API_FORMATS:
        return None, _error("MODEL_API_FORMAT_UNSUPPORTED", "请选择受支持的模型 API 格式")

    model = _normalize_name(action.get("model"))
    if not model:
        return None, _error("MODEL_NAME_REQUIRED", "请输入模型名称")
    if len(model) > MODEL_NAME_MAX_LENGTH:
        return None, _error("MODEL_NAME_TOO_LONG", f"模型名称不能超过 {MODEL_NAME_MAX_LENGTH} 个字符")

    base_url, error = _normalize_base_url(action.get("base_url"))
    if error:
        return None, error

    api_key = action.get("api_key") or ""
    if not isinstance(api_key, str) or len(api_key) > MODEL_API_KEY_MAX_LENGTH:
        return None, _error("MODEL_API_KEY_INVALID", f"API Key 不能超过 {MODEL_API_KEY_MAX_LENGTH} 个字符")

    for candidate in workspace.get("models", []):
        if candidate["id"] == except_model_id:
            continue
        if (
            candidate["provider"].casefold() == provider.casefold()
            and candidate.get("api_format", DEFAULT_API_FORMAT) == api_format
            and candidate["model"].casefold() == model.casefold()
            and candidate["base_url"] == base_url
        ):
            return None, _error("MODEL_SERVICE_DUPLICATE", f"已存在相同的模型服务「{provider} / {model}」")
    capabilities = action.get("capabilities") if isinstance(action.get("capabilities"), dict) else {}
    return {
        "provider": provider,
        "api_format": api_format,
        "model": model,
        "base_url": base_url,
        "api_key": api_key,
        "capabilities": {
            "text": True,
            "vision": bool(capabilities.get("vision")),
            "source": capabilities.get("source") if capabilities.get("source") in {"configured", "verified"} else "configured",
        },
    }, None


def _set_chat(workspace: dict, subject: dict, chat: dict, timestamp: int) -> dict:
    subjects = []
    for candidate in workspace.get("subjects", []):
        if candidate["id"] == subject["id"]:
            data = {**(candidate.get("data") or {})}
            data["chat"] = chat
            subjects.append({**candidate, "updated_at": timestamp, "data": data})
        else:
            subjects.append(candidate)
    return {**workspace, "subjects": subjects, "updated_at": timestamp}


def _set_subject_data(workspace: dict, subject: dict, data: dict, timestamp: int) -> dict:
    updated = {**subject, "data": data, "updated_at": timestamp}
    subjects = [updated if candidate["id"] == subject["id"] else candidate for candidate in workspace.get("subjects", [])]
    return {**workspace, "subjects": subjects, "updated_at": timestamp}


def _find_source(workspace: dict, source_id: str) -> tuple[dict | None, dict | None]:
    for subject in workspace.get("subjects", []):
        source = next(
            (candidate for candidate in subject.get("data", {}).get("sources", []) if candidate.get("id") == source_id),
            None,
        )
        if source:
            return subject, source
    return None, None


def _find_source_version(workspace: dict, version_id: str) -> tuple[dict | None, dict | None]:
    for subject in workspace.get("subjects", []):
        version = next(
            (
                candidate
                for candidate in subject.get("data", {}).get("source_versions", [])
                if candidate.get("id") == version_id
            ),
            None,
        )
        if version:
            return subject, version
    return None, None


def _source_version_summary(version: dict) -> dict:
    return {
        key: version.get(key)
        for key in (
            "id",
            "number",
            "status",
            "content_hash",
            "mime_type",
            "size_bytes",
            "anchor_count",
            "cache_hit",
            "created_at",
            "processed_at",
        )
    }


def _empty_chat() -> dict:
    return {"active_model_id": None, "messages": []}


def _get_chat(workspace: dict, subject_id: str) -> dict:
    subject = _find_subject(workspace, subject_id)
    chat = (subject or {}).get("data", {}).get("chat") if subject else None
    if not chat or not isinstance(chat.get("messages"), list):
        return _empty_chat()
    return chat


def _ensure_chat(workspace: dict, subject: dict, timestamp: int) -> tuple[dict, dict]:
    chat = subject.get("data", {}).get("chat")
    if chat and isinstance(chat.get("messages"), list):
        return workspace, chat
    chat = _empty_chat()
    return _set_chat(workspace, subject, chat, timestamp), chat


def _model_snapshot(profile: dict) -> dict:
    return {
        "model_id": profile["id"],
        "provider": profile["provider"],
        "api_format": profile.get("api_format", DEFAULT_API_FORMAT),
        "model": profile["model"],
        "base_url": profile["base_url"],
    }


def build_chat_request_messages(chat: dict) -> list[dict]:
    messages = []
    for message in chat.get("messages", []):
        if message.get("role") == "user":
            messages.append({"role": "user", "content": message.get("content", "")})
        elif message.get("role") == "assistant":
            if message.get("status") in (MESSAGE_COMPLETE, MESSAGE_STOPPED) and message.get("content"):
                messages.append({"role": "assistant", "content": message["content"]})
    return messages


def apply_action(workspace: dict, action: dict, now=None, id_factory=None) -> dict:
    """Single app-level entry: user action + state -> next state + visible result."""
    action_type = action.get("type")
    now_fn = _clock(now)
    ids = _ids(id_factory)

    if action_type == SUBJECT_CREATE:
        return _create_subject(workspace, action, now_fn, ids)
    if action_type == SUBJECT_RENAME:
        return _rename_subject(workspace, action, now_fn)
    if action_type == SUBJECT_SWITCH:
        return _switch_subject(workspace, action, now_fn)
    if action_type == SUBJECT_DELETE:
        return _delete_subject(workspace, action, now_fn)
    if action_type == MODEL_ADD:
        return _add_model(workspace, action, now_fn, ids)
    if action_type == MODEL_UPDATE:
        return _update_model(workspace, action, now_fn)
    if action_type == MODEL_DELETE:
        return _delete_model(workspace, action, now_fn)
    if action_type == MODEL_SET_VALIDATION:
        return _set_model_validation(workspace, action, now_fn)
    if action_type == CHAT_SEND:
        return _send_chat(workspace, action, now_fn, ids)
    if action_type == CHAT_APPEND:
        return _append_chat(workspace, action, now_fn)
    if action_type == CHAT_COMPLETE:
        return _complete_chat(workspace, action, now_fn)
    if action_type == CHAT_FAIL:
        return _fail_chat(workspace, action, now_fn)
    if action_type == CHAT_STOP:
        return _stop_chat(workspace, action, now_fn)
    if action_type == CHAT_CLEAR:
        return _clear_chat(workspace, action, now_fn)
    if action_type == CHAT_SWITCH_MODEL:
        return _switch_chat_model(workspace, action, now_fn)
    if action_type == SOURCE_CREATE:
        return _create_source(workspace, action, now_fn, ids)
    if action_type == SOURCE_ADD_VERSION:
        return _add_source_version(workspace, action, now_fn, ids)
    if action_type == SOURCE_COMPLETE_VERSION:
        return _complete_source_version(workspace, action, now_fn)
    if action_type == SOURCE_FAIL_VERSION:
        return _fail_source_version(workspace, action, now_fn)
    if action_type == SOURCE_DELETE:
        return _delete_source(workspace, action, now_fn)
    return _fail(workspace, "INVALID_APP_ACTION", f"不支持的应用操作：{action_type}")


# --- subject spaces ---------------------------------------------------------


def _create_subject(workspace: dict, action: dict, now, ids) -> dict:
    name, error = _validate_subject_name(workspace, action.get("name"))
    if error:
        return _fail(workspace, error["code"], error["message"])
    timestamp = _now_ms(now())
    subject = {
        "id": ids(),
        "name": name,
        "created_at": timestamp,
        "updated_at": timestamp,
        "data": {},
    }
    return _ok(
        {**workspace, "active_subject_id": subject["id"], "subjects": [*workspace["subjects"], subject], "updated_at": timestamp},
        subject_id=subject["id"],
        message=f"已创建科目空间「{name}」",
    )


def _rename_subject(workspace: dict, action: dict, now) -> dict:
    subject = _find_subject(workspace, action.get("subject_id"))
    if not subject:
        return _fail(workspace, "SUBJECT_NOT_FOUND", "要重命名的科目空间不存在")
    name, error = _validate_subject_name(workspace, action.get("name"), except_subject_id=subject["id"])
    if error:
        return _fail(workspace, error["code"], error["message"])
    timestamp = _now_ms(now())
    renamed = {**subject, "name": name, "updated_at": timestamp}
    return _ok(
        {**workspace, "subjects": [renamed if s["id"] == subject["id"] else s for s in workspace["subjects"]], "updated_at": timestamp},
        subject_id=subject["id"],
        message=f"科目空间已重命名为「{name}」",
    )


def _switch_subject(workspace: dict, action: dict, now) -> dict:
    subject = _find_subject(workspace, action.get("subject_id"))
    if not subject:
        return _fail(workspace, "SUBJECT_NOT_FOUND", "要切换的科目空间不存在")
    if workspace.get("active_subject_id") == subject["id"]:
        return _ok(workspace, subject_id=subject["id"], message=f"当前已是「{subject['name']}」")
    timestamp = _now_ms(now())
    return _ok(
        {**workspace, "active_subject_id": subject["id"], "updated_at": timestamp},
        subject_id=subject["id"],
        message=f"已切换到「{subject['name']}」",
    )


def _delete_subject(workspace: dict, action: dict, now) -> dict:
    subject = _find_subject(workspace, action.get("subject_id"))
    if not subject:
        return _fail(workspace, "SUBJECT_NOT_FOUND", "要删除的科目空间不存在")
    remaining = [s for s in workspace["subjects"] if s["id"] != subject["id"]]
    active = workspace.get("active_subject_id")
    if active == subject["id"]:
        active = remaining[0]["id"] if remaining else None
    timestamp = _now_ms(now())
    return _ok(
        {**workspace, "subjects": remaining, "active_subject_id": active, "updated_at": timestamp},
        subject_id=subject["id"],
        message=f"已删除科目空间「{subject['name']}」",
    )


# --- model services ----------------------------------------------------------


def _add_model(workspace: dict, action: dict, now, ids) -> dict:
    fields, error = _validate_model_input(workspace, action)
    if error:
        return _fail(workspace, error["code"], error["message"])
    timestamp = _now_ms(now())
    profile = {
        "id": ids(),
        **fields,
        "created_at": timestamp,
        "updated_at": timestamp,
        "last_validation": None,
    }
    return _ok(
        {**workspace, "models": [*workspace.get("models", []), profile], "updated_at": timestamp},
        model_id=profile["id"],
        message=f"已添加模型服务「{profile['provider']} / {profile['model']}」",
    )


def _update_model(workspace: dict, action: dict, now) -> dict:
    existing = _find_model(workspace, action.get("model_id"))
    if not existing:
        return _fail(workspace, "MODEL_SERVICE_NOT_FOUND", "要修改的模型服务不存在")
    fields, error = _validate_model_input(workspace, action, except_model_id=existing["id"])
    if error:
        return _fail(workspace, error["code"], error["message"])
    timestamp = _now_ms(now())
    updated = {**existing, **fields, "updated_at": timestamp, "last_validation": None}
    return _ok(
        {**workspace, "models": [updated if m["id"] == existing["id"] else m for m in workspace.get("models", [])], "updated_at": timestamp},
        model_id=existing["id"],
        message=f"已更新模型服务「{updated['provider']} / {updated['model']}」",
    )


def _delete_model(workspace: dict, action: dict, now) -> dict:
    existing = _find_model(workspace, action.get("model_id"))
    if not existing:
        return _fail(workspace, "MODEL_SERVICE_NOT_FOUND", "要删除的模型服务不存在")
    timestamp = _now_ms(now())
    subjects = []
    for subject in workspace.get("subjects", []):
        data = subject.get("data", {})
        old_chat = data.get("chat")
        learning_chat = data.get("learning_chat")
        changed = False
        if old_chat and old_chat.get("active_model_id") == existing["id"]:
            data = {**data, "chat": {**old_chat, "active_model_id": None}}
            changed = True
        if learning_chat and learning_chat.get("active_model_id") == existing["id"]:
            data = {**data, "learning_chat": {**learning_chat, "active_model_id": None}}
            changed = True
        if changed:
            subjects.append({**subject, "data": data, "updated_at": timestamp})
        else:
            subjects.append(subject)
    return _ok(
        {
            **workspace,
            "models": [m for m in workspace.get("models", []) if m["id"] != existing["id"]],
            "subjects": subjects,
            "current_model_id": (
                None
                if workspace.get("current_model_id") == existing["id"]
                else workspace.get("current_model_id")
            ),
            "updated_at": timestamp,
        },
        model_id=existing["id"],
        message=f"已删除模型服务「{existing['provider']} / {existing['model']}」",
    )


def _set_model_validation(workspace: dict, action: dict, now) -> dict:
    profile = _find_model(workspace, action.get("model_id"))
    if not profile:
        return _fail(workspace, "MODEL_SERVICE_NOT_FOUND", "要验证的模型服务不存在")
    status = (action.get("validation") or {}).get("status")
    if status not in (MODEL_CHECKING, MODEL_OK, MODEL_VALIDATION_ERROR, MODEL_UNKNOWN):
        return _fail(workspace, "MODEL_VALIDATION_INVALID", "无效的模型验证状态")
    timestamp = _now_ms(now())
    validation = {
        "status": status,
        "checked_at": _now_ms((action.get("validation") or {}).get("checked_at") or timestamp),
        "message": (action.get("validation") or {}).get("message"),
    }
    updated = {**profile, "updated_at": timestamp, "last_validation": validation}
    return _ok(
        {**workspace, "models": [updated if m["id"] == profile["id"] else m for m in workspace.get("models", [])], "updated_at": timestamp},
        model_id=profile["id"],
        message="模型服务验证通过" if status == MODEL_OK else "模型服务验证状态已更新",
    )


# --- chat ---------------------------------------------------------------------


def _normalize_chat_text(value):
    if not isinstance(value, str) or not value.strip():
        return None, _error("CHAT_MESSAGE_REQUIRED", "请输入问题")
    text = value.strip()
    if len(text) > CHAT_MESSAGE_MAX_LENGTH:
        return None, _error("CHAT_MESSAGE_TOO_LONG", f"问题不能超过 {CHAT_MESSAGE_MAX_LENGTH} 个字符")
    return text, None


def _send_chat(workspace: dict, action: dict, now, ids) -> dict:
    subject = _find_subject(workspace, action.get("subject_id"))
    if not subject:
        return _fail(workspace, "CHAT_SUBJECT_NOT_FOUND", "当前科目空间不存在")
    workspace, chat = _ensure_chat(workspace, subject, _now_ms(now()))
    if any(m.get("status") == MESSAGE_GENERATING for m in chat.get("messages", [])):
        return _fail(workspace, "CHAT_GENERATION_IN_PROGRESS", "已有回答正在生成中，请先停止或等待完成")

    text, error = _normalize_chat_text(action.get("content"))
    if error:
        return _fail(workspace, error["code"], error["message"])

    model_id = action.get("model_id") or chat.get("active_model_id")
    if not model_id:
        return _fail(workspace, "CHAT_MODEL_NOT_SELECTED", "请先选择要使用的模型服务")
    profile = _find_model(workspace, model_id)
    if not profile:
        return _fail(workspace, "CHAT_MODEL_NOT_FOUND", "所选模型服务不存在，请重新选择")

    timestamp = _now_ms(now())
    user_message = {"id": ids(), "role": "user", "content": text, "created_at": timestamp}
    assistant_message = {
        "id": ids(),
        "role": "assistant",
        "content": "",
        "status": MESSAGE_GENERATING,
        "mode": "general-knowledge",
        "created_at": timestamp,
        "updated_at": timestamp,
        "completed_at": None,
        "model": _model_snapshot(profile),
        "error": None,
    }
    next_chat = {
        "active_model_id": model_id,
        "messages": [*chat.get("messages", []), user_message, assistant_message],
    }
    next_workspace = _set_chat(workspace, subject, next_chat, timestamp)
    return _ok(
        next_workspace,
        subject_id=subject["id"],
        message_id=assistant_message["id"],
        user_message_id=user_message["id"],
        message="问题已发送，正在生成回答",
        request={
            "subject_id": subject["id"],
            "assistant_message_id": assistant_message["id"],
            "model_profile": profile,
            "messages": build_chat_request_messages(next_chat),
        },
    )


def _message_and_chat(workspace: dict, subject_id: str, message_id: str) -> tuple[dict | None, dict | None, dict | None]:
    subject = _find_subject(workspace, subject_id)
    if not subject:
        return None, None, _error("CHAT_SUBJECT_NOT_FOUND", "当前科目空间不存在")
    chat = _get_chat(workspace, subject_id)
    message = next((m for m in chat.get("messages", []) if m["id"] == message_id), None)
    if not message:
        return subject, chat, _error("CHAT_MESSAGE_NOT_FOUND", "要更新的消息不存在")
    return subject, chat, message


def _append_chat(workspace: dict, action: dict, now) -> dict:
    result = _message_and_chat(workspace, action.get("subject_id"), action.get("message_id"))
    subject, chat, message = result
    if isinstance(message, dict) and "code" in message:
        return _fail(workspace, message["code"], message["message"])
    if message["status"] != MESSAGE_GENERATING:
        return _ok(workspace, message="生成已结束，忽略迟到的内容分片")
    if not isinstance(action.get("delta"), str):
        return _ok(workspace)
    timestamp = _now_ms(now())
    updated = {**message, "content": (message["content"] + action["delta"])[:CHAT_MESSAGE_MAX_LENGTH], "updated_at": timestamp}
    next_chat = {**chat, "messages": [updated if m["id"] == message["id"] else m for m in chat["messages"]]}
    return _ok(_set_chat(workspace, subject, next_chat, timestamp), message_id=message["id"])


def _complete_chat(workspace: dict, action: dict, now) -> dict:
    result = _message_and_chat(workspace, action.get("subject_id"), action.get("message_id"))
    subject, chat, message = result
    if isinstance(message, dict) and "code" in message:
        return _fail(workspace, message["code"], message["message"])
    if message["status"] != MESSAGE_GENERATING:
        return _ok(workspace, message="消息已不在生成状态")
    timestamp = _now_ms(now())
    content = action.get("text") if isinstance(action.get("text"), str) else message.get("content", "")
    updated = {
        **message,
        "content": content[:CHAT_MESSAGE_MAX_LENGTH],
        "status": MESSAGE_COMPLETE,
        "updated_at": timestamp,
        "completed_at": timestamp,
        "error": None,
    }
    next_chat = {**chat, "messages": [updated if m["id"] == message["id"] else m for m in chat["messages"]]}
    return _ok(_set_chat(workspace, subject, next_chat, timestamp), message_id=message["id"])


def _fail_chat(workspace: dict, action: dict, now) -> dict:
    result = _message_and_chat(workspace, action.get("subject_id"), action.get("message_id"))
    subject, chat, message = result
    if isinstance(message, dict) and "code" in message:
        return _fail(workspace, message["code"], message["message"])
    if message["status"] != MESSAGE_GENERATING:
        return _ok(workspace, message="消息已不在生成状态")
    timestamp = _now_ms(now())
    updated = {
        **message,
        "status": MESSAGE_ERROR,
        "updated_at": timestamp,
        "completed_at": timestamp,
        "error": {
            "code": action.get("error_code") or "MODEL_REQUEST_FAILED",
            "message": action.get("error_message") or "模型请求失败",
        },
    }
    next_chat = {**chat, "messages": [updated if m["id"] == message["id"] else m for m in chat["messages"]]}
    return _ok(_set_chat(workspace, subject, next_chat, timestamp), message_id=message["id"])


def _stop_chat(workspace: dict, action: dict, now) -> dict:
    result = _message_and_chat(workspace, action.get("subject_id"), action.get("message_id"))
    subject, chat, message = result
    if isinstance(message, dict) and "code" in message:
        return _fail(workspace, message["code"], message["message"])
    if message["status"] != MESSAGE_GENERATING:
        return _ok(workspace, message="消息已不在生成状态")
    timestamp = _now_ms(now())
    updated = {**message, "status": MESSAGE_STOPPED, "updated_at": timestamp, "completed_at": timestamp, "error": None}
    next_chat = {**chat, "messages": [updated if m["id"] == message["id"] else m for m in chat["messages"]]}
    return _ok(_set_chat(workspace, subject, next_chat, timestamp), message_id=message["id"])


def _clear_chat(workspace: dict, action: dict, now) -> dict:
    subject = _find_subject(workspace, action.get("subject_id"))
    if not subject:
        return _fail(workspace, "CHAT_SUBJECT_NOT_FOUND", "当前科目空间不存在")
    chat = _get_chat(workspace, subject["id"])
    timestamp = _now_ms(now())
    return _ok(
        _set_chat(workspace, subject, {**chat, "messages": []}, timestamp),
        subject_id=subject["id"],
        message="当前科目的会话记录已删除",
    )


def _switch_chat_model(workspace: dict, action: dict, now) -> dict:
    subject = _find_subject(workspace, action.get("subject_id"))
    if not subject:
        return _fail(workspace, "CHAT_SUBJECT_NOT_FOUND", "当前科目空间不存在")
    if not action.get("model_id"):
        return _fail(workspace, "CHAT_MODEL_NOT_SELECTED", "请选择要使用的模型服务")
    if not _find_model(workspace, action["model_id"]):
        return _fail(workspace, "CHAT_MODEL_NOT_FOUND", "所选模型服务不存在，请重新选择")
    workspace, chat = _ensure_chat(workspace, subject, _now_ms(now()))
    timestamp = _now_ms(now())
    return _ok(
        _set_chat(workspace, subject, {**chat, "active_model_id": action["model_id"]}, timestamp),
        subject_id=subject["id"],
        model_id=action["model_id"],
        message="已切换当前会话使用的模型",
    )


# --- source library -----------------------------------------------------------


def _new_source_version(source_id: str, number: int, action: dict, timestamp: int, version_id: str) -> dict:
    return {
        "id": version_id,
        "source_id": source_id,
        "number": number,
        "status": "processing",
        "content_hash": action["content_hash"],
        "mime_type": action["mime_type"],
        "size_bytes": action["size_bytes"],
        "anchor_count": 0,
        "cache_hit": False,
        "assets": [],
        "failure": None,
        "created_at": timestamp,
        "processed_at": None,
    }


def _create_source(workspace: dict, action: dict, now, ids) -> dict:
    subject = _find_subject(workspace, action.get("subject_id"))
    if not subject:
        return _fail(workspace, "RESOURCE_NOT_FOUND", "科目空间不存在")
    timestamp = _now_ms(now())
    source_id = ids()
    version = _new_source_version(source_id, 1, action, timestamp, ids())
    source = {
        "id": source_id,
        "subject_id": subject["id"],
        "display_name": action["display_name"],
        "media_kind": action["media_kind"],
        "status": "processing",
        "current_version": _source_version_summary(version),
        "version_count": 1,
        "failure": None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    data = {**subject.get("data", {})}
    data["sources"] = [*data.get("sources", []), source]
    data["source_versions"] = [*data.get("source_versions", []), version]
    return _ok(
        _set_subject_data(workspace, subject, data, timestamp),
        source=source,
        version=version,
        message=f"已上传用户资料「{source['display_name']}」",
    )


def _add_source_version(workspace: dict, action: dict, now, ids) -> dict:
    subject, source = _find_source(workspace, action.get("source_id"))
    if not source:
        return _fail(workspace, "RESOURCE_NOT_FOUND", "用户资料不存在")
    data = {**subject.get("data", {})}
    versions = [candidate for candidate in data.get("source_versions", []) if candidate.get("source_id") == source["id"]]
    if any(version.get("status") == "processing" for version in versions):
        return _fail(workspace, "OPERATION_IN_PROGRESS", "该资料已有版本正在处理")
    timestamp = _now_ms(now())
    version = _new_source_version(source["id"], max((item["number"] for item in versions), default=0) + 1, action, timestamp, ids())
    updated_source = {
        **source,
        "status": "processing",
        "current_version": _source_version_summary(version),
        "version_count": source.get("version_count", len(versions)) + 1,
        "failure": None,
        "updated_at": timestamp,
    }
    data["sources"] = [updated_source if candidate.get("id") == source["id"] else candidate for candidate in data.get("sources", [])]
    data["source_versions"] = [*data.get("source_versions", []), version]
    return _ok(
        _set_subject_data(workspace, subject, data, timestamp),
        source=updated_source,
        version=version,
        message=f"已创建资料版本 {version['number']}",
    )


def _complete_source_version(workspace: dict, action: dict, now) -> dict:
    subject, version = _find_source_version(workspace, action.get("version_id"))
    if not version:
        return _fail(workspace, "RESOURCE_NOT_FOUND", "资料版本不存在")
    if version.get("status") != "processing":
        return _fail(workspace, "RESOURCE_CONFLICT", "资料版本已不在处理中")
    timestamp = _now_ms(now())
    updated_version = {
        **version,
        "status": "ready",
        "anchor_count": int(action.get("anchor_count") or 0),
        "cache_hit": bool(action.get("cache_hit")),
        "assets": action.get("assets") or [],
        "failure": None,
        "processed_at": timestamp,
    }
    data = {**subject.get("data", {})}
    data["source_versions"] = [
        updated_version if candidate.get("id") == version["id"] else candidate
        for candidate in data.get("source_versions", [])
    ]
    source = next((candidate for candidate in data.get("sources", []) if candidate.get("id") == version["source_id"]), None)
    updated_source = source
    if source and (source.get("current_version") or {}).get("id") == version["id"]:
        updated_source = {
            **source,
            "status": "ready",
            "current_version": _source_version_summary(updated_version),
            "failure": None,
            "updated_at": timestamp,
        }
        data["sources"] = [
            updated_source if candidate.get("id") == source["id"] else candidate for candidate in data.get("sources", [])
        ]
    return _ok(
        _set_subject_data(workspace, subject, data, timestamp),
        source=updated_source,
        version=updated_version,
    )


def _fail_source_version(workspace: dict, action: dict, now) -> dict:
    subject, version = _find_source_version(workspace, action.get("version_id"))
    if not version:
        return _fail(workspace, "RESOURCE_NOT_FOUND", "资料版本不存在")
    if version.get("status") != "processing":
        return _ok(workspace, version=version)
    timestamp = _now_ms(now())
    failure = {
        "code": action.get("error_code") or "SOURCE_PROCESSING_FAILED",
        "message": action.get("error_message") or "资料解析失败",
        "retryable": bool(action.get("retryable")),
        "details": action.get("details") or {},
    }
    updated_version = {
        **version,
        "status": "failed",
        "failure": failure,
        "processed_at": timestamp,
    }
    data = {**subject.get("data", {})}
    data["source_versions"] = [
        updated_version if candidate.get("id") == version["id"] else candidate
        for candidate in data.get("source_versions", [])
    ]
    source = next((candidate for candidate in data.get("sources", []) if candidate.get("id") == version["source_id"]), None)
    updated_source = source
    if source and (source.get("current_version") or {}).get("id") == version["id"]:
        updated_source = {
            **source,
            "status": "failed",
            "current_version": _source_version_summary(updated_version),
            "failure": failure,
            "updated_at": timestamp,
        }
        data["sources"] = [
            updated_source if candidate.get("id") == source["id"] else candidate for candidate in data.get("sources", [])
        ]
    return _ok(
        _set_subject_data(workspace, subject, data, timestamp),
        source=updated_source,
        version=updated_version,
    )


def _delete_source(workspace: dict, action: dict, now) -> dict:
    subject, source = _find_source(workspace, action.get("source_id"))
    if not source:
        return _fail(workspace, "RESOURCE_NOT_FOUND", "用户资料不存在")
    timestamp = _now_ms(now())
    data = {**subject.get("data", {})}
    data["sources"] = [candidate for candidate in data.get("sources", []) if candidate.get("id") != source["id"]]
    data["source_versions"] = [
        {**version, "status": "unavailable"} if version.get("source_id") == source["id"] else version
        for version in data.get("source_versions", [])
    ]
    return _ok(
        _set_subject_data(workspace, subject, data, timestamp),
        source_id=source["id"],
        message=f"已从资料库删除「{source['display_name']}」",
    )


# --- restore / sanitize -------------------------------------------------------


def normalize_workspace(raw, now=None) -> tuple[dict, str | None]:
    """Restore a persisted JSON value into the current schema version."""
    timestamp = _now_ms(now)
    if not isinstance(raw, dict):
        return initial_workspace(timestamp), "本地状态已损坏，已从空工作区重新开始。"

    if raw.get("schema_version") is not None and raw.get("schema_version") != SCHEMA_VERSION:
        return initial_workspace(timestamp), f"无法识别本地状态版本 {raw.get('schema_version')}，已从空工作区重新开始。"

    models = _normalize_models(raw.get("models"), timestamp)
    model_ids = {m["id"] for m in models}
    subjects, dropped = _normalize_subjects(raw.get("subjects"), timestamp, model_ids)

    requested_active = raw.get("active_subject_id")
    active_subject_id = requested_active if any(s["id"] == requested_active for s in subjects) else (subjects[0]["id"] if subjects else None)
    issue = None
    if dropped or (requested_active and requested_active != active_subject_id):
        issue = "部分本地科目状态无法恢复，已保留可识别的科目。"

    workspace = {
        "schema_version": SCHEMA_VERSION,
        "active_subject_id": active_subject_id,
        "current_model_id": raw.get("current_model_id") if raw.get("current_model_id") in model_ids else None,
        "subjects": subjects,
        "models": models,
        "created_at": _number_or(raw.get("created_at"), timestamp),
        "updated_at": _number_or(raw.get("updated_at"), timestamp),
    }
    return workspace, issue


def _normalize_subjects(raw_subjects, timestamp: int, model_ids: set[str]) -> tuple[list[dict], bool]:
    if not isinstance(raw_subjects, list):
        return [], False
    subjects = []
    seen_ids = set()
    seen_names = set()
    dropped = False
    for candidate in raw_subjects:
        if not isinstance(candidate, dict):
            dropped = True
            continue
        subject_id = candidate.get("id")
        name = _normalize_name(candidate.get("name"))
        if not isinstance(subject_id, str) or not subject_id or not name or subject_id in seen_ids:
            dropped = True
            continue
        folded = name.casefold()
        if folded in seen_names:
            dropped = True
            continue
        seen_ids.add(subject_id)
        seen_names.add(folded)
        data = {**candidate["data"]} if isinstance(candidate.get("data"), dict) else {}
        if "chat" in data:
            data["chat"] = _normalize_chat(data["chat"], timestamp)
            if data["chat"].get("active_model_id") and data["chat"]["active_model_id"] not in model_ids:
                data["chat"] = {**data["chat"], "active_model_id": None}
        learning_chat = data.get("learning_chat")
        if isinstance(learning_chat, dict) and learning_chat.get("active_model_id") not in model_ids:
            data["learning_chat"] = {**learning_chat, "active_model_id": None}
        data = _recover_processing_sources(data, timestamp)
        subjects.append(
            {
                "id": subject_id,
                "name": name,
                "created_at": _number_or(candidate.get("created_at"), timestamp),
                "updated_at": _number_or(candidate.get("updated_at"), timestamp),
                "data": data,
            }
        )
    return subjects, dropped


def _recover_processing_sources(data: dict, timestamp: int) -> dict:
    versions = data.get("source_versions")
    if not isinstance(versions, list):
        return data

    failure = {
        "code": "SOURCE_PROCESSING_FAILED",
        "message": "资料解析因服务重启中断，请重新上传该版本",
        "retryable": True,
        "details": {},
    }
    recovered_versions = {}
    normalized_versions = []
    for version in versions:
        if isinstance(version, dict) and version.get("status") == "processing":
            version = {
                **version,
                "status": "failed",
                "failure": failure,
                "processed_at": timestamp,
            }
            if isinstance(version.get("id"), str):
                recovered_versions[version["id"]] = version
        normalized_versions.append(version)
    if not recovered_versions:
        return data

    normalized = {**data, "source_versions": normalized_versions}
    sources = data.get("sources")
    if not isinstance(sources, list):
        return normalized

    normalized["sources"] = []
    for source in sources:
        current = source.get("current_version") if isinstance(source, dict) else None
        recovered = recovered_versions.get(current.get("id")) if isinstance(current, dict) else None
        if recovered:
            source = {
                **source,
                "status": "failed",
                "current_version": _source_version_summary(recovered),
                "failure": failure,
                "updated_at": timestamp,
            }
        normalized["sources"].append(source)
    return normalized


def _normalize_models(raw_models, timestamp: int) -> list[dict]:
    if not isinstance(raw_models, list):
        return []
    models = []
    seen_ids = set()
    seen_keys = set()
    for candidate in raw_models:
        if not isinstance(candidate, dict):
            continue
        model_id = candidate.get("id")
        provider = _normalize_name(candidate.get("provider"))
        model = _normalize_name(candidate.get("model"))
        api_format = candidate.get("api_format", DEFAULT_API_FORMAT)
        base_url, error = _normalize_base_url(candidate.get("base_url"))
        if (
            not isinstance(model_id, str)
            or not model_id
            or not provider
            or not model
            or api_format not in API_FORMATS
            or error
            or model_id in seen_ids
        ):
            continue
        key = (provider.casefold(), api_format, model.casefold(), base_url)
        if key in seen_keys:
            continue
        seen_ids.add(model_id)
        seen_keys.add(key)
        capabilities = candidate.get("capabilities") if isinstance(candidate.get("capabilities"), dict) else {}
        models.append(
            {
                "id": model_id,
                "provider": provider,
                "api_format": api_format,
                "model": model,
                "base_url": base_url,
                "api_key": candidate.get("api_key") if isinstance(candidate.get("api_key"), str) else "",
                "capabilities": {
                    "text": True,
                    "vision": bool(capabilities.get("vision")),
                    "source": capabilities.get("source") if capabilities.get("source") in {"configured", "verified"} else "configured",
                },
                "created_at": _number_or(candidate.get("created_at"), timestamp),
                "updated_at": _number_or(candidate.get("updated_at"), timestamp),
                "last_validation": _normalize_validation(candidate.get("last_validation"), timestamp),
            }
        )
    return models


def _normalize_chat(value, timestamp: int) -> dict:
    if not isinstance(value, dict) or not isinstance(value.get("messages"), list):
        return _empty_chat()
    messages = []
    for candidate in value["messages"]:
        if not isinstance(candidate, dict):
            continue
        role = candidate.get("role")
        content = candidate.get("content") if isinstance(candidate.get("content"), str) else ""
        message_id = candidate.get("id")
        if role not in ("user", "assistant") or not isinstance(message_id, str) or not message_id:
            continue
        base = {"id": message_id, "role": role, "content": content, "created_at": _number_or(candidate.get("created_at"), timestamp)}
        if role == "user":
            messages.append(base)
            continue
        status = candidate.get("status")
        if status not in (MESSAGE_GENERATING, MESSAGE_COMPLETE, MESSAGE_STOPPED, MESSAGE_ERROR):
            status = MESSAGE_COMPLETE
        if status == MESSAGE_GENERATING:
            status = MESSAGE_STOPPED
        model = candidate.get("model")
        messages.append(
            {
                **base,
                "status": status,
                "updated_at": _number_or(candidate.get("updated_at"), timestamp),
                "completed_at": _number_or(candidate.get("completed_at"), timestamp),
                "mode": "general-knowledge",
                "model": {
                    "model_id": model.get("model_id") if isinstance(model, dict) and isinstance(model.get("model_id"), str) else None,
                    "provider": model.get("provider") if isinstance(model, dict) and isinstance(model.get("provider"), str) else "",
                    "api_format": (
                        model.get("api_format", DEFAULT_API_FORMAT)
                        if isinstance(model, dict) and model.get("api_format", DEFAULT_API_FORMAT) in API_FORMATS
                        else DEFAULT_API_FORMAT
                    ),
                    "model": model.get("model") if isinstance(model, dict) and isinstance(model.get("model"), str) else "",
                    "base_url": model.get("base_url") if isinstance(model, dict) and isinstance(model.get("base_url"), str) else "",
                },
                "error": {
                    "code": candidate["error"].get("code") if isinstance(candidate.get("error"), dict) and isinstance(candidate["error"].get("code"), str) else "MODEL_REQUEST_FAILED",
                    "message": candidate["error"].get("message") if isinstance(candidate.get("error"), dict) and isinstance(candidate["error"].get("message"), str) else "模型请求失败",
                } if isinstance(candidate.get("error"), dict) else None,
            }
        )
    return {
        "active_model_id": value.get("active_model_id") if isinstance(value.get("active_model_id"), str) else None,
        "messages": messages,
    }


def _normalize_validation(value, timestamp: int) -> dict | None:
    if not isinstance(value, dict):
        return None
    status = value.get("status")
    if status not in (MODEL_CHECKING, MODEL_OK, MODEL_VALIDATION_ERROR, MODEL_UNKNOWN):
        return None
    if status == MODEL_CHECKING:
        return None
    return {
        "status": status,
        "checked_at": _number_or(value.get("checked_at"), timestamp),
        "message": value.get("message") if isinstance(value.get("message"), str) else None,
    }


def _number_or(value, fallback: int) -> int:
    if isinstance(value, (int, float)) and math.isfinite(value):
        return int(value)
    return fallback
