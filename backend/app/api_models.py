"""Pydantic response models for the static HTTP contract."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PatchModel(ContractModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"minProperties": 1})

    @model_validator(mode="before")
    @classmethod
    def require_at_least_one_field(cls, value):
        if isinstance(value, dict) and not value:
            raise ValueError("at least one field is required")
        return value


ErrorCode = Literal[
    "VALIDATION_FAILED",
    "RESOURCE_NOT_FOUND",
    "RESOURCE_CONFLICT",
    "STORAGE_WRITE_FAILED",
    "INTERNAL_ERROR",
    "SUBJECT_NAME_DUPLICATE",
    "SUBJECT_DELETE_BLOCKED",
    "MODEL_SERVICE_DUPLICATE",
    "MODEL_CAPABILITY_UNSUPPORTED",
    "MODEL_VERIFICATION_FAILED",
    "MODEL_CONNECTION_FAILED",
    "MODEL_HTTP_ERROR",
    "MODEL_INVALID_RESPONSE",
    "SOURCE_TYPE_UNSUPPORTED",
    "SOURCE_TOO_LARGE",
    "SOURCE_PROCESSING_FAILED",
    "SOURCE_UNAVAILABLE",
    "SOURCE_VERSION_MISMATCH",
    "CHAT_GENERATION_IN_PROGRESS",
    "CHAT_MODEL_NOT_SELECTED",
    "CHAT_SELECTION_INVALID",
    "GROUNDING_SOURCE_REQUIRED",
    "IMAGE_INPUT_UNSUPPORTED",
    "BLUEPRINT_CONSTRAINT_CONFLICT",
    "BLUEPRINT_NOT_CONFIRMED",
    "QUESTION_STRUCTURE_INVALID",
    "QUESTION_EVIDENCE_INCOMPLETE",
    "QUESTION_GENERATION_FAILED",
    "EXAM_VERSION_CONFLICT",
    "REVISION_PROPOSAL_INVALID",
    "REVISION_PROPOSAL_STALE",
    "ATTEMPT_STATE_CONFLICT",
    "ANSWER_TYPE_MISMATCH",
    "ANSWER_NOT_AVAILABLE",
    "FEEDBACK_UNAVAILABLE",
    "EXPORT_ANSWER_NOT_ALLOWED",
    "EXPORT_NOT_READY",
    "OPERATION_IN_PROGRESS",
    "OPERATION_NOT_CANCELABLE",
    "EVALUATION_ALREADY_RUNNING",
    "SESSION_NAME_DUPLICATE",
    "SESSION_NOT_FOUND",
    "SESSION_SOURCE_CONFLICT",
    "ATTACHMENT_NOT_FOUND",
    "ATTACHMENT_EXPIRED",
    "MODEL_DISCOVERY_UNSUPPORTED",
    "MODEL_DISCOVERY_FAILED",
    "MODEL_MANUAL_NAME_REQUIRED",
    "AI_DOCUMENT_READ_ONLY",
    "AI_DOCUMENT_VERSION_CONFLICT",
    "AI_DOCUMENT_PROPOSAL_INVALID",
    "ATTEMPT_ALREADY_COMPLETED",
    "ATTEMPT_NOT_COMPLETED",
    "GRADING_ALREADY_REQUESTED",
    "GRADING_STALE",
]

ResourceType = Literal[
    "model",
    "source",
    "source-version",
    "chat-message",
    "learning-artifact",
    "exam-blueprint",
    "exam-draft",
    "question",
    "exam",
    "attempt",
    "feedback",
    "revision-proposal",
    "export",
    "evaluation-run",
    "session",
    "attachment",
    "ai-document",
    "ai-document-version",
    "ai-document-proposal",
]

OperationKind = Literal[
    "model-verification",
    "source-parsing",
    "chat-generation",
    "crash-course-generation",
    "blueprint-parsing",
    "exam-generation",
    "question-retry",
    "subjective-feedback",
    "attempt-grading",
    "exam-revision",
    "ai-document-generation",
    "ai-document-revision",
    "exam-export",
    "evaluation",
]


class ApiError(ContractModel):
    code: ErrorCode
    message: str = Field(min_length=1)
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(ContractModel):
    ok: Literal[False]
    error: ApiError


class Health(ContractModel):
    status: Literal["ok"]


class ResourceRef(ContractModel):
    type: ResourceType
    id: str


class OperationProgress(ContractModel):
    completed: int = Field(ge=0)
    total: int | None = Field(ge=0)
    message: str | None


class Operation(ContractModel):
    id: str
    kind: OperationKind
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
    number: int = Field(ge=1)
    status: Literal["processing", "ready", "failed", "unavailable"]
    content_hash: str
    mime_type: str
    size_bytes: int = Field(ge=0)
    anchor_count: int = Field(ge=0)
    cache_hit: bool
    created_at: int
    processed_at: int | None


class SourceAsset(ContractModel):
    id: str
    kind: Literal["image", "attachment"]
    mime_type: str
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
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
    version_count: int = Field(ge=0)
    failure: ApiError | None = None
    created_at: int
    updated_at: int


class SourceList(ContractModel):
    items: list[Source]


class SourceVersionList(ContractModel):
    items: list[SourceVersionSummary]


class SourceLocation(ContractModel):
    kind: Literal["section", "paragraph", "page", "table", "slide", "image"]
    label: str = Field(min_length=1)
    section_path: list[str] = Field(default_factory=list)
    page: int | None = Field(default=None, ge=1)
    slide: int | None = Field(default=None, ge=1)
    block_index: int | None = Field(default=None, ge=0)
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


class SourceAnchorList(ContractModel):
    items: list[SourceAnchor]


class Citation(ContractModel):
    id: str
    source_id: str
    source_version_id: str
    anchor_id: str
    source_name: str
    location: SourceLocation
    excerpt: str | None = Field(default=None, max_length=1000)
    available: bool


class SubjectInput(ContractModel):
    name: str = Field(min_length=1, max_length=80)


class SubjectCounts(ContractModel):
    sources: int = Field(ge=0)
    artifacts: int = Field(ge=0)
    exam_blueprints: int = Field(ge=0)
    exam_drafts: int = Field(ge=0)
    exams: int = Field(ge=0)


class Subject(ContractModel):
    id: str
    name: str = Field(min_length=1, max_length=80)
    active: bool
    counts: SubjectCounts
    created_at: int
    updated_at: int


class SubjectList(ContractModel):
    items: list[Subject]


class ModelCapabilitiesInput(ContractModel):
    text: Literal[True]
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
    capabilities: ModelCapabilitiesInput = None


class ModelServicePatch(PatchModel):
    provider: str = Field(default=None, min_length=1, max_length=60)
    model: str = Field(default=None, min_length=1, max_length=120)
    base_url: str = Field(default=None, min_length=1, max_length=500)
    api_key: str | None = Field(default=None, max_length=2000)
    capabilities: ModelCapabilitiesInput = None


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
    schema_version: int = Field(ge=1)
    active_subject_id: str | None
    subjects: list[Subject]
    models: list[ModelService]
    load_issue: str | None = None


class ChatConfigPatch(PatchModel):
    learning_mode: Literal["chat", "socratic", "crash-course"] = None
    goal: str | None = Field(default=None, max_length=2000)
    grounding_mode: Literal["strict", "general-knowledge", "supplemental"] = None
    source_version_ids: list[str] = Field(default=None, json_schema_extra={"uniqueItems": True})

    @field_validator("source_version_ids")
    @classmethod
    def source_versions_must_be_unique(cls, value):
        if value is not None and len(value) != len(set(value)):
            raise ValueError("source_version_ids must contain unique items")
        return value


class ChatModelInput(ContractModel):
    model_id: str


class SelectionContext(ContractModel):
    document_kind: Literal["exam-draft", "exam", "learning-artifact"]
    document_id: str
    version_id: str
    question_id: str | None = None
    block_id: str | None = None
    citation_ids: list[str] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    selected_text: str = Field(default=None, min_length=1, max_length=20000)
    image_asset: AssetReference = None

    @field_validator("citation_ids")
    @classmethod
    def citations_must_be_unique(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("citation_ids must contain unique items")
        return value

    @model_validator(mode="after")
    def require_exactly_one_selection(self):
        if (self.selected_text is None) == (self.image_asset is None):
            raise ValueError("exactly one of selected_text and image_asset is required")
        return self


class MessageSourceContext(ContractModel):
    source_version_ids: list[str] = Field(json_schema_extra={"uniqueItems": True})
    focused_source_version_ids: list[str] = Field(json_schema_extra={"uniqueItems": True})
    only_use_specified_sources: bool
    grounding_mode: Literal["strict", "general-knowledge", "supplemental"]
    selection: SelectionContext | None = None
    attachment_ids: list[str] = Field(json_schema_extra={"uniqueItems": True})
    citations: list[Citation]

    @field_validator("source_version_ids", "focused_source_version_ids", "attachment_ids")
    @classmethod
    def context_ids_must_be_unique(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("context id lists must contain unique items")
        return value


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
    content: str = Field(default=None, min_length=1, max_length=20000)
    model_id: str | None = None
    source_version_ids: list[str] = Field(default=None, json_schema_extra={"uniqueItems": True})
    grounding_mode: Literal["strict", "general-knowledge", "supplemental"] = None
    selection: SelectionContext = None
    focused_source_version_ids: list[str] = Field(default=None, json_schema_extra={"uniqueItems": True})
    only_use_specified_sources: bool = False
    attachment_ids: list[str] = Field(default=None, json_schema_extra={"uniqueItems": True})

    @field_validator("source_version_ids", "focused_source_version_ids", "attachment_ids")
    @classmethod
    def context_ids_must_be_unique(cls, value):
        if value is not None and len(value) != len(set(value)):
            raise ValueError("context id lists must contain unique items")
        return value

    @model_validator(mode="after")
    def require_content_for_text_intents(self):
        if self.intent in {"ask", "attempt", "restate", "self-test-answer"} and self.content is None:
            raise ValueError(f"content is required for intent {self.intent}")
        return self


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
    source_context: MessageSourceContext
    selection: SelectionContext | None = None
    model: ModelSnapshot | None = None
    error: ApiError | None = None
    created_at: int
    updated_at: int
    completed_at: int | None = None


class SocraticState(ContractModel):
    stage: Literal["awaiting-attempt", "hinting", "correcting", "awaiting-restate", "self-testing", "completed"]
    hint_level: int = Field(ge=0, le=3)
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


class SessionInput(ContractModel):
    title: str = Field(default=None, min_length=1, max_length=200)
    source_version_ids: list[str] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )

    @field_validator("source_version_ids")
    @classmethod
    def source_versions_must_be_unique(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("source_version_ids must contain unique items")
        return value


class SessionPatch(PatchModel):
    title: str = Field(default=None, min_length=1, max_length=200)


class Session(ContractModel):
    id: str
    subject_id: str
    title: str
    active: bool
    source_version_ids: list[str] = Field(json_schema_extra={"uniqueItems": True})
    messages: list[ChatMessage]
    created_at: int
    updated_at: int


class SessionList(ContractModel):
    items: list[Session]
    active_session_id: str | None


class SessionSource(ContractModel):
    source_version_id: str
    source_id: str
    source_name: str
    version_number: int = Field(ge=1)
    status: Literal["processing", "ready", "failed", "unavailable"]
    added_at: int


class SessionSourceList(ContractModel):
    items: list[SessionSource]


class SessionSourceInput(ContractModel):
    source_version_id: str


class SessionSourcePatch(ContractModel):
    source_version_id: str


class TempAttachment(ContractModel):
    id: str
    subject_id: str
    file_name: str
    mime_type: str
    size_bytes: int = Field(ge=0)
    status: Literal["ready", "failed", "expired"]
    vision_required: bool
    failure: ApiError | None = None
    created_at: int
    expires_at: int


class ModelDiscoveryInput(ContractModel):
    provider: Literal["openai-compatible", "ollama"]
    base_url: AnyHttpUrl = Field(max_length=500)
    api_key: str = Field(default="", max_length=2000, json_schema_extra={"writeOnly": True})
    manual_model_name: str | None = Field(default=None, max_length=120)


class DiscoveredModelCapabilities(ContractModel):
    text: bool
    vision: bool


class DiscoveredModel(ContractModel):
    name: str
    capabilities: DiscoveredModelCapabilities


class ModelDiscoveryResponse(ContractModel):
    provider: Literal["openai-compatible", "ollama"]
    models: list[DiscoveredModel]
    manual_model_allowed: bool
    error: ApiError | None = None


class ModelSelection(ContractModel):
    model_id: str


class AiDocumentCreateInput(ContractModel):
    title: str = Field(min_length=1, max_length=200)
    instruction: str = Field(min_length=1, max_length=10000)
    source_version_ids: list[str] = Field(json_schema_extra={"uniqueItems": True})
    grounding_mode: Literal["strict", "general-knowledge", "supplemental"]
    model_id: str

    @field_validator("source_version_ids")
    @classmethod
    def source_versions_must_be_unique(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("source_version_ids must contain unique items")
        return value


class AiDocumentVersion(ContractModel):
    id: str
    document_id: str
    number: int = Field(ge=1)
    status: Literal["ready", "unavailable"]
    content: list[ContentBlock]
    upstream_citations: list[Citation]
    created_at: int


class AiDocumentVersionList(ContractModel):
    items: list[AiDocumentVersion]


class AiDocument(ContractModel):
    id: str
    subject_id: str
    title: str
    generated_by: Literal["ai"]
    current_version_id: str
    versions: list[AiDocumentVersion]
    created_at: int
    updated_at: int


class AiDocumentList(ContractModel):
    items: list[AiDocument]


class AiDocumentRevisionInput(ContractModel):
    base_version_id: str
    instruction: str = Field(min_length=1, max_length=10000)
    model_id: str


class AiDocumentChange(ContractModel):
    path: str = Field(min_length=1)
    operation: Literal["add", "replace", "remove"]
    before: Any
    after: Any


class AiDocumentRevisionProposal(ContractModel):
    id: str
    document_id: str
    base_version_id: str
    status: Literal["generating", "ready", "applied", "discarded", "failed"]
    changes: list[AiDocumentChange]
    error: ApiError | None = None
    created_at: int
    updated_at: int


class AiDocumentRevisionProposalList(ContractModel):
    items: list[AiDocumentRevisionProposal]


class CrashCourseInput(ContractModel):
    goal: str = Field(min_length=1, max_length=2000)
    source_version_ids: list[str] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    grounding_mode: Literal["strict", "general-knowledge", "supplemental"]
    model_id: str | None = None

    @field_validator("source_version_ids")
    @classmethod
    def source_versions_must_be_unique(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("source_version_ids must contain unique items")
        return value


class SelfTest(ContractModel):
    prompt: list[ContentBlock]
    answer: list[ContentBlock]


class KnowledgePoint(ContractModel):
    id: str
    title: str = Field(min_length=1)
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
