"""FastAPI application assembled from the static HTTP contract."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api_models import (
    Citation,
    ErrorResponse,
    Operation,
    OperationAccepted,
    Source,
    SourceAnchorList,
    SourceAnchor,
    SourceList,
    SourceVersion,
    SourceVersionList,
)
from .ai_documents import AiDocumentService
from .attachments import AttachmentService
from .core_api import create_core_router
from .exam_api import create_exam_router
from .exams import ExamService
from .learning import LearningError, LearningService
from .model_client import ModelApiClient, ObservedModelClient
from .observability import EvaluationService, ObservabilityService
from .observability_api import create_observability_router
from .issue16_api import create_issue16_router
from .operations import OperationFailure, OperationManager
from .rendering import ExamRenderingService
from .rendering_api import create_rendering_router
from .sources import MAX_SOURCE_BYTES, SourceLibrary, SourceLibraryError
from .store import WorkspaceService, WorkspaceStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
FRONTEND_DIR = PROJECT_ROOT / "frontend"


def _error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    retryable: bool = False,
    details: dict | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": False,
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                "details": details or {},
            },
        },
    )


def create_app(data_dir: str | os.PathLike | None = None, model_client=None) -> FastAPI:
    data_path = Path(data_dir or os.environ.get("LEARNING_LOOP_DATA_DIR") or DEFAULT_DATA_DIR)
    store = WorkspaceStore(data_path / "workspace.json")
    workspace = WorkspaceService(store)
    operations = OperationManager(storage_path=data_path / "operations.json")
    observability = ObservabilityService(data_path / "observability.json")
    operations.set_observer(observability)
    client = ObservedModelClient(model_client or ModelApiClient(), observability)
    sources = SourceLibrary(workspace, operations, data_path)
    attachments = AttachmentService(workspace, data_path)
    learning = LearningService(workspace, sources, operations, client)
    learning.attachments = attachments
    documents = AiDocumentService(workspace, sources, operations, client)
    exams = ExamService(learning)
    rendering = ExamRenderingService(exams, data_path)
    evaluations = EvaluationService(learning, observability)
    learning.selection_resolver = exams.resolve_selection

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await operations.shutdown()

    app = FastAPI(title="Learning Loop Agent", lifespan=lifespan)
    app.state.workspace_service = workspace
    app.state.model_client = client
    app.state.operations = operations
    app.state.source_library = sources
    app.state.attachment_service = attachments
    app.state.ai_document_service = documents
    app.state.learning_service = learning
    app.state.exam_service = exams
    app.state.rendering_service = rendering
    app.state.observability_service = observability
    app.state.evaluation_service = evaluations
    app.state.store = store

    @app.exception_handler(LearningError)
    async def learning_error_handler(_, exc: LearningError):
        return _error_response(
            exc.status_code,
            exc.code,
            str(exc),
            retryable=exc.retryable,
            details=exc.details,
        )

    @app.exception_handler(SourceLibraryError)
    async def source_error_handler(_, exc: SourceLibraryError):
        return _error_response(
            exc.status_code,
            exc.code,
            str(exc),
            retryable=exc.retryable,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_, exc: RequestValidationError):
        details = {
            "fields": [
                {"path": ".".join(str(part) for part in item["loc"]), "message": item["msg"]}
                for item in exc.errors()
            ]
        }
        return _error_response(422, "VALIDATION_FAILED", "请求参数不符合 API 契约", details=details)

    app.include_router(create_issue16_router(learning, attachments, documents))
    app.include_router(create_core_router(learning))
    app.include_router(create_exam_router(exams))
    app.include_router(create_rendering_router(rendering))
    app.include_router(create_observability_router(observability, evaluations))

    @app.get(
        "/api/subjects/{subject_id}/sources",
        operation_id="listSources",
        response_model=SourceList,
        responses={404: {"model": ErrorResponse}},
    )
    def list_sources(subject_id: str):
        return {"items": sources.list_sources(subject_id)}

    @app.post(
        "/api/subjects/{subject_id}/sources",
        operation_id="uploadSource",
        status_code=202,
        response_model=OperationAccepted,
        responses={
            404: {"model": ErrorResponse},
            413: {"model": ErrorResponse},
            415: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
    )
    async def upload_source(
        subject_id: str,
        file: UploadFile = File(...),
        display_name: str | None = Form(default=None, min_length=1, max_length=255),
    ):
        try:
            content = await file.read(MAX_SOURCE_BYTES + 1)
            return sources.create_source(subject_id, file.filename, display_name, content)
        finally:
            await file.close()

    @app.get(
        "/api/sources/{source_id}",
        operation_id="getSource",
        response_model=Source,
        responses={404: {"model": ErrorResponse}},
    )
    def get_source(source_id: str):
        return sources.get_source(source_id)

    @app.delete(
        "/api/sources/{source_id}",
        operation_id="deleteSource",
        status_code=204,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def delete_source(source_id: str):
        sources.delete_source(source_id)
        return Response(status_code=204)

    @app.get(
        "/api/sources/{source_id}/versions",
        operation_id="listSourceVersions",
        response_model=SourceVersionList,
        responses={404: {"model": ErrorResponse}},
    )
    def list_source_versions(source_id: str):
        return {"items": sources.list_versions(source_id)}

    @app.post(
        "/api/sources/{source_id}/versions",
        operation_id="createSourceVersion",
        status_code=202,
        response_model=OperationAccepted,
        responses={
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            413: {"model": ErrorResponse},
            415: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
    )
    async def create_source_version(source_id: str, file: UploadFile = File(...)):
        try:
            content = await file.read(MAX_SOURCE_BYTES + 1)
            return sources.create_version(source_id, file.filename, content)
        finally:
            await file.close()

    @app.get(
        "/api/source-versions/{version_id}",
        operation_id="getSourceVersion",
        response_model=SourceVersion,
        responses={404: {"model": ErrorResponse}},
    )
    def get_source_version(version_id: str):
        return sources.get_version(version_id)

    @app.get(
        "/api/source-versions/{version_id}/anchors/{anchor_id}",
        operation_id="getSourceAnchor",
        response_model=SourceAnchor,
        responses={404: {"model": ErrorResponse}, 410: {"model": ErrorResponse}},
    )
    def get_source_anchor(version_id: str, anchor_id: str):
        return sources.get_anchor(version_id, anchor_id)

    @app.get(
        "/api/source-versions/{version_id}/assets/{asset_id}",
        operation_id="getSourceAsset",
        response_class=Response,
        responses={
            200: {
                "description": "原始资源字节",
                "content": {
                    "image/*": {"schema": {"type": "string", "format": "binary"}},
                    "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
                },
            },
            404: {"model": ErrorResponse},
            410: {"model": ErrorResponse},
        },
    )
    def get_source_asset(version_id: str, asset_id: str):
        content, mime_type = sources.get_asset(version_id, asset_id)
        return Response(content=content, media_type=mime_type)

    @app.get(
        "/api/source-versions/{version_id}/anchors",
        operation_id="listSourceVersionAnchors",
        response_model=SourceAnchorList,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 410: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def list_source_version_anchors(version_id: str):
        return {"items": sources.list_anchors(version_id)}

    @app.get(
        "/api/citations/{citation_id}",
        operation_id="getCitation",
        response_model=Citation,
        responses={404: {"model": ErrorResponse}},
    )
    def get_citation(citation_id: str):
        return sources.get_citation(citation_id)

    @app.get(
        "/api/operations/{operation_id}",
        operation_id="getOperation",
        response_model=Operation,
        responses={404: {"model": ErrorResponse}},
    )
    def get_operation(operation_id: str):
        operation = operations.get(operation_id)
        if not operation:
            return _error_response(404, "RESOURCE_NOT_FOUND", "异步任务不存在")
        return operation

    @app.post(
        "/api/operations/{operation_id}/cancel",
        operation_id="cancelOperation",
        status_code=202,
        response_model=OperationAccepted,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def cancel_operation(operation_id: str):
        try:
            operation = operations.cancel(operation_id)
        except OperationFailure as exc:
            status_code = 404 if exc.code == "RESOURCE_NOT_FOUND" else 409
            return _error_response(
                status_code,
                exc.code,
                str(exc),
                retryable=exc.retryable,
                details=exc.details,
            )
        return {"operation": operation, "resource": operation.get("resource")}

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return FileResponse(FRONTEND_DIR / "favicon.svg", media_type="image/svg+xml")

    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    return app


app = create_app()
