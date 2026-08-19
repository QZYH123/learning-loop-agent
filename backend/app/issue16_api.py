"""HTTP adapters introduced by Issue 16."""
from __future__ import annotations

from fastapi import APIRouter, File, Response, UploadFile

from .api_models import (
    AiDocument,
    AiDocumentCreateInput,
    AiDocumentList,
    AiDocumentRevisionInput,
    AiDocumentRevisionProposal,
    AiDocumentRevisionProposalList,
    AiDocumentVersionList,
    ChatMessage,
    ChatMessageInput,
    ChatMessageRetryInput,
    ErrorResponse,
    ModelDiscoveryInput,
    ModelDiscoveryResponse,
    ModelSelection,
    ModelService,
    OperationAccepted,
    Session,
    SessionInput,
    SessionList,
    SessionPatch,
    SessionSource,
    SessionNoteInput,
    SessionSourceInput,
    SessionSourceList,
    SessionSourcePatch,
    TempAttachment,
)


def create_issue16_router(learning, attachments, documents) -> APIRouter:
    router = APIRouter(responses={422: {"model": ErrorResponse}})

    @router.get("/api/subjects/{subject_id}/sessions", operation_id="listSessions", response_model=SessionList, responses={404: {"model": ErrorResponse}})
    def list_sessions(subject_id: str):
        return learning.list_sessions(subject_id)

    @router.post("/api/subjects/{subject_id}/sessions", operation_id="createSession", status_code=201, response_model=Session, responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}})
    def create_session(subject_id: str, payload: SessionInput | None = None):
        return learning.create_session(subject_id, (payload or SessionInput()).model_dump(exclude_none=True, exclude_unset=True))

    @router.get("/api/sessions/{session_id}", operation_id="getSession", response_model=Session, responses={404: {"model": ErrorResponse}})
    def get_session(session_id: str):
        return learning.get_session(session_id)

    @router.patch("/api/sessions/{session_id}", operation_id="updateSession", response_model=Session, responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}})
    def update_session(session_id: str, payload: SessionPatch):
        return learning.update_session(session_id, payload.model_dump(exclude_unset=True))

    @router.delete("/api/sessions/{session_id}", operation_id="deleteSession", status_code=204, responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
    def delete_session(session_id: str):
        learning.delete_session(session_id)
        return Response(status_code=204)

    @router.post("/api/sessions/{session_id}/activate", operation_id="activateSession", response_model=Session, responses={404: {"model": ErrorResponse}})
    def activate_session(session_id: str):
        return learning.activate_session(session_id)

    @router.get("/api/sessions/{session_id}/sources", operation_id="listSessionSources", response_model=SessionSourceList, responses={404: {"model": ErrorResponse}})
    def list_session_sources(session_id: str):
        return learning.list_session_sources(session_id)

    @router.post("/api/sessions/{session_id}/sources", operation_id="addSessionSource", status_code=201, response_model=SessionSource, responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}})
    def add_session_source(session_id: str, payload: SessionSourceInput):
        return learning.add_session_source(session_id, payload.source_version_id)

    @router.patch("/api/sessions/{session_id}/sources/{version_id}", operation_id="updateSessionSource", response_model=SessionSource, responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}})
    def update_session_source(session_id: str, version_id: str, payload: SessionSourcePatch):
        return learning.update_session_source(session_id, version_id, payload.source_version_id)

    @router.delete("/api/sessions/{session_id}/sources/{version_id}", operation_id="removeSessionSource", status_code=204, responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
    def remove_session_source(session_id: str, version_id: str):
        learning.remove_session_source(session_id, version_id)
        return Response(status_code=204)

    @router.post("/api/sessions/{session_id}/messages", operation_id="createSessionMessage", status_code=202, response_model=OperationAccepted, responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}})
    async def create_session_message(session_id: str, payload: ChatMessageInput):
        return learning.create_session_message(session_id, payload.model_dump(exclude_none=True))

    @router.post(
        "/api/sessions/{session_id}/messages/{message_id}/retry",
        operation_id="retrySessionMessage",
        status_code=202,
        response_model=OperationAccepted,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def retry_session_message(session_id: str, message_id: str, payload: ChatMessageRetryInput | None = None):
        body = (payload or ChatMessageRetryInput()).model_dump(exclude_none=True)
        return learning.retry_session_message(session_id, message_id, body)

    @router.post(
        "/api/sessions/{session_id}/notes",
        operation_id="appendSessionNote",
        status_code=201,
        response_model=ChatMessage,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def append_session_note(session_id: str, payload: SessionNoteInput):
        return learning.append_session_note(session_id, payload.model_dump())

    @router.post("/api/subjects/{subject_id}/attachments", operation_id="uploadChatAttachment", status_code=201, response_model=TempAttachment, responses={404: {"model": ErrorResponse}, 413: {"model": ErrorResponse}, 415: {"model": ErrorResponse}, 422: {"model": ErrorResponse}})
    async def upload_chat_attachment(subject_id: str, file: UploadFile = File(...)):
        try:
            content = await file.read()
            return attachments.upload(subject_id, file.filename, file.content_type, content)
        finally:
            await file.close()

    @router.get("/api/attachments/{attachment_id}", operation_id="getChatAttachment", response_model=TempAttachment, responses={404: {"model": ErrorResponse}, 410: {"model": ErrorResponse}})
    def get_chat_attachment(attachment_id: str):
        return attachments.get(attachment_id)

    @router.delete("/api/attachments/{attachment_id}", operation_id="deleteChatAttachment", status_code=204, responses={404: {"model": ErrorResponse}})
    def delete_chat_attachment(attachment_id: str):
        attachments.delete(attachment_id)
        return Response(status_code=204)

    @router.get("/api/attachments/{attachment_id}/file", operation_id="downloadChatAttachment", response_class=Response, responses={404: {"model": ErrorResponse}, 410: {"model": ErrorResponse}})
    def download_chat_attachment(attachment_id: str):
        content, mime_type = attachments.file(attachment_id)
        return Response(content=content, media_type=mime_type)

    @router.get("/api/models/current", operation_id="getCurrentModel", response_model=ModelService | None, responses={404: {"model": ErrorResponse}})
    def get_current_model():
        return learning.get_current_model()

    @router.put("/api/models/current", operation_id="selectCurrentModel", response_model=ModelService, responses={404: {"model": ErrorResponse}})
    def select_current_model(payload: ModelSelection):
        return learning.select_current_model(payload.model_id)

    @router.post("/api/models/discover", operation_id="discoverModels", response_model=ModelDiscoveryResponse, responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}})
    def discover_models(payload: ModelDiscoveryInput):
        return learning.discover_models(payload.model_dump(mode="json", exclude_none=True))

    @router.get("/api/subjects/{subject_id}/documents", operation_id="listAiDocuments", response_model=AiDocumentList, responses={404: {"model": ErrorResponse}})
    def list_ai_documents(subject_id: str):
        return {"items": documents.list_documents(subject_id)}

    @router.post("/api/subjects/{subject_id}/documents", operation_id="createAiDocument", status_code=202, response_model=OperationAccepted, responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}})
    async def create_ai_document(subject_id: str, payload: AiDocumentCreateInput):
        return documents.create_document(subject_id, payload.model_dump())

    @router.get("/api/documents/{document_id}", operation_id="getAiDocument", response_model=AiDocument, responses={404: {"model": ErrorResponse}})
    def get_ai_document(document_id: str):
        return documents.get_document(document_id)

    @router.get("/api/documents/{document_id}/versions", operation_id="listAiDocumentVersions", response_model=AiDocumentVersionList, responses={404: {"model": ErrorResponse}})
    def list_ai_document_versions(document_id: str):
        return {"items": documents.list_versions(document_id)}

    @router.post("/api/documents/{document_id}/versions/{version_id}/restore", operation_id="restoreAiDocumentVersion", response_model=AiDocument, responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
    def restore_ai_document_version(document_id: str, version_id: str):
        return documents.restore_version(document_id, version_id)

    @router.get("/api/documents/{document_id}/revision-proposals", operation_id="listAiDocumentRevisionProposals", response_model=AiDocumentRevisionProposalList, responses={404: {"model": ErrorResponse}})
    def list_ai_document_revision_proposals(document_id: str):
        return {"items": documents.list_proposals(document_id)}

    @router.post("/api/documents/{document_id}/revision-proposals", operation_id="createAiDocumentRevisionProposal", status_code=202, response_model=OperationAccepted, responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}})
    async def create_ai_document_revision_proposal(document_id: str, payload: AiDocumentRevisionInput):
        return documents.create_proposal(document_id, payload.model_dump())

    @router.get("/api/document-revision-proposals/{proposal_id}", operation_id="getAiDocumentRevisionProposal", response_model=AiDocumentRevisionProposal, responses={404: {"model": ErrorResponse}})
    def get_ai_document_revision_proposal(proposal_id: str):
        return documents.get_proposal(proposal_id)

    @router.post("/api/document-revision-proposals/{proposal_id}/apply", operation_id="applyAiDocumentRevisionProposal", response_model=AiDocument, responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
    def apply_ai_document_revision_proposal(proposal_id: str):
        return documents.apply_proposal(proposal_id)

    @router.post("/api/document-revision-proposals/{proposal_id}/discard", operation_id="discardAiDocumentRevisionProposal", status_code=204, responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
    def discard_ai_document_revision_proposal(proposal_id: str):
        documents.discard_proposal(proposal_id)
        return Response(status_code=204)

    return router
