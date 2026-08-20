"""Pydantic models for blueprint, exam, and attempt contract resources."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, field_validator, model_serializer, model_validator

from .api_models import (
    ApiError,
    Citation,
    ContentBlock,
    ContractModel,
    ModelSnapshot,
    PatchModel,
    SelectionContext,
)

QuestionType = Literal[
    "single-choice",
    "multiple-choice",
    "fill-blank",
    "true-false",
    "short-answer",
    "argumentation",
    "extended-response",
]
GroundingMode = Literal["strict", "general-knowledge", "supplemental"]


class BlueprintQuestionPlan(ContractModel):
    type: QuestionType
    count: int = Field(ge=1)
    difficulty: Literal["easy", "medium", "hard"]
    score_each: float = Field(gt=0)


class BlueprintIssue(ContractModel):
    code: str
    severity: Literal["warning", "error"]
    path: str
    message: str


class ExamBlueprintPromptInput(ContractModel):
    prompt: str = Field(min_length=1, max_length=10000)
    grounding_mode: GroundingMode
    source_version_ids: list[str] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    model_id: str | None = None
    use_defaults: bool = False

    @field_validator("source_version_ids")
    @classmethod
    def source_versions_must_be_unique(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("source_version_ids must contain unique items")
        return value


class ExamBlueprintPatch(PatchModel):
    title: str = Field(default=None, min_length=1, max_length=200)
    syllabus: list[str] = None
    source_version_ids: list[str] = Field(default=None, json_schema_extra={"uniqueItems": True})
    grounding_mode: GroundingMode = None
    question_plan: list[BlueprintQuestionPlan] = Field(default=None, min_length=1)
    total_score: float = Field(default=None, gt=0)
    duration_minutes: int | None = Field(default=None, ge=1)

    @field_validator("source_version_ids")
    @classmethod
    def source_versions_must_be_unique(cls, value):
        if value is not None and len(value) != len(set(value)):
            raise ValueError("source_version_ids must contain unique items")
        return value

    @field_validator("syllabus")
    @classmethod
    def syllabus_items_must_not_be_empty(cls, value):
        if value is not None and any(not item for item in value):
            raise ValueError("syllabus items must not be empty")
        return value


class ExamBlueprint(ContractModel):
    id: str
    subject_id: str
    prompt: str
    title: str
    status: Literal["parsing", "draft", "confirmed", "failed"]
    syllabus: list[str]
    source_version_ids: list[str]
    grounding_mode: GroundingMode
    question_plan: list[BlueprintQuestionPlan]
    total_score: float = Field(gt=0)
    duration_minutes: int | None = None
    issues: list[BlueprintIssue]
    confirmed_at: int | None = None
    created_at: int
    updated_at: int


class ExamBlueprintList(ContractModel):
    items: list[ExamBlueprint]


class AnswerArea(ContractModel):
    lines: int = Field(ge=0, le=100)


class QuestionEvidence(ContractModel):
    basis: GroundingMode
    citations: list[Citation]
    status: Literal["complete", "needs-review"]
    note: str | None = None


class ChoiceOption(ContractModel):
    id: str
    content: list[ContentBlock] = Field(min_length=1)


class ChoiceAnswerKey(ContractModel):
    kind: Literal["choice"]
    option_ids: list[str] = Field(min_length=1, json_schema_extra={"uniqueItems": True})

    @field_validator("option_ids")
    @classmethod
    def option_ids_must_be_unique(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("option_ids must contain unique items")
        return value


class BlankNormalization(ContractModel):
    trim: bool
    case_sensitive: bool
    collapse_whitespace: bool


class FillBlankDefinition(ContractModel):
    id: str
    acceptable_answers: list[str] = Field(min_length=1)
    normalization: BlankNormalization


class FillBlankAnswerKey(ContractModel):
    kind: Literal["fill-blank"]
    blanks: list[FillBlankDefinition] = Field(min_length=1)


class TrueFalseAnswerKey(ContractModel):
    kind: Literal["true-false"]
    value: bool


class ScoringPoint(ContractModel):
    id: str
    description: str = Field(min_length=1)
    score: float = Field(ge=0)


class SubjectiveAnswerKey(ContractModel):
    kind: Literal["subjective"]
    reference_answer: list[ContentBlock] = Field(min_length=1)
    scoring_points: list[ScoringPoint] = Field(min_length=1)


AnswerKey = Annotated[
    ChoiceAnswerKey | FillBlankAnswerKey | TrueFalseAnswerKey | SubjectiveAnswerKey,
    Field(discriminator="kind"),
]


class QuestionInput(ContractModel):
    id: str
    type: QuestionType
    stem: list[ContentBlock] = Field(min_length=1)
    options: list[ChoiceOption] = Field(default_factory=list, json_schema_extra={"minItems": 2})
    score: float = Field(gt=0)
    answer_area: AnswerArea
    answer: AnswerKey
    explanation: list[ContentBlock] = Field(min_length=1)
    knowledge_points: list[str] = Field(min_length=1)
    evidence: QuestionEvidence
    reliability: Literal["reliable", "needs-review"]

    @field_validator("knowledge_points")
    @classmethod
    def knowledge_points_must_not_be_empty(cls, value):
        if any(not item for item in value):
            raise ValueError("knowledge_points items must not be empty")
        return value

    @model_validator(mode="after")
    def validate_question_structure(self):
        expected_kind = (
            "choice" if self.type in {"single-choice", "multiple-choice"}
            else "fill-blank" if self.type == "fill-blank"
            else "true-false" if self.type == "true-false"
            else "subjective"
        )
        if self.answer.kind != expected_kind:
            raise ValueError("question type and answer kind do not match")
        if expected_kind == "choice":
            if len(self.options) < 2:
                raise ValueError("choice questions require at least two options")
            option_ids = [item.id for item in self.options]
            if len(option_ids) != len(set(option_ids)):
                raise ValueError("choice option ids must contain unique items")
            if not set(self.answer.option_ids) <= set(option_ids):
                raise ValueError("choice answer references an unknown option")
            if self.type == "single-choice" and len(self.answer.option_ids) != 1:
                raise ValueError("single-choice questions require exactly one answer option")
        elif expected_kind == "fill-blank":
            blank_ids = [item.id for item in self.answer.blanks]
            if len(blank_ids) != len(set(blank_ids)):
                raise ValueError("fill-blank ids must contain unique items")
        elif expected_kind == "subjective":
            point_ids = [item.id for item in self.answer.scoring_points]
            if len(point_ids) != len(set(point_ids)):
                raise ValueError("scoring point ids must contain unique items")
        return self

    @model_serializer(mode="wrap")
    def serialize_question(self, handler):
        data = handler(self)
        if self.type not in {"single-choice", "multiple-choice"}:
            data.pop("options", None)
        return data


class DraftQuestion(ContractModel):
    id: str
    ordinal: int = Field(ge=1)
    planned_type: QuestionType
    status: Literal["queued", "generating", "complete", "failed", "needs-review"]
    question: QuestionInput | None
    error: ApiError | None
    updated_at: int


class ExamDraftPatch(PatchModel):
    title: str = Field(default=None, min_length=1, max_length=200)
    instructions: list[ContentBlock] = None
    question_order: list[str] = Field(default=None, min_length=1, json_schema_extra={"uniqueItems": True})

    @field_validator("question_order")
    @classmethod
    def question_order_must_be_unique(cls, value):
        if value is not None and len(value) != len(set(value)):
            raise ValueError("question_order must contain unique items")
        return value


class ExamDraft(ContractModel):
    id: str
    subject_id: str
    blueprint_id: str
    title: str
    instructions: list[ContentBlock]
    status: Literal["generating", "editable", "failed", "published"]
    questions: list[DraftQuestion]
    total_score: float = Field(ge=0)
    created_at: int
    updated_at: int


class ExamDraftList(ContractModel):
    items: list[ExamDraft]


class PublishExamInput(ContractModel):
    accept_needs_review: bool = False


class ExamDocument(ContractModel):
    title: str = Field(min_length=1, max_length=200)
    instructions: list[ContentBlock]
    questions: list[QuestionInput] = Field(min_length=1)


class Exam(ContractModel):
    id: str
    subject_id: str
    source_blueprint_id: str | None
    current_version_id: str
    document: ExamDocument
    total_score: float = Field(ge=0)
    can_undo: bool
    can_redo: bool
    created_at: int
    updated_at: int


class ExamList(ContractModel):
    items: list[Exam]


class ExamPatch(PatchModel):
    title: str = Field(default=None, min_length=1, max_length=200)


class ExamDocumentReplaceInput(ContractModel):
    base_version_id: str
    document: ExamDocument
    summary: str = Field(default=None, max_length=500)


class ExamVersion(ContractModel):
    id: str
    exam_id: str
    number: int = Field(ge=1)
    actor: Literal["user", "ai", "restore", "undo", "redo"]
    summary: str = Field(min_length=1)
    model: ModelSnapshot | None = None
    created_at: int


class ExamVersionList(ContractModel):
    items: list[ExamVersion]


class AttemptInput(ContractModel):
    mode: Literal["exam", "practice"]
    show_suggested_score: bool = False


class AttemptPatch(PatchModel):
    mode: Literal["exam", "practice"] = None
    show_suggested_score: bool = None


class AttemptQuestion(ContractModel):
    id: str
    ordinal: int = Field(ge=1)
    type: QuestionType
    stem: list[ContentBlock]
    options: list[ChoiceOption] = Field(default_factory=list)
    score: float = Field(gt=0)
    answer_area: AnswerArea


class AttemptPaper(ContractModel):
    exam_id: str
    exam_version_id: str
    title: str
    instructions: list[ContentBlock]
    questions: list[AttemptQuestion]
    total_score: float = Field(ge=0)


class ChoiceAnswerInput(ContractModel):
    kind: Literal["choice"]
    option_ids: list[str] = Field(json_schema_extra={"uniqueItems": True})

    @field_validator("option_ids")
    @classmethod
    def option_ids_must_be_unique(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("option_ids must contain unique items")
        return value


class BlankAnswer(ContractModel):
    blank_id: str
    value: str


class FillBlankAnswerInput(ContractModel):
    kind: Literal["fill-blank"]
    blanks: list[BlankAnswer]

    @field_validator("blanks")
    @classmethod
    def blank_ids_must_be_unique(cls, value):
        ids = [item.blank_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("blank_id values must contain unique items")
        return value


class TrueFalseAnswerInput(ContractModel):
    kind: Literal["true-false"]
    value: bool


class TextAnswerInput(ContractModel):
    kind: Literal["text"]
    text: str = Field(max_length=50000)


AttemptAnswerValue = Annotated[
    ChoiceAnswerInput | FillBlankAnswerInput | TrueFalseAnswerInput | TextAnswerInput,
    Field(discriminator="kind"),
]


class AttemptAnswerInput(ContractModel):
    answer: AttemptAnswerValue


class AttemptAnswer(ContractModel):
    id: str
    attempt_id: str
    question_id: str
    answer: AttemptAnswerValue
    saved_at: int


class FeedbackInput(ContractModel):
    model_id: str | None = None
    show_suggested_score: bool = None


class QuestionFeedback(ContractModel):
    id: str
    attempt_id: str
    question_id: str
    answer_snapshot: AttemptAnswerValue
    status: Literal["complete", "needs-review", "unable-to-assess"]
    correct: bool | None = None
    matched_points: list[ScoringPoint]
    missed_points: list[ScoringPoint]
    reasoning_issues: list[str]
    suggestions: list[str]
    suggested_score: float | None = Field(ge=0)
    reference_answer: list[ContentBlock] = Field(default_factory=list)
    evidence: QuestionEvidence
    model: ModelSnapshot | None
    created_at: int


class Attempt(ContractModel):
    id: str
    exam_id: str
    exam_version_id: str
    mode: Literal["exam", "practice"]
    status: Literal["in-progress", "paused", "grading", "submitted"]
    completion_status: Literal["in-progress", "completed"]
    grading_status: Literal["not-requested", "queued", "grading", "completed", "failed", "stale"]
    unanswered_question_ids: list[str] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    show_suggested_score: bool
    paper: AttemptPaper
    answers: list[AttemptAnswer]
    feedback: list[QuestionFeedback]
    elapsed_ms: int = Field(ge=0)
    timing_started_at: int | None
    created_at: int
    updated_at: int
    submitted_at: int | None = None
    completed_at: int | None = None
    grading_error: ApiError | None = None


class AttemptReviewItem(ContractModel):
    question: QuestionInput
    answer: AttemptAnswer | None
    feedback: QuestionFeedback | None


class AttemptReview(ContractModel):
    attempt_id: str
    mode: Literal["exam", "practice"]
    status: Literal["in-progress", "paused", "grading", "submitted"]
    items: list[AttemptReviewItem]
    total_suggested_score: float | None = Field(ge=0)


class RevisionScope(ContractModel):
    kind: Literal["whole-exam", "questions", "blocks"]
    question_ids: list[str] = Field(json_schema_extra={"uniqueItems": True})
    block_ids: list[str] = Field(json_schema_extra={"uniqueItems": True})

    @field_validator("question_ids", "block_ids")
    @classmethod
    def ids_must_be_unique(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("scope ids must contain unique items")
        return value


class ExamRevisionProposalInput(ContractModel):
    base_version_id: str
    instruction: str = Field(min_length=1, max_length=10000)
    scope: RevisionScope
    selection: SelectionContext = None
    model_id: str | None = None


class DraftRevisionProposalInput(ContractModel):
    instruction: str = Field(min_length=1, max_length=10000)
    scope: RevisionScope | None = None
    model_id: str | None = None


class ExamChange(ContractModel):
    path: str = Field(min_length=1)
    operation: Literal["add", "replace", "remove", "move"]
    summary: str = Field(min_length=1)
    before: Any
    after: Any


class ExamRevisionProposal(ContractModel):
    id: str
    exam_id: str
    base_version_id: str
    instruction: str
    scope: RevisionScope
    status: Literal["generating", "ready", "applied", "discarded", "failed"]
    changes: list[ExamChange]
    model: ModelSnapshot | None = None
    error: ApiError | None = None
    created_at: int
    updated_at: int


class ExamRevisionProposalList(ContractModel):
    items: list[ExamRevisionProposal]


class DraftRevisionProposal(ContractModel):
    id: str
    draft_id: str
    instruction: str
    scope: RevisionScope
    status: Literal["generating", "ready", "applied", "discarded", "failed"]
    changes: list[ExamChange]
    model: ModelSnapshot | None = None
    error: ApiError | None = None
    created_at: int
    updated_at: int


class DraftRevisionProposalList(ContractModel):
    items: list[DraftRevisionProposal]


ExamEdition = Literal["questions", "solutions"]


class QuestionSolution(ContractModel):
    answer: AnswerKey
    explanation: list[ContentBlock]
    knowledge_points: list[str]
    evidence: QuestionEvidence
    reliability: Literal["reliable", "needs-review"]


class RenderQuestion(ContractModel):
    question: AttemptQuestion
    solution: QuestionSolution | None


class PageMargins(ContractModel):
    top: float = Field(ge=0)
    right: float = Field(ge=0)
    bottom: float = Field(ge=0)
    left: float = Field(ge=0)


class ExamRenderLayout(ContractModel):
    paper_size: Literal["A4", "Letter"]
    margins_mm: PageMargins


class ExamRenderDocument(ContractModel):
    exam_id: str
    exam_version_id: str
    edition: ExamEdition
    title: str
    instructions: list[ContentBlock]
    questions: list[RenderQuestion]
    total_score: float
    layout: ExamRenderLayout


class ExamExportInput(ContractModel):
    format: Literal["pdf", "markdown"]
    edition: ExamEdition
    attempt_id: str | None = None


class ExamExport(ContractModel):
    id: str
    exam_id: str
    exam_version_id: str
    format: Literal["pdf", "markdown"]
    edition: ExamEdition
    status: Literal["queued", "rendering", "ready", "failed"]
    file_name: str
    mime_type: Literal["application/pdf", "text/markdown"]
    size_bytes: int | None = None
    download_url: str | None = None
    failure: ApiError | None = None
    created_at: int
    updated_at: int
