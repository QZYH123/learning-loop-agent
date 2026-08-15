"""Markdown/TXT source-library adapter and parse-cache orchestration."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from .domain import (
    SOURCE_ADD_VERSION,
    SOURCE_COMPLETE_VERSION,
    SOURCE_CREATE,
    SOURCE_DELETE,
    SOURCE_FAIL_VERSION,
)
from .operations import OperationFailure, OperationManager


MAX_SOURCE_BYTES = 20 * 1024 * 1024
SOURCE_FORMATS = {
    ".md": ("markdown", "text/markdown"),
    ".markdown": ("markdown", "text/markdown"),
    ".txt": ("text", "text/plain"),
}


class SourceLibraryError(Exception):
    def __init__(self, status_code: int, code: str, message: str, *, retryable: bool = False, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.retryable = retryable
        self.details = details or {}


class SourceLibrary:
    def __init__(self, workspace_service, operations: OperationManager, data_path: Path):
        self.workspace_service = workspace_service
        self.operations = operations
        self.files_dir = data_path / "source-files"
        self.cache_dir = data_path / "source-cache"

    def list_sources(self, subject_id: str) -> list[dict]:
        subject = self._subject(subject_id)
        return subject.get("data", {}).get("sources", [])

    def get_source(self, source_id: str) -> dict:
        for subject in self.workspace_service.snapshot().get("subjects", []):
            source = next(
                (item for item in subject.get("data", {}).get("sources", []) if item.get("id") == source_id),
                None,
            )
            if source:
                return source
        raise SourceLibraryError(404, "RESOURCE_NOT_FOUND", "用户资料不存在")

    def list_versions(self, source_id: str) -> list[dict]:
        source = self.get_source(source_id)
        versions = self._versions_for_source(source["subject_id"], source_id)
        return [self._version_summary(version) for version in sorted(versions, key=lambda item: item["number"])]

    def get_version(self, version_id: str) -> dict:
        for subject in self.workspace_service.snapshot().get("subjects", []):
            version = next(
                (
                    item
                    for item in subject.get("data", {}).get("source_versions", [])
                    if item.get("id") == version_id
                ),
                None,
            )
            if version:
                return version
        raise SourceLibraryError(404, "RESOURCE_NOT_FOUND", "资料版本不存在")

    def create_source(self, subject_id: str, filename: str | None, display_name: str | None, content: bytes) -> dict:
        self._subject(subject_id)
        name, media_kind, mime_type = self._validate_upload(filename, display_name, content)
        digest = hashlib.sha256(content).hexdigest()
        result = self.workspace_service.dispatch(
            {
                "type": SOURCE_CREATE,
                "subject_id": subject_id,
                "display_name": name,
                "media_kind": media_kind,
                "mime_type": mime_type,
                "content_hash": digest,
                "size_bytes": len(content),
            }
        )
        self._require_dispatch(result)
        return self._start_parse(result["source"], result["version"], content, media_kind)

    def create_version(self, source_id: str, filename: str | None, content: bytes) -> dict:
        source = self.get_source(source_id)
        _, media_kind, mime_type = self._validate_upload(filename, source["display_name"], content)
        if media_kind != source["media_kind"]:
            raise SourceLibraryError(415, "SOURCE_TYPE_UNSUPPORTED", "新版本必须与原资料类型一致")
        if self.operations.has_active("source", source_id):
            raise SourceLibraryError(409, "OPERATION_IN_PROGRESS", "该资料已有版本正在处理")
        result = self.workspace_service.dispatch(
            {
                "type": SOURCE_ADD_VERSION,
                "source_id": source_id,
                "mime_type": mime_type,
                "content_hash": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
        )
        self._require_dispatch(result)
        return self._start_parse(result["source"], result["version"], content, media_kind)

    def delete_source(self, source_id: str) -> None:
        source = self.get_source(source_id)
        if self.operations.has_active("source", source_id):
            raise SourceLibraryError(409, "OPERATION_IN_PROGRESS", "资料仍在处理中，请等待完成或取消任务")
        result = self.workspace_service.dispatch({"type": SOURCE_DELETE, "source_id": source["id"]})
        self._require_dispatch(result)

    def _start_parse(self, source: dict, version: dict, content: bytes, media_kind: str) -> dict:
        async def worker():
            await asyncio.sleep(0)
            try:
                self._write_atomic(self.files_dir / f"{version['id']}.bin", content)
                cached, anchor_count = self._parse_with_cache(version["content_hash"], content, media_kind)
                result = self.workspace_service.dispatch(
                    {
                        "type": SOURCE_COMPLETE_VERSION,
                        "version_id": version["id"],
                        "cache_hit": cached,
                        "anchor_count": anchor_count,
                    }
                )
                self._require_worker_dispatch(result)
                return {"type": "source-version", "id": version["id"]}
            except asyncio.CancelledError:
                self._mark_failed(version["id"], "资料解析已取消")
                raise
            except UnicodeDecodeError as exc:
                message = "资料不是有效的 UTF-8 文本"
                self._mark_failed(version["id"], message)
                raise OperationFailure("SOURCE_PROCESSING_FAILED", message, details={"reason": str(exc)}) from exc
            except OSError as exc:
                message = "无法保存或解析用户资料"
                self._mark_failed(version["id"], message, retryable=True)
                raise OperationFailure(
                    "SOURCE_PROCESSING_FAILED",
                    message,
                    retryable=True,
                    details={"reason": str(exc)},
                ) from exc

        resource = {"type": "source", "id": source["id"]}
        operation = self.operations.start(
            "source-parsing",
            worker,
            subject_id=source["subject_id"],
            resource=resource,
        )
        return {"operation": operation, "resource": resource}

    def _parse_with_cache(self, digest: str, content: bytes, media_kind: str) -> tuple[bool, int]:
        cache_path = self.cache_dir / f"{digest}.json"
        if cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                if cached.get("content_hash") == digest and isinstance(cached.get("text"), str):
                    return True, int(cached.get("anchor_count") or 0)
            except (OSError, ValueError, TypeError):
                pass

        text = content.decode("utf-8-sig")
        chunks = [chunk for chunk in re.split(r"\n\s*\n", text) if chunk.strip()]
        payload = {
            "schema_version": 1,
            "content_hash": digest,
            "media_kind": media_kind,
            "text": text,
            "anchor_count": len(chunks),
        }
        self._write_atomic(cache_path, (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        return False, len(chunks)

    def _mark_failed(self, version_id: str, message: str, retryable: bool = False) -> None:
        self.workspace_service.dispatch(
            {
                "type": SOURCE_FAIL_VERSION,
                "version_id": version_id,
                "error_code": "SOURCE_PROCESSING_FAILED",
                "error_message": message,
                "retryable": retryable,
            }
        )

    def _subject(self, subject_id: str) -> dict:
        subject = next(
            (item for item in self.workspace_service.snapshot().get("subjects", []) if item.get("id") == subject_id),
            None,
        )
        if not subject:
            raise SourceLibraryError(404, "RESOURCE_NOT_FOUND", "科目空间不存在")
        return subject

    def _versions_for_source(self, subject_id: str, source_id: str) -> list[dict]:
        subject = self._subject(subject_id)
        return [
            item
            for item in subject.get("data", {}).get("source_versions", [])
            if item.get("source_id") == source_id
        ]

    @staticmethod
    def _version_summary(version: dict) -> dict:
        keys = (
            "id",
            "number",
            "status",
            "content_hash",
            "mime_type",
            "size_bytes",
            "anchor_count",
            "cache_hit",
            "created_at",
            "processed_at",
        )
        return {key: version.get(key) for key in keys}

    @staticmethod
    def _validate_upload(filename: str | None, display_name: str | None, content: bytes) -> tuple[str, str, str]:
        if len(content) > MAX_SOURCE_BYTES:
            raise SourceLibraryError(413, "SOURCE_TOO_LARGE", f"资料不能超过 {MAX_SOURCE_BYTES // (1024 * 1024)} MB")
        safe_filename = Path(filename or "").name.strip()
        if not safe_filename:
            raise SourceLibraryError(422, "VALIDATION_FAILED", "上传文件缺少文件名")
        source_format = SOURCE_FORMATS.get(Path(safe_filename).suffix.lower())
        if not source_format:
            raise SourceLibraryError(415, "SOURCE_TYPE_UNSUPPORTED", "当前只支持 Markdown 和 TXT 资料")
        name = (display_name or safe_filename).strip()
        if not name or len(name) > 255:
            raise SourceLibraryError(422, "VALIDATION_FAILED", "资料名称长度必须为 1 到 255 个字符")
        return name, source_format[0], source_format[1]

    @staticmethod
    def _write_atomic(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f"{path.name}-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    @staticmethod
    def _require_dispatch(result: dict) -> None:
        if not result.get("ok"):
            error = result.get("error") or {}
            status = 404 if error.get("code") == "RESOURCE_NOT_FOUND" else 409
            raise SourceLibraryError(status, error.get("code", "RESOURCE_CONFLICT"), error.get("message", "操作失败"))
        if result.get("persisted") is False:
            error = result.get("storage_error") or {}
            raise SourceLibraryError(500, "STORAGE_WRITE_FAILED", error.get("message", "无法保存工作区"), retryable=True)

    @staticmethod
    def _require_worker_dispatch(result: dict) -> None:
        if not result.get("ok"):
            error = result.get("error") or {}
            raise OperationFailure(error.get("code", "RESOURCE_CONFLICT"), error.get("message", "无法更新资料状态"))
        if result.get("persisted") is False:
            error = result.get("storage_error") or {}
            raise OperationFailure(
                "STORAGE_WRITE_FAILED",
                error.get("message", "无法保存工作区"),
                retryable=True,
            )
