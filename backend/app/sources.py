"""Markdown/TXT source-library adapter and parse-cache orchestration."""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import mimetypes
import re
import threading
import time
import uuid
from collections import Counter
from pathlib import Path

from .domain import (
    SOURCE_ADD_VERSION,
    SOURCE_COMPLETE_VERSION,
    SOURCE_CREATE,
    SOURCE_DELETE,
    SOURCE_FAIL_VERSION,
)
from .files import write_bytes_atomic, write_json_atomic
from .operations import OperationFailure, OperationManager
from .source_parsers import parse_source


MAX_SOURCE_BYTES = 20 * 1024 * 1024
BM25_K1 = 1.5
BM25_B = 0.75
SOURCE_FORMATS = {
    ".md": ("markdown", "text/markdown"),
    ".markdown": ("markdown", "text/markdown"),
    ".txt": ("text", "text/plain"),
    ".pdf": ("pdf", "application/pdf"),
    ".docx": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".pptx": ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    ".png": ("image", "image/png"),
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".webp": ("image", "image/webp"),
    ".gif": ("image", "image/gif"),
    ".bmp": ("image", "image/bmp"),
    ".tif": ("image", "image/tiff"),
    ".tiff": ("image", "image/tiff"),
}


def tokenize_terms(text: str, *, unique: bool = True) -> list[str]:
    folded = (text or "").casefold()
    terms = re.findall(r"[a-z0-9_]{2,}", folded)
    han_chars = re.findall(r"[\u4e00-\u9fff]", folded)
    if len(han_chars) < 2:
        terms.extend(han_chars)
    else:
        for run in re.findall(r"[\u4e00-\u9fff]+", folded):
            if len(run) < 2:
                terms.append(run)
            else:
                terms.extend(run[index : index + 2] for index in range(len(run) - 1))
    return list(dict.fromkeys(terms)) if unique else terms


def bm25_scores(query_terms: list[str], documents: list[list[str]], *, k1: float = BM25_K1, b: float = BM25_B) -> list[float]:
    if not documents:
        return []
    if not query_terms:
        return [0.0] * len(documents)
    lengths = [len(document) for document in documents]
    avgdl = sum(lengths) / len(documents)
    document_frequency: Counter[str] = Counter()
    for document in documents:
        document_frequency.update(set(document))
    total = len(documents)
    idf = {
        term: math.log((total - document_frequency.get(term, 0) + 0.5) / (document_frequency.get(term, 0) + 0.5) + 1)
        for term in query_terms
    }
    scores = []
    for document, length in zip(documents, lengths):
        term_frequency = Counter(document)
        score = 0.0
        for term in query_terms:
            freq = term_frequency.get(term, 0)
            if not freq:
                continue
            length_norm = k1 * (1 - b + b * (length / avgdl if avgdl else 0))
            score += idf[term] * freq * (k1 + 1) / (freq + length_norm)
        scores.append(score)
    return scores


def title_location_hit(anchor: dict, terms: list[str]) -> bool:
    if not terms:
        return False
    location = anchor.get("location") or {}
    fields = [str(location.get("label") or "")]
    fields.extend(str(part) for part in location.get("section_path") or [])
    haystack = "\n".join(fields).casefold()
    return any(term in haystack for term in terms)


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
        self.index_dir = data_path / "source-index"
        self.citations_path = data_path / "citations.json"
        self._citation_lock = threading.RLock()

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

    def get_anchor(self, version_id: str, anchor_id: str) -> dict:
        version = self.get_version(version_id)
        if version.get("status") == "unavailable":
            raise SourceLibraryError(410, "SOURCE_UNAVAILABLE", "资料已不可用，来源位置仅保留历史身份")
        if version.get("status") != "ready":
            raise SourceLibraryError(409, "SOURCE_UNAVAILABLE", "资料尚未完成解析")
        index = self._load_version_index(version_id)
        anchor = next((item for item in index.get("anchors", []) if item.get("id") == anchor_id), None)
        if not anchor:
            raise SourceLibraryError(404, "RESOURCE_NOT_FOUND", "来源位置不存在")
        return {**anchor, "available": True}

    def list_anchors(self, version_id: str) -> list[dict]:
        version = self.get_version(version_id)
        if version.get("status") == "unavailable":
            raise SourceLibraryError(410, "SOURCE_UNAVAILABLE", "资料已不可用，来源位置仅保留历史身份")
        if version.get("status") != "ready":
            raise SourceLibraryError(409, "SOURCE_UNAVAILABLE", "资料尚未完成解析")
        index = self._load_version_index(version_id)
        return [{**anchor, "available": True} for anchor in index.get("anchors", [])]

    def get_asset(self, version_id: str, asset_id: str) -> tuple[bytes, str]:
        version = self.get_version(version_id)
        if version.get("status") == "unavailable":
            raise SourceLibraryError(410, "SOURCE_UNAVAILABLE", "资料已不可用")
        index = self._load_version_index(version_id)
        asset = next((item for item in index.get("assets", []) if item.get("id") == asset_id), None)
        if not asset:
            raise SourceLibraryError(404, "RESOURCE_NOT_FOUND", "资料图片不存在")
        path = self.cache_dir / f"{version['content_hash']}.assets" / Path(asset["cache_file"]).name
        if not path.exists():
            raise SourceLibraryError(404, "RESOURCE_NOT_FOUND", "资料图片文件不存在")
        return path.read_bytes(), asset["mime_type"]

    def retrieve(
        self,
        query: str,
        version_ids: list[str],
        limit: int = 5,
        priority_version_ids: list[str] | None = None,
    ) -> list[dict]:
        retrieve_started_at = int(time.time() * 1000)
        retrieve_started = time.perf_counter()
        terms = self._query_terms(query)
        priority_ids = set(priority_version_ids or [])
        corpus: list[tuple[str, dict]] = []
        image_anchors = []
        for version_id in version_ids:
            version = self.get_version(version_id)
            if version.get("status") != "ready":
                raise SourceLibraryError(409, "SOURCE_UNAVAILABLE", "选定资料尚不可用于检索")
            index = self._load_version_index(version_id)
            for anchor in index.get("anchors", []):
                anchor = {
                    **anchor,
                    "_upstream_citations": index.get("upstream_citations", []),
                }
                corpus.append((version_id, anchor))
                if any(block.get("type") == "image" for block in anchor.get("content", [])):
                    image_anchors.append((int(version_id in priority_ids), anchor))

        documents = [tokenize_terms(self._anchor_text(anchor), unique=False) for _, anchor in corpus]
        scores = bm25_scores(terms, documents, k1=BM25_K1, b=BM25_B)
        scored = []
        for (version_id, anchor), score in zip(corpus, scores):
            if score <= 0:
                continue
            if title_location_hit(anchor, terms):
                score *= 2
            scored.append((int(version_id in priority_ids), score, anchor))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        unique = []
        seen: set[str] = set()
        for item in scored:
            key = self._anchor_text(item[2])[:200]
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        image_anchors.sort(key=lambda item: item[0], reverse=True)
        matches = [anchor for _, _, anchor in unique[:limit]]
        if not matches:
            matches = [anchor for _, anchor in image_anchors[:limit]]
        self.operations.record_stage(
            "retrieve",
            started_at=retrieve_started_at,
            completed_at=int(time.time() * 1000),
            outer_elapsed_ms=max(0, round((time.perf_counter() - retrieve_started) * 1000)),
            counters={"retrieval_hits": len(matches)},
        )
        return matches

    def create_citation(self, anchor: dict) -> dict:
        source = self.get_source(anchor["source_id"])
        citation = {
            "id": f"citation-{uuid.uuid4().hex}",
            "source_id": anchor["source_id"],
            "source_version_id": anchor["source_version_id"],
            "anchor_id": anchor["id"],
            "source_name": source["display_name"],
            "location": anchor["location"],
            "excerpt": self._anchor_text(anchor)[:1000] or None,
            "available": True,
        }
        with self._citation_lock:
            records = self._load_citations()
            records.append(citation)
            self._write_json_atomic(self.citations_path, {"schema_version": 1, "citations": records})
        return citation

    def get_citation(self, citation_id: str) -> dict:
        citation = next((item for item in self._load_citations() if item.get("id") == citation_id), None)
        if not citation:
            raise SourceLibraryError(404, "RESOURCE_NOT_FOUND", "来源引用不存在")
        version = self.get_version(citation["source_version_id"])
        return {**citation, "available": version.get("status") != "unavailable"}

    def list_citations(self) -> list[dict]:
        return list(self._load_citations())

    def merge_citations(self, incoming: list[dict]) -> None:
        with self._citation_lock:
            records = self._load_citations()
            existing = {item.get("id") for item in records if item.get("id")}
            changed = False
            for citation in incoming:
                citation_id = citation.get("id") if isinstance(citation, dict) else None
                if not citation_id or citation_id in existing:
                    continue
                records.append(citation)
                existing.add(citation_id)
                changed = True
            if changed:
                self._write_json_atomic(self.citations_path, {"schema_version": 1, "citations": records})

    def create_source(self, subject_id: str, filename: str | None, display_name: str | None, content: bytes) -> dict:
        self._subject(subject_id)
        name, media_kind, mime_type = self._validate_upload(filename, display_name, content)
        existing = next(
            (
                item
                for item in self.list_sources(subject_id)
                if item.get("display_name") == name
                and item.get("media_kind") == media_kind
                and not self._is_ai_document(item["id"])
            ),
            None,
        )
        if existing:
            return self.create_version(existing["id"], filename, content)
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
        if self._is_ai_document(source_id):
            raise SourceLibraryError(409, "AI_DOCUMENT_READ_ONLY", "AI 资料文档只能通过修改提案创建新版本")
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

    def materialize_ai_document_version(
        self,
        document: dict,
        version: dict,
        existing_source: dict | None = None,
    ) -> tuple[dict, dict]:
        encoded = json.dumps(version["content"], ensure_ascii=False, sort_keys=True).encode("utf-8")
        source_version = {
            "id": version["id"],
            "source_id": document["id"],
            "number": version["number"],
            "status": "ready",
            "content_hash": hashlib.sha256(encoded).hexdigest(),
            "mime_type": "text/markdown",
            "size_bytes": len(encoded),
            "anchor_count": 1,
            "cache_hit": False,
            "assets": [],
            "failure": None,
            "created_at": version["created_at"],
            "processed_at": version["created_at"],
        }
        source = {
            "id": document["id"],
            "subject_id": document["subject_id"],
            "display_name": document["title"],
            "media_kind": "markdown",
            "status": "ready",
            "current_version": self._version_summary(source_version),
            "version_count": version["number"],
            "failure": None,
            "created_at": (existing_source or {}).get("created_at", document["created_at"]),
            "updated_at": document["updated_at"],
        }
        anchor = {
            "id": f"anchor-{version['id']}-0",
            "source_id": document["id"],
            "source_version_id": version["id"],
            "location": {
                "kind": "section",
                "label": f"AI 生成：{document['title']}",
                "section_path": [document["title"]],
                "page": None,
                "slide": None,
                "block_index": 0,
                "asset_id": None,
            },
            "content": version["content"],
        }
        self._write_json_atomic(self.index_dir / f"{version['id']}.json", {
            "schema_version": 1,
            "source_id": document["id"],
            "source_version_id": version["id"],
            "anchors": [anchor],
            "assets": [],
            "upstream_citations": version.get("upstream_citations", []),
        })
        return source, source_version

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
                await asyncio.to_thread(self._write_atomic, self.files_dir / f"{version['id']}.bin", content)
                parse_started_at = int(time.time() * 1000)
                parse_started = time.perf_counter()
                cached, parsed = await asyncio.to_thread(
                    self._parse_with_cache,
                    version["content_hash"],
                    content,
                    media_kind,
                )
                self.operations.record_stage(
                    "parse",
                    started_at=parse_started_at,
                    completed_at=int(time.time() * 1000),
                    outer_elapsed_ms=max(0, round((time.perf_counter() - parse_started) * 1000)),
                    counters={"cache_hits": int(cached), "cache_misses": int(not cached)},
                )
                index = await asyncio.to_thread(self._materialize_version_index, source, version, parsed)
                result = self.workspace_service.dispatch(
                    {
                        "type": SOURCE_COMPLETE_VERSION,
                        "version_id": version["id"],
                        "cache_hit": cached,
                        "anchor_count": len(index["anchors"]),
                        "assets": [self._public_asset(asset) for asset in index["assets"]],
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
            except Exception as exc:
                message = "资料文件无法解析"
                self._mark_failed(version["id"], message)
                raise OperationFailure("SOURCE_PROCESSING_FAILED", message, details={"reason": str(exc)}) from exc

        resource = {"type": "source", "id": source["id"]}
        operation = self.operations.start(
            "source-parsing",
            worker,
            subject_id=source["subject_id"],
            resource=resource,
        )
        return {"operation": operation, "resource": resource}

    def _parse_with_cache(self, digest: str, content: bytes, media_kind: str) -> tuple[bool, dict]:
        cache_path = self.cache_dir / f"{digest}.json"
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("content_hash") == digest and isinstance(cached.get("anchors"), list):
                return True, cached

        parsed = parse_source(media_kind, content)
        cache_assets_dir = self.cache_dir / f"{digest}.assets"
        assets = []
        for index, asset in enumerate(parsed["assets"]):
            extension = mimetypes.guess_extension(asset["mime_type"]) or ".bin"
            filename = f"{index}{extension}"
            self._write_atomic(cache_assets_dir / filename, asset["data"])
            assets.append({key: value for key, value in asset.items() if key != "data"} | {"cache_file": filename})
        payload = {
            "schema_version": 1,
            "content_hash": digest,
            "media_kind": media_kind,
            "anchors": parsed["anchors"],
            "assets": assets,
        }
        self._write_json_atomic(cache_path, payload)
        return False, payload

    def _materialize_version_index(self, source: dict, version: dict, parsed: dict) -> dict:
        assets = []
        asset_ids = []
        for index, asset in enumerate(parsed.get("assets", [])):
            asset_id = f"asset-{uuid.uuid4().hex}"
            asset_ids.append(asset_id)
            assets.append({"id": asset_id, **asset})

        anchors = []
        for anchor_index, neutral in enumerate(parsed.get("anchors", [])):
            location = {**neutral["location"]}
            asset_index = location.pop("asset_index", None)
            location["asset_id"] = asset_ids[asset_index] if asset_index is not None else None
            blocks = []
            for block_index, neutral_block in enumerate(neutral.get("content", [])):
                block = {**neutral_block, "id": f"block-{version['id']}-{anchor_index}-{block_index}"}
                block_asset_index = block.pop("asset_index", None)
                if block_asset_index is not None:
                    block["asset"] = {
                        "source_version_id": version["id"],
                        "asset_id": asset_ids[block_asset_index],
                    }
                blocks.append(block)
            anchors.append({
                "id": f"anchor-{uuid.uuid4().hex}",
                "source_id": source["id"],
                "source_version_id": version["id"],
                "location": location,
                "content": blocks,
            })
        index = {
            "schema_version": 1,
            "source_id": source["id"],
            "source_version_id": version["id"],
            "anchors": anchors,
            "assets": assets,
        }
        self._write_json_atomic(self.index_dir / f"{version['id']}.json", index)
        return index

    def _load_version_index(self, version_id: str) -> dict:
        path = self.index_dir / f"{version_id}.json"
        if not path.exists():
            raise SourceLibraryError(404, "RESOURCE_NOT_FOUND", "资料版本尚无可用索引")
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_citations(self) -> list[dict]:
        if not self.citations_path.exists():
            return []
        payload = json.loads(self.citations_path.read_text(encoding="utf-8"))
        return payload.get("citations", [])

    @staticmethod
    def _query_terms(query: str) -> list[str]:
        return tokenize_terms(query)

    @staticmethod
    def _anchor_text(anchor: dict) -> str:
        values = []
        for block in anchor.get("content", []):
            if block.get("type") == "markdown":
                values.append(block.get("text", ""))
            elif block.get("type") == "latex":
                values.append(block.get("latex", ""))
            elif block.get("type") == "table":
                values.extend(block.get("columns", []))
                values.extend(cell for row in block.get("rows", []) for cell in row)
        return "\n".join(values)

    @staticmethod
    def _public_asset(asset: dict) -> dict:
        return {key: asset.get(key) for key in ("id", "kind", "mime_type", "width", "height", "alt")}

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict) -> None:
        write_json_atomic(path, payload)

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

    def _is_ai_document(self, source_id: str) -> bool:
        return any(
            document.get("id") == source_id
            for subject in self.workspace_service.snapshot().get("subjects", [])
            for document in subject.get("data", {}).get("ai_documents", [])
        )

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
            raise SourceLibraryError(415, "SOURCE_TYPE_UNSUPPORTED", "支持 Markdown、TXT、PDF、DOCX、PPTX 和常见图片格式")
        name = (display_name or safe_filename).strip()
        if not name or len(name) > 255:
            raise SourceLibraryError(422, "VALIDATION_FAILED", "资料名称长度必须为 1 到 255 个字符")
        return name, source_format[0], source_format[1]

    @staticmethod
    def _write_atomic(path: Path, content: bytes) -> None:
        write_bytes_atomic(path, content)

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
