"""Pydantic models for blueprint, exam, and attempt contract resources."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from .api_models import (
    ApiError,
    Citation,
    ContentBlock,
    ContractModel,
    ModelSnapshot,
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
    source_version_ids: list[str] = Field(default_factory=list)
    model_id: str | None = None


class ExamBlueprintPatch(ContractModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    syllabus: list[str] | None = None
    source_version_ids: list[str] | None = None
    grounding_mode: GroundingMode | None = None
    question_plan: list[BlueprintQuestionPlan] | None = None
    total_score: float | None = Field(default=None, gt=0)
    duration_minutes: int | None = Field(default=None, ge=1)


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
    total_score: float
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
    option_ids: list[str] = Field(min_length=1)


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
    options: list[ChoiceOption] = Field(default_factory=list)
    score: float = Field(gt=0)
    answer_area: AnswerArea
    answer: AnswerKey
    explanation: list[ContentBlock] = Field(min_length=1)
    knowledge_points: list[str] = Field(min_length=1)
    evidence: QuestionEvidence
    reliability: Literal["reliable", "needs-review"]


class DraftQuestion(ContractModel):
    id: str
    ordinal: int = Field(ge=1)
    planned_type: QuestionType
    status: Literal["queued", "generating", "complete", "failed", "needs-review"]
    question: QuestionInput | None
    error: ApiError | None
    updated_at: int


class ExamDraftPatch(ContractModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    instructions: list[ContentBlock] | None = None
    question_order: list[str] | None = None


class ExamDraft(ContractModel):
    id: str
    subject_id: str
    blueprint_id: str
    title: str
    instructions: list[ContentBlock]
    status: Literal["generating", "editable", "failed", "published"]
    questions: list[DraftQuestion]
    total_score: float
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
    total_score: float
    can_undo: bool
    can_redo: bool
    created_at: int
    updated_at: int


class ExamList(ContractModel):
    items: list[Exam]


class AttemptInput(ContractModel):
    mode: Literal["exam", "practice"]
    show_suggested_score: bool = False


class AttemptPatch(ContractModel):
    mode: Literal["exam", "practice"] | None = None
    show_suggested_score: bool | None = None


class AttemptQuestion(ContractModel):
    id: str
    ordinal: int
    type: QuestionType
    stem: list[ContentBlock]
    options: list[ChoiceOption] = Field(default_factory=list)
    score: float
    answer_area: AnswerArea


class AttemptPaper(ContractModel):
    exam_id: str
    exam_version_id: str
    title: str
    instructions: list[ContentBlock]
    questions: list[AttemptQuestion]
    total_score: float


class ChoiceAnswerInput(ContractModel):
    kind: Literal["choice"]
    option_ids: list[str]


class BlankAnswer(ContractModel):
    blank_id: str
    value: str


class FillBlankAnswerInput(ContractModel):
    kind: Literal["fill-blank"]
    blanks: list[BlankAnswer]


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
    show_suggested_score: bool | None = None


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
    suggested_score: float | None
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
    show_suggested_score: bool
    paper: AttemptPaper
    answers: list[AttemptAnswer]
    feedback: list[QuestionFeedback]
    created_at: int
    updated_at: int
    submitted_at: int | None = None


class AttemptReviewItem(ContractModel):
    question: QuestionInput
    answer: AttemptAnswer | None
    feedback: QuestionFeedback | None


class AttemptReview(ContractModel):
    attempt_id: str
    mode: Literal["exam", "practice"]
    status: Literal["in-progress", "paused", "grading", "submitted"]
    items: list[AttemptReviewItem]
    total_suggested_score: float | None


class RevisionScope(ContractModel):
    kind: Literal["whole-exam", "questions", "blocks"]
    question_ids: list[str]
    block_ids: list[str]


class ExamRevisionProposalInput(ContractModel):
    base_version_id: str
    instruction: str = Field(min_length=1, max_length=10000)
    scope: RevisionScope
    selection: SelectionContext | None = None
    model_id: str | None = None


class ExamChange(ContractModel):
    path: str
    operation: Literal["add", "replace", "remove", "move"]
    summary: str
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
