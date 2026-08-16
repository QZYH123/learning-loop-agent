"""Explicitly requested AI-authored source documents and version proposals."""
from __future__ import annotations

import asyncio
import time
import uuid

from .learning import LearningError
from .model_client import ModelClientError
from .operations import OperationFailure
from .sources import SourceLibraryError


class AiDocumentService:
    def __init__(self, workspace_service, sources, operations, model_client, now=None, id_factory=None):
        self.workspace_service = workspace_service
        self.sources = sources
        self.operations = operations
        self.model_client = model_client
        self._now = now or (lambda: int(time.time() * 1000))
        self._ids = id_factory or (lambda prefix: f"{prefix}-{uuid.uuid4().hex}")

    def list_documents(self, subject_id: str) -> list[dict]:
        self._subject(subject_id)
        return self.workspace_service.snapshot()["subjects"][self._subject_index(subject_id)].get("data", {}).get("ai_documents", [])

    def get_document(self, document_id: str) -> dict:
        return self._find(document_id)[1]

    def list_versions(self, document_id: str) -> list[dict]:
        return self.get_document(document_id).get("versions", [])

    def create_document(self, subject_id: str, payload: dict) -> dict:
        self._subject(subject_id)
        self._validate_sources(subject_id, payload.get("source_version_ids", []), payload["grounding_mode"])
        profile = self._model(payload["model_id"])
        timestamp = self._now()
        document_id = self._ids("ai-document")
        version_id = self._ids("ai-document-version")
        resource = {"type": "ai-document", "id": document_id}

        async def worker():
            try:
                anchors = [] if payload["grounding_mode"] == "general-knowledge" else self.sources.retrieve(payload["instruction"], payload.get("source_version_ids", []), limit=10)
                if payload["grounding_mode"] == "strict" and not anchors:
                    raise OperationFailure("GROUNDING_SOURCE_REQUIRED", "资料未覆盖该文档要求")
                response = await self.model_client.chat(profile, [{"role": "user", "content": f"创建资料文档：{payload['instruction']}\n资料片段：{self._anchor_text(anchors)}"}])
                citations = [self.sources.create_citation(anchor) for anchor in anchors]
                version = {"id": version_id, "document_id": document_id, "number": 1, "status": "ready", "content": [{"id": self._ids("block"), "type": "markdown", "text": response.get("text") or ""}], "upstream_citations": citations, "created_at": timestamp}
                document = {
                    "id": document_id,
                    "subject_id": subject_id,
                    "title": payload["title"],
                    "generated_by": "ai",
                    "current_version_id": version_id,
                    "versions": [version],
                    "created_at": timestamp,
                    "updated_at": self._now(),
                }
                self._mutate(subject_id, lambda data: {
                    **data,
                    "ai_documents": [*data.get("ai_documents", []), document],
                })
                return resource
            except asyncio.CancelledError:
                raise
            except (LearningError, SourceLibraryError, ModelClientError) as exc:
                raise OperationFailure(getattr(exc, "code", "AI_DOCUMENT_PROPOSAL_INVALID"), str(exc), retryable=True) from exc

        operation = self.operations.start("ai-document-generation", worker, subject_id=subject_id, resource=resource)
        return {"operation": operation, "resource": resource}

    def restore_version(self, document_id: str, version_id: str) -> dict:
        subject, document = self._find(document_id)
        version = next((item for item in document.get("versions", []) if item["id"] == version_id), None)
        if not version:
            raise LearningError(404, "RESOURCE_NOT_FOUND", "资料文档版本不存在")
        restored = self._new_version(document, version["content"], version["upstream_citations"])
        updated = {**document, "current_version_id": restored["id"], "versions": [*document["versions"], restored], "updated_at": self._now()}
        self._replace_document(subject["id"], document_id, updated)
        return updated

    def list_proposals(self, document_id: str) -> list[dict]:
        subject, document = self._find(document_id)
        return [item for item in subject.get("data", {}).get("ai_document_proposals", []) if item.get("document_id") == document_id]

    def get_proposal(self, proposal_id: str) -> dict:
        return self._find_proposal(proposal_id)[1]

    def create_proposal(self, document_id: str, payload: dict) -> dict:
        subject, document = self._find(document_id)
        if payload["base_version_id"] != document["current_version_id"]:
            raise LearningError(409, "AI_DOCUMENT_VERSION_CONFLICT", "资料文档已更新，请基于最新版本重试")
        profile = self._model(payload["model_id"])
        timestamp = self._now()
        proposal = {"id": self._ids("ai-document-proposal"), "document_id": document_id, "base_version_id": payload["base_version_id"], "status": "generating", "changes": [], "error": None, "created_at": timestamp, "updated_at": timestamp}
        self._mutate(subject["id"], lambda data: {**data, "ai_document_proposals": [*data.get("ai_document_proposals", []), proposal]})
        resource = {"type": "ai-document-proposal", "id": proposal["id"]}

        async def worker():
            try:
                base_version = next(
                    item
                    for item in document["versions"]
                    if item["id"] == proposal["base_version_id"]
                )
                current = base_version.get("content", [])
                citation_context = "\n".join(
                    f"[{citation['source_name']} - {citation['location']['label']}] {citation.get('excerpt') or ''}"
                    for citation in base_version.get("upstream_citations", [])
                )
                prompt = (
                    f"请按要求修改资料文档。\n\n修改要求：{payload['instruction']}"
                    f"\n\n当前文档内容：\n{self._content_text(current) or '无'}"
                    f"\n\n当前文档引用依据：\n{citation_context or '无'}"
                )
                response = await self.model_client.chat(profile, [{"role": "user", "content": prompt}])
                change = {"path": "/content", "operation": "replace", "before": current, "after": [{"id": self._ids("block"), "type": "markdown", "text": response.get("text") or ""}]}
                ready = {**proposal, "status": "ready", "changes": [change], "updated_at": self._now()}
                self._replace_proposal(subject["id"], proposal["id"], ready)
                return resource
            except asyncio.CancelledError:
                failed = {
                    **proposal,
                    "status": "failed",
                    "error": {
                        "code": "AI_DOCUMENT_PROPOSAL_INVALID",
                        "message": "修改提案生成已取消",
                        "retryable": True,
                        "details": {},
                    },
                    "updated_at": self._now(),
                }
                self._replace_proposal(subject["id"], proposal["id"], failed)
                raise
            except (LearningError, ModelClientError) as exc:
                failed = {**proposal, "status": "failed", "error": {"code": "AI_DOCUMENT_PROPOSAL_INVALID", "message": str(exc), "retryable": True, "details": {}}, "updated_at": self._now()}
                self._replace_proposal(subject["id"], proposal["id"], failed)
                raise OperationFailure("AI_DOCUMENT_PROPOSAL_INVALID", str(exc), retryable=True) from exc

        operation = self.operations.start("ai-document-revision", worker, subject_id=subject["id"], resource=resource)
        return {"operation": operation, "resource": resource}

    def apply_proposal(self, proposal_id: str) -> dict:
        subject, proposal = self._find_proposal(proposal_id)
        if proposal["status"] != "ready":
            raise LearningError(409, "AI_DOCUMENT_PROPOSAL_INVALID", "当前修改提案不能应用")
        _, document = self._find(proposal["document_id"])
        if document["current_version_id"] != proposal["base_version_id"]:
            raise LearningError(409, "AI_DOCUMENT_VERSION_CONFLICT", "资料文档已更新，该提案已失效")
        content = proposal["changes"][0]["after"]
        version = self._new_version(document, content, document["versions"][-1].get("upstream_citations", []))
        updated = {**document, "current_version_id": version["id"], "versions": [*document["versions"], version], "updated_at": self._now()}
        self._replace_document(subject["id"], document["id"], updated)
        self._replace_proposal(subject["id"], proposal_id, {**proposal, "status": "applied", "updated_at": self._now()})
        return updated

    def discard_proposal(self, proposal_id: str) -> None:
        subject, proposal = self._find_proposal(proposal_id)
        if proposal["status"] not in {"ready", "failed"}:
            raise LearningError(409, "AI_DOCUMENT_PROPOSAL_INVALID", "当前修改提案不能放弃")
        self._replace_proposal(subject["id"], proposal_id, {**proposal, "status": "discarded", "updated_at": self._now()})

    def _new_version(self, document: dict, content: list[dict], citations: list[dict]) -> dict:
        return {"id": self._ids("ai-document-version"), "document_id": document["id"], "number": len(document.get("versions", [])) + 1, "status": "ready", "content": content, "upstream_citations": citations, "created_at": self._now()}

    def _find(self, document_id: str) -> tuple[dict, dict]:
        for subject in self.workspace_service.snapshot().get("subjects", []):
            document = next((item for item in subject.get("data", {}).get("ai_documents", []) if item.get("id") == document_id), None)
            if document:
                return subject, document
        raise LearningError(404, "RESOURCE_NOT_FOUND", "AI 资料文档不存在")

    def _find_proposal(self, proposal_id: str) -> tuple[dict, dict]:
        for subject in self.workspace_service.snapshot().get("subjects", []):
            proposal = next((item for item in subject.get("data", {}).get("ai_document_proposals", []) if item.get("id") == proposal_id), None)
            if proposal:
                return subject, proposal
        raise LearningError(404, "RESOURCE_NOT_FOUND", "AI 资料文档修改提案不存在")

    def _subject(self, subject_id: str) -> dict:
        subject = next((item for item in self.workspace_service.snapshot().get("subjects", []) if item.get("id") == subject_id), None)
        if not subject:
            raise LearningError(404, "RESOURCE_NOT_FOUND", "科目空间不存在")
        return subject

    def _subject_index(self, subject_id: str) -> int:
        return next(index for index, item in enumerate(self.workspace_service.snapshot().get("subjects", [])) if item.get("id") == subject_id)

    def _model(self, model_id: str) -> dict:
        model = next((item for item in self.workspace_service.snapshot().get("models", []) if item.get("id") == model_id), None)
        if not model:
            raise LearningError(404, "RESOURCE_NOT_FOUND", "模型服务不存在")
        return model

    def _validate_sources(self, subject_id: str, version_ids: list[str], grounding_mode: str) -> None:
        if grounding_mode in {"strict", "supplemental"} and not version_ids:
            raise LearningError(409, "GROUNDING_SOURCE_REQUIRED", "当前依据模式需要至少选择一份资料")
        for version_id in version_ids:
            version = self.sources.get_version(version_id)
            source = self.sources.get_source(version["source_id"])
            if source["subject_id"] != subject_id or version["status"] != "ready":
                raise LearningError(409, "SOURCE_UNAVAILABLE", "选定资料不可用或不属于当前科目")

    @staticmethod
    def _anchor_text(anchors: list[dict]) -> str:
        return "\n".join(block.get("text", "") for anchor in anchors for block in anchor.get("content", []) if block.get("type") == "markdown")

    @staticmethod
    def _content_text(blocks: list[dict]) -> str:
        return "\n".join(
            block.get("text", "")
            for block in blocks
            if block.get("type") == "markdown"
        )

    def _mutate(self, subject_id: str, update) -> None:
        if self.workspace_service.update_subject_data(subject_id, update) is None:
            raise LearningError(404, "RESOURCE_NOT_FOUND", "科目空间不存在")

    def _replace_document(self, subject_id: str, document_id: str, document: dict) -> None:
        self._mutate(subject_id, lambda data: {**data, "ai_documents": [document if item.get("id") == document_id else item for item in data.get("ai_documents", [])]})

    def _replace_proposal(self, subject_id: str, proposal_id: str, proposal: dict) -> None:
        self._mutate(subject_id, lambda data: {**data, "ai_document_proposals": [proposal if item.get("id") == proposal_id else item for item in data.get("ai_document_proposals", [])]})
