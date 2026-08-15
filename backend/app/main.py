"""FastAPI application shell."""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .domain import (
    CHAT_CLEAR,
    CHAT_SEND,
    CHAT_SWITCH_MODEL,
    MODEL_ADD,
    MODEL_CHECKING,
    MODEL_DELETE,
    MODEL_OK,
    MODEL_SET_VALIDATION,
    MODEL_VALIDATION_ERROR,
    SUBJECT_CREATE,
    SUBJECT_DELETE,
    SUBJECT_RENAME,
    SUBJECT_SWITCH,
)
from .generation import GenerationManager
from .model_client import OpenAiCompatibleModelClient
from .store import WorkspaceService, WorkspaceStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
FRONTEND_DIR = PROJECT_ROOT / "frontend"


class SubjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class SubjectRename(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ModelCreate(BaseModel):
    provider: str = Field(min_length=1, max_length=60)
    model: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str = ""


class ChatSend(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    model_id: str | None = None


class ChatModelSwitch(BaseModel):
    model_id: str = Field(min_length=1)


def _error_response(status_code: int, code: str, message: str, workspace: dict | None = None) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"ok": False, "error": {"code": code, "message": message}, "workspace": workspace})


def _workspace_response(result: dict, status_code: int = 200, **extra) -> JSONResponse:
    payload = {"ok": True, "workspace": result.get("workspace"), "message": result.get("message")}
    if result.get("persisted") is False:
        payload["tone"] = "error"
        payload["message"] = result.get("storage_error", {}).get("message", "写入失败")
    payload.update(extra)
    return JSONResponse(status_code=status_code, content=payload)


def create_app(data_dir: str | os.PathLike | None = None, model_client=None) -> FastAPI:
    data_path = Path(data_dir or os.environ.get("LEARNING_LOOP_DATA_DIR") or DEFAULT_DATA_DIR)
    store = WorkspaceStore(data_path / "workspace.json")
    service = WorkspaceService(store)
    client = model_client or OpenAiCompatibleModelClient()
    generations = GenerationManager(service, client)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await generations.shutdown()

    app = FastAPI(title="Learning Loop Agent", lifespan=lifespan)
    app.state.workspace_service = service
    app.state.model_client = client
    app.state.generations = generations
    app.state.store = store

    def result_or_error(result: dict, status_code: int = 400):
        if not result.get("ok"):
            return _error_response(
                status_code,
                result.get("error", {}).get("code", "BAD_REQUEST"),
                result.get("error", {}).get("message", "请求失败"),
                result.get("workspace"),
            )
        return _workspace_response(result)

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/workspace")
    def get_workspace():
        return {
            "ok": True,
            "workspace": service.workspace,
            "load_issue": service.store.last_load_issue,
        }

    @app.post("/api/subjects")
    def create_subject(payload: SubjectCreate):
        return result_or_error(service.dispatch({"type": SUBJECT_CREATE, "name": payload.name}))

    @app.patch("/api/subjects/{subject_id}")
    def rename_subject(subject_id: str, payload: SubjectRename):
        return result_or_error(service.dispatch({"type": SUBJECT_RENAME, "subject_id": subject_id, "name": payload.name}))

    @app.post("/api/subjects/{subject_id}/activate")
    def activate_subject(subject_id: str):
        return result_or_error(service.dispatch({"type": SUBJECT_SWITCH, "subject_id": subject_id}))

    @app.delete("/api/subjects/{subject_id}")
    def delete_subject(subject_id: str):
        if generations.has_active_for_subject(subject_id):
            return _error_response(409, "CHAT_GENERATION_IN_PROGRESS", "该科目有回答正在生成，请先停止生成", service.workspace)
        return result_or_error(service.dispatch({"type": SUBJECT_DELETE, "subject_id": subject_id}))

    @app.post("/api/models")
    def add_model(payload: ModelCreate):
        return result_or_error(
            service.dispatch(
                {
                    "type": MODEL_ADD,
                    "provider": payload.provider,
                    "model": payload.model,
                    "base_url": payload.base_url,
                    "api_key": payload.api_key,
                }
            )
        )

    @app.delete("/api/models/{model_id}")
    def delete_model(model_id: str):
        return result_or_error(service.dispatch({"type": MODEL_DELETE, "model_id": model_id}))

    @app.post("/api/models/{model_id}/verify")
    async def verify_model(model_id: str):
        result = service.dispatch(
            {"type": MODEL_SET_VALIDATION, "model_id": model_id, "validation": {"status": MODEL_CHECKING}}
        )
        if not result.get("ok"):
            return result_or_error(result)
        profile = next((m for m in service.workspace.get("models", []) if m["id"] == model_id), None)
        if not profile:
            return _error_response(404, "MODEL_SERVICE_NOT_FOUND", "模型服务不存在", service.workspace)
        try:
            response = await asyncio.wait_for(client.validate(profile), timeout=15)
            result = service.dispatch(
                {
                    "type": MODEL_SET_VALIDATION,
                    "model_id": model_id,
                    "validation": {"status": MODEL_OK, "message": f"验证通过：{response.get('provider')} / {response.get('model')}"},
                }
            )
            return result_or_error(result)
        except asyncio.TimeoutError:
            result = service.dispatch(
                {
                    "type": MODEL_SET_VALIDATION,
                    "model_id": model_id,
                    "validation": {"status": MODEL_VALIDATION_ERROR, "message": "验证超时，请检查模型服务地址和网络"},
                }
            )
            return _workspace_response(result, tone="error", message="验证超时，请检查模型服务地址和网络")
        except Exception as exc:
            result = service.dispatch(
                {
                    "type": MODEL_SET_VALIDATION,
                    "model_id": model_id,
                    "validation": {"status": MODEL_VALIDATION_ERROR, "message": str(exc) or "模型服务验证失败"},
                }
            )
            return _workspace_response(result, tone="error", message=str(exc) or "模型服务验证失败")

    @app.get("/api/subjects/{subject_id}/chat")
    def get_chat(subject_id: str):
        chat = service.get_chat(subject_id)
        if chat is None:
            raise HTTPException(status_code=404, detail="科目空间不存在")
        return {"ok": True, "chat": chat}

    @app.post("/api/subjects/{subject_id}/chat/messages")
    async def send_chat_message(subject_id: str, payload: ChatSend):
        result = service.dispatch(
            {
                "type": CHAT_SEND,
                "subject_id": subject_id,
                "content": payload.content,
                "model_id": payload.model_id,
            }
        )
        if not result.get("ok"):
            return result_or_error(result)
        request = result["request"]
        generation_id = generations.start(subject_id, request)
        return _workspace_response(result, status_code=202, generation_id=generation_id)

    @app.post("/api/subjects/{subject_id}/chat/model")
    def switch_chat_model(subject_id: str, payload: ChatModelSwitch):
        return result_or_error(service.dispatch({"type": CHAT_SWITCH_MODEL, "subject_id": subject_id, "model_id": payload.model_id}))

    @app.delete("/api/subjects/{subject_id}/chat")
    def clear_chat(subject_id: str):
        if generations.has_active_for_subject(subject_id):
            return _error_response(409, "CHAT_GENERATION_IN_PROGRESS", "回答正在生成中，请先停止生成再清空会话", service.workspace)
        return result_or_error(service.dispatch({"type": CHAT_CLEAR, "subject_id": subject_id}))

    @app.post("/api/generations/{generation_id}/stop")
    def stop_generation(generation_id: str):
        if not generations.get(generation_id):
            return _error_response(404, "NO_ACTIVE_GENERATION", "当前没有正在生成的回答", service.workspace)
        generations.stop(generation_id)
        return {"ok": True, "workspace": service.workspace, "message": "正在停止生成…", "tone": "warning"}

    @app.post("/api/subjects/{subject_id}/chat/stop")
    def stop_subject_generation(subject_id: str):
        if generations.stop_for_subject(subject_id):
            return {"ok": True, "workspace": service.workspace, "message": "正在停止生成…", "tone": "warning"}
        chat = service.get_chat(subject_id)
        if chat is not None and not any(m.get("status") == "generating" for m in chat.get("messages", [])):
            return {"ok": True, "workspace": service.workspace, "message": "生成已结束", "tone": "warning"}
        return _error_response(404, "NO_ACTIVE_GENERATION", "当前没有正在生成的回答", service.workspace)

    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    return app


app = create_app()
