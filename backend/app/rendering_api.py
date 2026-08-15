"""HTTP routes for unified exam rendering and export copies."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Query, Response

from .api_models import ErrorResponse, OperationAccepted
from .exam_models import ExamEdition, ExamExport, ExamExportInput, ExamRenderDocument


def create_rendering_router(rendering) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/exams/{exam_id}/render-document",
        operation_id="getExamRenderDocument",
        response_model=ExamRenderDocument,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def get_render_document(exam_id: str, edition: ExamEdition = Query(...)):
        return rendering.get_render_document(exam_id, edition)

    @router.post(
        "/api/exams/{exam_id}/exports",
        operation_id="createExamExport",
        status_code=202,
        response_model=OperationAccepted,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def create_export(exam_id: str, payload: ExamExportInput):
        return rendering.create_export(exam_id, payload.model_dump(exclude_none=True))

    @router.get(
        "/api/exports/{export_id}",
        operation_id="getExamExport",
        response_model=ExamExport,
        responses={404: {"model": ErrorResponse}},
    )
    def get_export(export_id: str):
        return rendering.get_export(export_id)

    @router.get(
        "/api/exports/{export_id}/file",
        operation_id="downloadExamExport",
        response_class=Response,
        responses={
            200: {
                "description": "导出文件",
                "content": {
                    "application/pdf": {"schema": {"type": "string", "format": "binary"}},
                    "text/markdown": {"schema": {"type": "string"}},
                },
            },
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
        },
    )
    def download_export(export_id: str):
        content, mime_type, file_name = rendering.get_export_file(export_id)
        disposition = f"attachment; filename*=UTF-8''{quote(file_name)}"
        return Response(content=content, media_type=mime_type, headers={"Content-Disposition": disposition})

    return router
