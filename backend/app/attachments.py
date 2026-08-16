"""Message-scoped temporary attachment storage."""
from __future__ import annotations

import mimetypes
import time
import uuid
from pathlib import Path

from .learning import LearningError


MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
VISION_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


class AttachmentService:
    def __init__(self, workspace_service, data_dir, now=None, id_factory=None):
        self.workspace_service = workspace_service
        self.directory = Path(data_dir) / "attachments"
        self._now = now or (lambda: int(time.time() * 1000))
        self._ids = id_factory or (lambda prefix: f"{prefix}-{uuid.uuid4().hex}")

    def upload(self, subject_id: str, filename: str | None, content_type: str | None, content: bytes) -> dict:
        self._subject(subject_id)
        if len(content) > MAX_ATTACHMENT_BYTES:
            raise LearningError(413, "SOURCE_TOO_LARGE", "临时附件不能超过 10 MB")
        name = Path(filename or "").name.strip()
        if not name:
            raise LearningError(422, "VALIDATION_FAILED", "附件缺少文件名")
        mime_type = content_type or mimetypes.guess_type(name)[0] or "application/octet-stream"
        if not (mime_type.startswith("text/") or mime_type in VISION_TYPES or mime_type == "application/pdf"):
            raise LearningError(415, "SOURCE_TYPE_UNSUPPORTED", "消息附件仅支持文本、PDF 和图片")
        timestamp = self._now()
        attachment = {
            "id": self._ids("attachment"),
            "subject_id": subject_id,
            "file_name": name,
            "mime_type": mime_type,
            "size_bytes": len(content),
            "status": "ready",
            "vision_required": mime_type in VISION_TYPES,
            "failure": None,
            "created_at": timestamp,
            "expires_at": timestamp + 24 * 60 * 60 * 1000,
        }
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / f"{attachment['id']}.bin").write_bytes(content)
        self.workspace_service.update_subject_data(subject_id, lambda data: {**data, "attachments": [*data.get("attachments", []), attachment]})
        return attachment

    def get(self, attachment_id: str) -> dict:
        subject, attachment = self._find(attachment_id)
        if attachment["expires_at"] <= self._now():
            raise LearningError(410, "ATTACHMENT_EXPIRED", "临时附件已过期")
        return attachment

    def require(self, subject_id: str, attachment_id: str) -> dict:
        subject, attachment = self._find(attachment_id)
        if subject["id"] != subject_id:
            raise LearningError(409, "ATTACHMENT_NOT_FOUND", "附件不属于当前科目")
        return self.get(attachment_id)

    def file(self, attachment_id: str) -> tuple[bytes, str]:
        attachment = self.get(attachment_id)
        path = self.directory / f"{attachment_id}.bin"
        if not path.exists():
            raise LearningError(404, "ATTACHMENT_NOT_FOUND", "附件内容不存在")
        return path.read_bytes(), attachment["mime_type"]

    def delete(self, attachment_id: str) -> None:
        subject, attachment = self._find(attachment_id)
        self.workspace_service.update_subject_data(subject["id"], lambda data: {**data, "attachments": [item for item in data.get("attachments", []) if item.get("id") != attachment_id]})
        (self.directory / f"{attachment_id}.bin").unlink(missing_ok=True)

    def _find(self, attachment_id: str) -> tuple[dict, dict]:
        for subject in self.workspace_service.snapshot().get("subjects", []):
            attachment = next((item for item in subject.get("data", {}).get("attachments", []) if item.get("id") == attachment_id), None)
            if attachment:
                return subject, attachment
        raise LearningError(404, "ATTACHMENT_NOT_FOUND", "临时附件不存在")

    def _subject(self, subject_id: str) -> dict:
        subject = next((item for item in self.workspace_service.snapshot().get("subjects", []) if item.get("id") == subject_id), None)
        if not subject:
            raise LearningError(404, "RESOURCE_NOT_FOUND", "科目空间不存在")
        return subject
