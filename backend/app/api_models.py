"""Pydantic response models for the static HTTP contract."""
from __future__ import annotations

from typing import Any, Literal

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
