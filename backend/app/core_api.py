"""HTTP routes for subjects, models, chat, and learning artifacts."""
from __future__ import annotations

from fastapi import APIRouter, Response

from .api_models import (
    Chat,
    ChatConfigPatch,
    ChatMessageInput,
    ChatModelInput,
    CrashCourseInput,
    ErrorResponse,
    Health,
    LearningArtifact,
    LearningArtifactList,
    ModelService,
    ModelServiceInput,
    ModelServiceList,
    ModelServicePatch,
    OperationAccepted,
    Subject,
    SubjectInput,
    SubjectList,
    Workspace,
)
from .learning import LearningError
from .operations import OperationFailure


def create_core_router(learning) -> APIRouter:
    router = APIRouter()

    @router.get("/api/health", operation_id="getHealth", response_model=Health)
    def get_health():
        return {"status": "ok"}

    @router.get("/api/workspace", operation_id="getWorkspace", response_model=Workspace)
    def get_workspace():
        return learning.workspace()

    @router.get("/api/subjects", operation_id="listSubjects", response_model=SubjectList)
    def list_subjects():
        return {"items": learning.list_subjects()}

    @router.post(
        "/api/subjects",
        operation_id="createSubject",
        status_code=201,
        response_model=Subject,
        responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def create_subject(payload: SubjectInput):
        return learning.create_subject(payload.name)

    @router.get(
        "/api/subjects/{subject_id}",
        operation_id="getSubject",
        response_model=Subject,
        responses={404: {"model": ErrorResponse}},
    )
    def get_subject(subject_id: str):
        return learning.get_subject(subject_id)

    @router.patch(
        "/api/subjects/{subject_id}",
        operation_id="updateSubject",
        response_model=Subject,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def update_subject(subject_id: str, payload: SubjectInput):
        return learning.update_subject(subject_id, payload.name)

    @router.delete(
        "/api/subjects/{subject_id}",
        operation_id="deleteSubject",
        status_code=204,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def delete_subject(subject_id: str):
        learning.delete_subject(subject_id)
        return Response(status_code=204)

    @router.post(
        "/api/subjects/{subject_id}/activate",
        operation_id="activateSubject",
        response_model=Workspace,
        responses={404: {"model": ErrorResponse}},
    )
    def activate_subject(subject_id: str):
        return learning.activate_subject(subject_id)

    @router.get("/api/models", operation_id="listModels", response_model=ModelServiceList)
    def list_models():
        return {"items": learning.list_models()}

    @router.post(
        "/api/models",
        operation_id="createModel",
        status_code=201,
        response_model=ModelService,
        responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def create_model(payload: ModelServiceInput):
        return learning.create_model(payload.model_dump(exclude_none=True))

    @router.get(
        "/api/models/{model_id}",
        operation_id="getModel",
        response_model=ModelService,
        responses={404: {"model": ErrorResponse}},
    )
    def get_model(model_id: str):
        return learning.get_model(model_id)

    @router.patch(
        "/api/models/{model_id}",
        operation_id="updateModel",
        response_model=ModelService,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def update_model(model_id: str, payload: ModelServicePatch):
        patch = payload.model_dump(exclude_unset=True)
        if not patch:
            raise LearningError(422, "VALIDATION_FAILED", "至少提供一个需要修改的字段")
        return learning.update_model(model_id, patch)

    @router.delete(
        "/api/models/{model_id}",
        operation_id="deleteModel",
        status_code=204,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def delete_model(model_id: str):
        learning.delete_model(model_id)
        return Response(status_code=204)

    @router.post(
        "/api/models/{model_id}/verify",
        operation_id="verifyModel",
        status_code=202,
        response_model=OperationAccepted,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    async def verify_model(model_id: str):
        return learning.verify_model(model_id)

    @router.get(
        "/api/subjects/{subject_id}/chat",
        operation_id="getChat",
        response_model=Chat,
        responses={404: {"model": ErrorResponse}},
    )
    def get_chat(subject_id: str):
        return learning.get_chat(subject_id)

    @router.patch(
        "/api/subjects/{subject_id}/chat",
        operation_id="configureChat",
        response_model=Chat,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def configure_chat(subject_id: str, payload: ChatConfigPatch):
        patch = payload.model_dump(exclude_unset=True)
        if not patch:
            raise LearningError(422, "VALIDATION_FAILED", "至少提供一项会话配置")
        return learning.configure_chat(subject_id, patch)

    @router.delete(
        "/api/subjects/{subject_id}/chat",
        operation_id="clearChat",
        status_code=204,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def clear_chat(subject_id: str):
        learning.clear_chat(subject_id)
        return Response(status_code=204)

    @router.post(
        "/api/subjects/{subject_id}/chat/model",
        operation_id="switchChatModel",
        response_model=Chat,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def switch_chat_model(subject_id: str, payload: ChatModelInput):
        return learning.switch_chat_model(subject_id, payload.model_id)

    @router.post(
        "/api/subjects/{subject_id}/chat/messages",
        operation_id="createChatMessage",
        status_code=202,
        response_model=OperationAccepted,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def create_chat_message(subject_id: str, payload: ChatMessageInput):
        return learning.create_chat_message(subject_id, payload.model_dump(exclude_none=True))

    @router.post(
        "/api/subjects/{subject_id}/chat/crash-course",
        operation_id="generateCrashCourse",
        status_code=202,
        response_model=OperationAccepted,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def generate_crash_course(subject_id: str, payload: CrashCourseInput):
        return learning.generate_crash_course(subject_id, payload.model_dump(exclude_none=True))

    @router.post(
        "/api/subjects/{subject_id}/chat/stop",
        operation_id="stopSubjectChatGeneration",
        status_code=202,
        response_model=OperationAccepted,
        responses={404: {"model": ErrorResponse}},
    )
    def stop_chat(subject_id: str):
        return learning.stop_chat(subject_id)

    @router.post(
        "/api/generations/{generation_id}/stop",
        operation_id="stopGeneration",
        status_code=202,
        response_model=OperationAccepted,
        responses={404: {"model": ErrorResponse}},
        deprecated=True,
    )
    def stop_generation(generation_id: str):
        try:
            operation = learning.operations.cancel(generation_id)
        except OperationFailure as exc:
            status = 404 if exc.code == "RESOURCE_NOT_FOUND" else 409
            raise LearningError(status, exc.code, str(exc)) from exc
        return {"operation": operation, "resource": operation.get("resource")}

    @router.get(
        "/api/subjects/{subject_id}/artifacts",
        operation_id="listArtifacts",
        response_model=LearningArtifactList,
        responses={404: {"model": ErrorResponse}},
    )
    def list_artifacts(subject_id: str):
        return {"items": learning.list_artifacts(subject_id)}

    @router.get(
        "/api/artifacts/{artifact_id}",
        operation_id="getArtifact",
        response_model=LearningArtifact,
        responses={404: {"model": ErrorResponse}},
    )
    def get_artifact(artifact_id: str):
        return learning.get_artifact(artifact_id)

    @router.delete(
        "/api/artifacts/{artifact_id}",
        operation_id="deleteArtifact",
        status_code=204,
        responses={404: {"model": ErrorResponse}},
    )
    def delete_artifact(artifact_id: str):
        learning.delete_artifact(artifact_id)
        return Response(status_code=204)

    return router
