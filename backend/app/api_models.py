"""Pydantic response models for the static HTTP contract."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApiError(ContractModel):
    code: str
    message: str
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(ContractModel):
    ok: Literal[False] = False
    error: ApiError


class Health(ContractModel):
    status: Literal["ok"]


class ResourceRef(ContractModel):
    type: str
    id: str


class OperationProgress(ContractModel):
    completed: int
    total: int | None
    message: str | None


class Operation(ContractModel):
    id: str
    kind: str
    status: Literal["queued", "running", "succeeded", "failed", "canceling", "canceled"]
    cancelable: bool
    progress: OperationProgress
    subject_id: str | None
    resource: ResourceRef | None
    result: ResourceRef | None
    error: ApiError | None
    created_at: int
    updated_at: int
    started_at: int | None
    completed_at: int | None


class OperationAccepted(ContractModel):
    operation: Operation
    resource: ResourceRef | None


class SourceVersionSummary(ContractModel):
    id: str
    number: int
    status: Literal["processing", "ready", "failed", "unavailable"]
    content_hash: str
    mime_type: str
    size_bytes: int
    anchor_count: int
    cache_hit: bool
    created_at: int
    processed_at: int | None


class SourceAsset(ContractModel):
    id: str
    kind: Literal["image", "attachment"]
    mime_type: str
    width: int | None = None
    height: int | None = None
    alt: str | None = None


class SourceVersion(SourceVersionSummary):
    source_id: str
    assets: list[SourceAsset]
    failure: ApiError | None = None


class Source(ContractModel):
    id: str
    subject_id: str
    display_name: str
    media_kind: Literal["markdown", "text", "pdf", "docx", "pptx", "image"]
    status: Literal["processing", "ready", "failed", "unavailable"]
    current_version: SourceVersionSummary | None
    version_count: int
    failure: ApiError | None = None
    created_at: int
    updated_at: int


class SourceList(ContractModel):
    items: list[Source]


class SourceVersionList(ContractModel):
    items: list[SourceVersionSummary]


class SourceLocation(ContractModel):
    kind: Literal["section", "paragraph", "page", "table", "slide", "image"]
    label: str
    section_path: list[str] = Field(default_factory=list)
    page: int | None = None
    slide: int | None = None
    block_index: int | None = None
    asset_id: str | None = None


class AssetReference(ContractModel):
    source_version_id: str
    asset_id: str


class MarkdownBlock(ContractModel):
    id: str
    type: Literal["markdown"]
    text: str


class LatexBlock(ContractModel):
    id: str
    type: Literal["latex"]
    latex: str
    display: bool


class TableBlock(ContractModel):
    id: str
    type: Literal["table"]
    columns: list[str]
    rows: list[list[str]]


class ImageBlock(ContractModel):
    id: str
    type: Literal["image"]
    asset: AssetReference
    alt: str | None = None
    caption: str | None = None


ContentBlock = Annotated[
    MarkdownBlock | LatexBlock | TableBlock | ImageBlock,
    Field(discriminator="type"),
]


class SourceAnchor(ContractModel):
    id: str
    source_id: str
    source_version_id: str
    location: SourceLocation
    content: list[ContentBlock]
    available: bool


class Citation(ContractModel):
    id: str
    source_id: str
    source_version_id: str
    anchor_id: str
    source_name: str
    location: SourceLocation
    excerpt: str | None = None
    available: bool


class SubjectInput(ContractModel):
    name: str = Field(min_length=1, max_length=80)


class SubjectCounts(ContractModel):
    sources: int
    artifacts: int
    exam_blueprints: int
    exam_drafts: int
    exams: int


class Subject(ContractModel):
    id: str
    name: str
    active: bool
    counts: SubjectCounts
    created_at: int
    updated_at: int


class SubjectList(ContractModel):
    items: list[Subject]


class ModelCapabilitiesInput(ContractModel):
    text: Literal[True] = True
    vision: bool


class ModelCapabilities(ContractModel):
    text: bool
    vision: bool
    source: Literal["configured", "verified"]


class ModelValidation(ContractModel):
    status: Literal["unknown", "checking", "ok", "error"]
    checked_at: int | None
    message: str | None = None


class ModelServiceInput(ContractModel):
    provider: str = Field(min_length=1, max_length=60)
    model: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(default="", max_length=2000)
    capabilities: ModelCapabilitiesInput | None = None


class ModelServicePatch(ContractModel):
    provider: str | None = Field(default=None, min_length=1, max_length=60)
    model: str | None = Field(default=None, min_length=1, max_length=120)
    base_url: str | None = Field(default=None, min_length=1, max_length=500)
    api_key: str | None = Field(default=None, max_length=2000)
    capabilities: ModelCapabilitiesInput | None = None


class ModelService(ContractModel):
    id: str
    provider: str
    model: str
    base_url: str
    has_api_key: bool
    capabilities: ModelCapabilities
    validation: ModelValidation
    created_at: int
    updated_at: int


class ModelServiceList(ContractModel):
    items: list[ModelService]


class Workspace(ContractModel):
    schema_version: int
    active_subject_id: str | None
    subjects: list[Subject]
    models: list[ModelService]
    load_issue: str | None = None


class ChatConfigPatch(ContractModel):
    learning_mode: Literal["chat", "socratic", "crash-course"] | None = None
    goal: str | None = Field(default=None, max_length=2000)
    grounding_mode: Literal["strict", "general-knowledge", "supplemental"] | None = None
    source_version_ids: list[str] | None = None


class ChatModelInput(ContractModel):
    model_id: str


class SelectionContext(ContractModel):
    document_kind: Literal["exam-draft", "exam", "learning-artifact"]
    document_id: str
    version_id: str
    question_id: str | None = None
    block_id: str | None = None
    citation_ids: list[str] = Field(default_factory=list)
    selected_text: str | None = Field(default=None, min_length=1, max_length=20000)
    image_asset: AssetReference | None = None


ChatMessageIntent = Literal[
    "start",
    "ask",
    "attempt",
    "request-hint",
    "request-explanation",
    "restate",
    "request-self-test",
    "self-test-answer",
]


class ChatMessageInput(ContractModel):
    intent: ChatMessageIntent
    content: str | None = Field(default=None, min_length=1, max_length=20000)
    model_id: str | None = None
    source_version_ids: list[str] | None = None
    grounding_mode: Literal["strict", "general-knowledge", "supplemental"] | None = None
    selection: SelectionContext | None = None


class ModelSnapshot(ContractModel):
    model_id: str
    provider: str
    model: str
    base_url: str
    capabilities: ModelCapabilities


class ChatMessage(ContractModel):
    id: str
    role: Literal["user", "assistant", "system"]
    intent: ChatMessageIntent
    content: list[ContentBlock]
    status: Literal["queued", "generating", "complete", "stopped", "error"]
    grounding_mode: Literal["strict", "general-knowledge", "supplemental"] | None = None
    grounding_result: Literal["covered", "not-covered", "general-knowledge", "supplemental"] | None = None
    citations: list[Citation]
    selection: SelectionContext | None = None
    model: ModelSnapshot | None = None
    error: ApiError | None = None
    created_at: int
    updated_at: int
    completed_at: int | None = None


class SocraticState(ContractModel):
    stage: Literal["awaiting-attempt", "hinting", "correcting", "awaiting-restate", "self-testing", "completed"]
    hint_level: int
    answer_revealed: bool


class Chat(ContractModel):
    id: str
    subject_id: str
    learning_mode: Literal["chat", "socratic", "crash-course"]
    goal: str | None = None
    grounding_mode: Literal["strict", "general-knowledge", "supplemental"]
    source_version_ids: list[str]
    active_model_id: str | None
    socratic_state: SocraticState | None = None
    messages: list[ChatMessage]
    artifact_ids: list[str] = Field(default_factory=list)
    created_at: int
    updated_at: int


class CrashCourseInput(ContractModel):
    goal: str = Field(min_length=1, max_length=2000)
    source_version_ids: list[str] = Field(min_length=1)
    grounding_mode: Literal["strict", "general-knowledge", "supplemental"]
    model_id: str | None = None


class SelfTest(ContractModel):
    prompt: list[ContentBlock]
    answer: list[ContentBlock]


class KnowledgePoint(ContractModel):
    id: str
    title: str
    explanation: list[ContentBlock]
    key_points: list[str]
    citations: list[Citation]
    self_test: SelfTest


class LearningArtifact(ContractModel):
    id: str
    subject_id: str
    type: Literal["crash-course-outline", "note", "chapter-outline", "review-material"]
    title: str
    chat_id: str
    source_version_ids: list[str]
    grounding_mode: Literal["strict", "general-knowledge", "supplemental"]
    knowledge_points: list[KnowledgePoint]
    created_at: int
    updated_at: int


class LearningArtifactList(ContractModel):
    items: list[LearningArtifact]
