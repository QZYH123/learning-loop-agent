"""Explicitly requested AI-authored source documents and version proposals."""
from __future__ import annotations

import asyncio
import base64
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
                prompt = (
                    f"{self._grounding_instruction(payload['grounding_mode'])}"
                    "\n第一行只输出文档标题（创建要求中明确指定了名称或标题时必须原样使用指定名称），"
                    "从第二行开始输出正文，不要在标题行加任何前缀符号"
                    f"\n\n创建资料文档：{payload['instruction']}"
                    f"\n\n资料片段：\n{self._anchor_text(anchors) or '无'}"
                )
                response = await self.model_client.chat(profile, [{
                    "role": "user",
                    "content": self._grounded_content(prompt, anchors, profile),
                }])
                citations = self._citations_for_anchors(anchors)
                title, body = self._parse_generated_document(response.get("text") or "", payload.get("title"))
                version = {"id": version_id, "document_id": document_id, "number": 1, "status": "ready", "content": [{"id": self._ids("block"), "type": "markdown", "text": body}], "upstream_citations": citations, "created_at": timestamp}
                document = {
                    "id": document_id,
                    "subject_id": subject_id,
                    "title": title,
                    "generated_by": "ai",
                    "current_version_id": version_id,
                    "versions": [version],
                    "created_at": timestamp,
                    "updated_at": self._now(),
                }
                self._store_document_version(subject_id, document, version)
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
        self._store_document_version(subject["id"], updated, restored)
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
                    "请按要求修改资料文档。只能根据当前文档内容和已有引用依据改写；"
                    "不要新增引用未覆盖的事实，也不要编造来源。"
                    f"\n\n修改要求：{payload['instruction']}"
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
        self._store_document_version(subject["id"], updated, version)
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
        parts = []
        for anchor in anchors:
            for block in anchor.get("content", []):
                if block.get("type") == "markdown":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "latex":
                    parts.append(block.get("latex", ""))
                elif block.get("type") == "table":
                    parts.append(" | ".join(block.get("columns", [])))
                    parts.extend(" | ".join(row) for row in block.get("rows", []))
        return "\n".join(part for part in parts if part)

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

    def _store_document_version(self, subject_id: str, document: dict, version: dict) -> None:
        subject = self._subject(subject_id)
        data = subject.get("data", {})
        existing_source = next(
            (item for item in data.get("sources", []) if item.get("id") == document["id"]),
            None,
        )
        source, source_version = self.sources.materialize_ai_document_version(
            document,
            version,
            existing_source,
        )

        def update(current):
            documents = current.get("ai_documents", [])
            if any(item.get("id") == document["id"] for item in documents):
                documents = [
                    document if item.get("id") == document["id"] else item
                    for item in documents
                ]
            else:
                documents = [*documents, document]
            sources = current.get("sources", [])
            if existing_source:
                sources = [source if item.get("id") == source["id"] else item for item in sources]
            else:
                sources = [*sources, source]
            source_versions = [
                item
                for item in current.get("source_versions", [])
                if item.get("id") != source_version["id"]
            ]
            return {
                **current,
                "ai_documents": documents,
                "sources": sources,
                "source_versions": [*source_versions, source_version],
            }

        self._mutate(subject_id, update)

    def _replace_proposal(self, subject_id: str, proposal_id: str, proposal: dict) -> None:
        self._mutate(subject_id, lambda data: {**data, "ai_document_proposals": [proposal if item.get("id") == proposal_id else item for item in data.get("ai_document_proposals", [])]})

    def _citations_for_anchors(self, anchors: list[dict]) -> list[dict]:
        citations = []
        for anchor in anchors:
            citations.append(self.sources.create_citation(anchor))
            for upstream in anchor.get("_upstream_citations", []):
                try:
                    citations.append(self.sources.get_citation(upstream["id"]))
                except SourceLibraryError:
                    citations.append({**upstream, "available": False})
        return list({citation["id"]: citation for citation in citations}.values())

    def _grounded_content(self, text: str, anchors: list[dict], profile: dict) -> str | list[dict]:
        image_blocks = [
            block
            for anchor in anchors
            for block in anchor.get("content", [])
            if block.get("type") == "image"
        ]
        if not image_blocks:
            return text
        if not profile.get("capabilities", {}).get("vision"):
            raise LearningError(409, "IMAGE_INPUT_UNSUPPORTED", "当前模型不支持图片资料")
        content = [{"type": "text", "text": text}]
        for block in image_blocks:
            asset = block["asset"]
            raw, mime_type = self.sources.get_asset(asset["source_version_id"], asset["asset_id"])
            encoded = base64.b64encode(raw).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}})
        return content

    @classmethod
    def _parse_generated_document(cls, text: str, fallback_title: str | None) -> tuple[str, str]:
        raw = text or ""
        lines = raw.splitlines()
        first_idx = next((index for index, line in enumerate(lines) if line.strip()), None)
        if first_idx is None:
            return (fallback_title or "学习笔记"), raw
        title = cls._strip_generated_title(lines[first_idx])
        if not title:
            return (fallback_title or "学习笔记"), raw
        return title[:60], "\n".join(lines[first_idx + 1 :])

    @staticmethod
    def _strip_generated_title(line: str) -> str:
        title = (line or "").strip()
        while title.startswith("#"):
            title = title[1:].strip()
        if title.startswith("《"):
            title = title[1:]
            if title.endswith("》"):
                title = title[:-1]
            title = title.strip()
        if len(title) >= 2 and title[0] in "\"'“‘「" and title[-1] in "\"'”’」":
            title = title[1:-1].strip()
        return title

    @staticmethod
    def _grounding_instruction(grounding_mode: str) -> str:
        if grounding_mode == "strict":
            return "只能依据提供的资料片段创建文档，不得补充资料之外的知识。"
        if grounding_mode == "supplemental":
            return "资料优先；可以补充通用知识，但必须明确标出资料外的补充内容。"
        return "使用通用知识创建文档，并明确说明内容未依据用户资料。"
