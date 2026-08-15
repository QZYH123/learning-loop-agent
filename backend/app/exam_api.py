"""HTTP routes for blueprints, exam drafts, exams, and attempts."""
from __future__ import annotations

from fastapi import APIRouter, Response

from .api_models import ErrorResponse, OperationAccepted
from .exam_models import (
    Attempt,
    AttemptAnswer,
    AttemptAnswerInput,
    AttemptInput,
    AttemptPatch,
    AttemptReview,
    DraftQuestion,
    Exam,
    ExamBlueprint,
    ExamBlueprintList,
    ExamBlueprintPatch,
    ExamBlueprintPromptInput,
    ExamDraft,
    ExamDraftList,
    ExamDraftPatch,
    ExamDocumentReplaceInput,
    ExamList,
    ExamRevisionProposal,
    ExamRevisionProposalInput,
    ExamRevisionProposalList,
    ExamVersionList,
    FeedbackInput,
    PublishExamInput,
    QuestionInput,
)
from .learning import LearningError


def create_exam_router(exams) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/subjects/{subject_id}/exam-blueprints",
        operation_id="listExamBlueprints",
        response_model=ExamBlueprintList,
        responses={404: {"model": ErrorResponse}},
    )
    def list_blueprints(subject_id: str):
        return {"items": exams.list_blueprints(subject_id)}

    @router.post(
        "/api/subjects/{subject_id}/exam-blueprints",
        operation_id="parseExamBlueprint",
        status_code=202,
        response_model=OperationAccepted,
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def parse_blueprint(subject_id: str, payload: ExamBlueprintPromptInput):
        return exams.parse_blueprint(subject_id, payload.model_dump(exclude_none=True))

    @router.get(
        "/api/exam-blueprints/{blueprint_id}",
        operation_id="getExamBlueprint",
        response_model=ExamBlueprint,
        responses={404: {"model": ErrorResponse}},
    )
    def get_blueprint(blueprint_id: str):
        return exams.get_blueprint(blueprint_id)

    @router.patch(
        "/api/exam-blueprints/{blueprint_id}",
        operation_id="updateExamBlueprint",
        response_model=ExamBlueprint,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def update_blueprint(blueprint_id: str, payload: ExamBlueprintPatch):
        patch = payload.model_dump(exclude_unset=True)
        if not patch:
            raise LearningError(422, "VALIDATION_FAILED", "至少提供一项蓝图修改")
        return exams.update_blueprint(blueprint_id, patch)

    @router.delete(
        "/api/exam-blueprints/{blueprint_id}",
        operation_id="deleteExamBlueprint",
        status_code=204,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def delete_blueprint(blueprint_id: str):
        exams.delete_blueprint(blueprint_id)
        return Response(status_code=204)

    @router.post(
        "/api/exam-blueprints/{blueprint_id}/confirm",
        operation_id="confirmExamBlueprint",
        response_model=ExamBlueprint,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def confirm_blueprint(blueprint_id: str):
        return exams.confirm_blueprint(blueprint_id)

    @router.post(
        "/api/exam-blueprints/{blueprint_id}/generate",
        operation_id="generateExamDraft",
        status_code=202,
        response_model=OperationAccepted,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    async def generate_draft(blueprint_id: str):
        return exams.generate_draft(blueprint_id)

    @router.get(
        "/api/subjects/{subject_id}/exam-drafts",
        operation_id="listExamDrafts",
        response_model=ExamDraftList,
        responses={404: {"model": ErrorResponse}},
    )
    def list_drafts(subject_id: str):
        return {"items": exams.list_drafts(subject_id)}

    @router.get(
        "/api/exam-drafts/{draft_id}",
        operation_id="getExamDraft",
        response_model=ExamDraft,
        responses={404: {"model": ErrorResponse}},
    )
    def get_draft(draft_id: str):
        return exams.get_draft(draft_id)

    @router.patch(
        "/api/exam-drafts/{draft_id}",
        operation_id="updateExamDraft",
        response_model=ExamDraft,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def update_draft(draft_id: str, payload: ExamDraftPatch):
        patch = payload.model_dump(exclude_unset=True)
        if not patch:
            raise LearningError(422, "VALIDATION_FAILED", "至少提供一项草稿修改")
        return exams.update_draft(draft_id, patch)

    @router.delete(
        "/api/exam-drafts/{draft_id}",
        operation_id="deleteExamDraft",
        status_code=204,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def delete_draft(draft_id: str):
        exams.delete_draft(draft_id)
        return Response(status_code=204)

    @router.put(
        "/api/exam-drafts/{draft_id}/questions/{question_id}",
        operation_id="replaceDraftQuestion",
        response_model=DraftQuestion,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def replace_question(draft_id: str, question_id: str, payload: QuestionInput):
        return exams.replace_draft_question(draft_id, question_id, payload.model_dump())

    @router.delete(
        "/api/exam-drafts/{draft_id}/questions/{question_id}",
        operation_id="deleteDraftQuestion",
        status_code=204,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def delete_question(draft_id: str, question_id: str):
        exams.delete_draft_question(draft_id, question_id)
        return Response(status_code=204)

    @router.post(
        "/api/exam-drafts/{draft_id}/questions/{question_id}/retry",
        operation_id="retryDraftQuestion",
        status_code=202,
        response_model=OperationAccepted,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    async def retry_question(draft_id: str, question_id: str):
        return exams.retry_question(draft_id, question_id)

    @router.post(
        "/api/exam-drafts/{draft_id}/publish",
        operation_id="publishExamDraft",
        status_code=201,
        response_model=Exam,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def publish_draft(draft_id: str, payload: PublishExamInput | None = None):
        return exams.publish_draft(draft_id, payload.accept_needs_review if payload else False)

    @router.get(
        "/api/subjects/{subject_id}/exams",
        operation_id="listExams",
        response_model=ExamList,
        responses={404: {"model": ErrorResponse}},
    )
    def list_exams(subject_id: str):
        return {"items": exams.list_exams(subject_id)}

    @router.get(
        "/api/exams/{exam_id}",
        operation_id="getExam",
        response_model=Exam,
        responses={404: {"model": ErrorResponse}},
    )
    def get_exam(exam_id: str):
        return exams.get_exam(exam_id)

    @router.put(
        "/api/exams/{exam_id}",
        operation_id="replaceExamDocument",
        response_model=Exam,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def replace_exam(exam_id: str, payload: ExamDocumentReplaceInput):
        return exams.replace_exam_document(exam_id, payload.model_dump(exclude_none=True))

    @router.delete(
        "/api/exams/{exam_id}",
        operation_id="deleteExam",
        status_code=204,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def delete_exam(exam_id: str):
        exams.delete_exam(exam_id)
        return Response(status_code=204)

    @router.get(
        "/api/exams/{exam_id}/versions",
        operation_id="listExamVersions",
        response_model=ExamVersionList,
        responses={404: {"model": ErrorResponse}},
    )
    def list_exam_versions(exam_id: str):
        return {"items": exams.list_exam_versions(exam_id)}

    @router.post(
        "/api/exams/{exam_id}/versions/{version_id}/restore",
        operation_id="restoreExamVersion",
        response_model=Exam,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def restore_exam_version(exam_id: str, version_id: str):
        return exams.restore_exam_version(exam_id, version_id)

    @router.post(
        "/api/exams/{exam_id}/undo",
        operation_id="undoExamChange",
        response_model=Exam,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def undo_exam_change(exam_id: str):
        return exams.undo_exam_change(exam_id)

    @router.post(
        "/api/exams/{exam_id}/redo",
        operation_id="redoExamChange",
        response_model=Exam,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def redo_exam_change(exam_id: str):
        return exams.redo_exam_change(exam_id)

    @router.get(
        "/api/exams/{exam_id}/revision-proposals",
        operation_id="listExamRevisionProposals",
        response_model=ExamRevisionProposalList,
        responses={404: {"model": ErrorResponse}},
    )
    def list_revision_proposals(exam_id: str):
        return {"items": exams.list_revision_proposals(exam_id)}

    @router.post(
        "/api/exams/{exam_id}/revision-proposals",
        operation_id="createExamRevisionProposal",
        status_code=202,
        response_model=OperationAccepted,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def create_revision_proposal(exam_id: str, payload: ExamRevisionProposalInput):
        return exams.create_revision_proposal(exam_id, payload.model_dump(exclude_none=True))

    @router.get(
        "/api/revision-proposals/{proposal_id}",
        operation_id="getExamRevisionProposal",
        response_model=ExamRevisionProposal,
        responses={404: {"model": ErrorResponse}},
    )
    def get_revision_proposal(proposal_id: str):
        return exams.get_revision_proposal(proposal_id)

    @router.post(
        "/api/revision-proposals/{proposal_id}/apply",
        operation_id="applyExamRevisionProposal",
        response_model=Exam,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def apply_revision_proposal(proposal_id: str):
        return exams.apply_revision_proposal(proposal_id)

    @router.post(
        "/api/revision-proposals/{proposal_id}/discard",
        operation_id="discardExamRevisionProposal",
        status_code=204,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def discard_revision_proposal(proposal_id: str):
        exams.discard_revision_proposal(proposal_id)
        return Response(status_code=204)

    @router.post(
        "/api/exams/{exam_id}/attempts",
        operation_id="createAttempt",
        status_code=201,
        response_model=Attempt,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def create_attempt(exam_id: str, payload: AttemptInput):
        return exams.create_attempt(exam_id, payload.model_dump())

    @router.get(
        "/api/attempts/{attempt_id}",
        operation_id="getAttempt",
        response_model=Attempt,
        responses={404: {"model": ErrorResponse}},
    )
    def get_attempt(attempt_id: str):
        return exams.get_attempt(attempt_id)

    @router.patch(
        "/api/attempts/{attempt_id}",
        operation_id="updateAttempt",
        response_model=Attempt,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def update_attempt(attempt_id: str, payload: AttemptPatch):
        patch = payload.model_dump(exclude_unset=True)
        if not patch:
            raise LearningError(422, "VALIDATION_FAILED", "至少提供一项作答设置")
        return exams.update_attempt(attempt_id, patch)

    @router.put(
        "/api/attempts/{attempt_id}/answers/{question_id}",
        operation_id="saveAttemptAnswer",
        response_model=AttemptAnswer,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def save_answer(attempt_id: str, question_id: str, payload: AttemptAnswerInput):
        return exams.save_answer(attempt_id, question_id, payload.answer.model_dump())

    @router.post(
        "/api/attempts/{attempt_id}/answers/{question_id}/feedback",
        operation_id="requestQuestionFeedback",
        status_code=202,
        response_model=OperationAccepted,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    async def request_feedback(attempt_id: str, question_id: str, payload: FeedbackInput | None = None):
        return exams.request_feedback(attempt_id, question_id, payload.model_dump(exclude_none=True) if payload else {})

    @router.post(
        "/api/attempts/{attempt_id}/pause",
        operation_id="pauseAttempt",
        response_model=Attempt,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def pause_attempt(attempt_id: str):
        return exams.pause_attempt(attempt_id)

    @router.post(
        "/api/attempts/{attempt_id}/resume",
        operation_id="resumeAttempt",
        response_model=Attempt,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def resume_attempt(attempt_id: str):
        return exams.resume_attempt(attempt_id)

    @router.post(
        "/api/attempts/{attempt_id}/submit",
        operation_id="submitAttempt",
        status_code=202,
        response_model=OperationAccepted,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    async def submit_attempt(attempt_id: str):
        return exams.submit_attempt(attempt_id)

    @router.get(
        "/api/attempts/{attempt_id}/review",
        operation_id="getAttemptReview",
        response_model=AttemptReview,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def review_attempt(attempt_id: str):
        return exams.review_attempt(attempt_id)

    return router
