"""Zip pack/unpack helpers for a single subject-space export."""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from .domain import SUBJECT_NAME_MAX_LENGTH
from .files import write_bytes_atomic

EXPORT_SCHEMA_VERSION = 1
IMPORT_NAME_SUFFIX = "（导入）"
CONFLICT_MESSAGE = "该科目已存在，请先删除或重命名现有科目"
UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
ALLOWED_SOURCE_TOP = {"source-files", "source-index", "source-cache"}


class TransferError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def sanitize_export_stem(name: str) -> str:
    cleaned = UNSAFE_FILENAME.sub("-", name or "").strip(" .-")
    return (cleaned or "subject")[:SUBJECT_NAME_MAX_LENGTH]


def local_date_stamp(now=None) -> str:
    clock = now or datetime.now
    current = clock()
    return current.strftime("%Y%m%d")


def export_zip_filename(name: str, date_stamp: str | None = None) -> str:
    return f"{sanitize_export_stem(name)}-{date_stamp or local_date_stamp()}.zip"


def content_disposition(file_name: str) -> str:
    return f"attachment; filename*=UTF-8''{quote(file_name)}"


def imported_subject_name(name: str, existing_names: set[str]) -> str:
    if name not in existing_names:
        return name
    suffix = IMPORT_NAME_SUFFIX
    max_base = SUBJECT_NAME_MAX_LENGTH - len(suffix)
    return f"{name[:max_base]}{suffix}"


def collect_source_entries(library, versions: list[dict]) -> list[tuple[str, bytes]]:
    entries: list[tuple[str, bytes]] = []
    seen: set[str] = set()

    def add(relative: str, data: bytes) -> None:
        if relative in seen:
            return
        seen.add(relative)
        entries.append((relative, data))

    for version in versions:
        version_id = version.get("id")
        if not version_id:
            continue
        original = library.files_dir / f"{version_id}.bin"
        if original.is_file():
            add(f"source-files/{version_id}.bin", original.read_bytes())
        index_path = library.index_dir / f"{version_id}.json"
        if index_path.is_file():
            add(f"source-index/{version_id}.json", index_path.read_bytes())
        digest = version.get("content_hash")
        if not digest:
            continue
        cache_json = library.cache_dir / f"{digest}.json"
        if cache_json.is_file():
            add(f"source-cache/{digest}.json", cache_json.read_bytes())
        assets_dir = library.cache_dir / f"{digest}.assets"
        if assets_dir.is_dir():
            for asset in sorted(path for path in assets_dir.rglob("*") if path.is_file()):
                relative = Path("source-cache") / asset.relative_to(library.cache_dir)
                add(relative.as_posix(), asset.read_bytes())
    return entries


def build_export_zip(
    *,
    subject: dict,
    citations: list[dict],
    source_entries: list[tuple[str, bytes]],
    exported_at: int,
) -> bytes:
    files = [
        "manifest.json",
        "subject.json",
        "citations.json",
        *[f"sources/{relative}" for relative, _ in source_entries],
    ]
    manifest = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "exported_at": exported_at,
        "subject_id": subject["id"],
        "subject_name": subject["name"],
        "files": files,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        _write_json(archive, "manifest.json", manifest)
        _write_json(archive, "subject.json", subject)
        _write_json(archive, "citations.json", {"schema_version": 1, "citations": citations})
        for relative, data in source_entries:
            archive.writestr(f"sources/{relative}", data)
    return buffer.getvalue()


def parse_export_zip(content: bytes) -> dict:
    archive = _open_zip(content)
    with archive:
        names = {_normalize_zip_name(name): name for name in archive.namelist() if not name.endswith("/")}
        if "manifest.json" not in names:
            raise TransferError(422, "VALIDATION_FAILED", "缺少 manifest.json，无法导入")
        manifest = _read_json(archive, names["manifest.json"], "manifest.json")
        if not isinstance(manifest, dict):
            raise TransferError(422, "VALIDATION_FAILED", "manifest.json 格式无效")
        version = manifest.get("schema_version")
        if version != EXPORT_SCHEMA_VERSION:
            raise TransferError(422, "VALIDATION_FAILED", "不支持的导出格式版本，请使用当前版本导出的文件")
        if "subject.json" not in names:
            raise TransferError(422, "VALIDATION_FAILED", "缺少 subject.json，无法导入")
        subject = _read_json(archive, names["subject.json"], "subject.json")
        _validate_subject_node(subject)
        citations_payload = {"schema_version": 1, "citations": []}
        if "citations.json" in names:
            citations_payload = _read_json(archive, names["citations.json"], "citations.json")
        citations = citations_payload.get("citations") if isinstance(citations_payload, dict) else None
        if not isinstance(citations, list):
            raise TransferError(422, "VALIDATION_FAILED", "citations.json 格式无效")
        source_entries = _read_source_entries(archive, names)
        _validate_ready_version_files(subject, source_entries)
    return {"manifest": manifest, "subject": subject, "citations": citations, "source_entries": source_entries}


def write_source_entries(library, source_entries: dict[str, bytes]) -> None:
    for relative, data in source_entries.items():
        dest = library_dest(library, relative)
        write_bytes_atomic(dest, data)


def library_dest(library, relative: str) -> Path:
    parts = Path(_normalize_zip_name(relative)).parts
    if not parts or parts[0] not in ALLOWED_SOURCE_TOP or ".." in parts:
        raise TransferError(422, "VALIDATION_FAILED", "导入文件路径不合法")
    mapping = {
        "source-files": library.files_dir,
        "source-index": library.index_dir,
        "source-cache": library.cache_dir,
    }
    dest = (mapping[parts[0]].joinpath(*parts[1:])).resolve()
    root = mapping[parts[0]].resolve()
    if dest != root and root not in dest.parents:
        raise TransferError(422, "VALIDATION_FAILED", "导入文件路径不合法")
    return dest


def _open_zip(content: bytes) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
        if archive.testzip() is not None:
            raise TransferError(422, "VALIDATION_FAILED", "导入文件已损坏，无法打开")
        return archive
    except TransferError:
        raise
    except (zipfile.BadZipFile, OSError, RuntimeError):
        raise TransferError(422, "VALIDATION_FAILED", "无法打开导入文件，请确认是有效的 zip") from None


def _read_json(archive: zipfile.ZipFile, name: str, label: str) -> dict | list:
    try:
        payload = json.loads(archive.read(name).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, OSError):
        raise TransferError(422, "VALIDATION_FAILED", f"{label} 无法解析") from None
    return payload


def _write_json(archive: zipfile.ZipFile, name: str, payload: dict) -> None:
    archive.writestr(name, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _normalize_zip_name(name: str) -> str:
    cleaned = name.replace("\\", "/").lstrip("/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def _validate_subject_node(subject) -> None:
    if not isinstance(subject, dict):
        raise TransferError(422, "VALIDATION_FAILED", "科目数据不完整，无法导入")
    subject_id = subject.get("id")
    name = subject.get("name")
    data = subject.get("data")
    if not isinstance(subject_id, str) or not subject_id.strip():
        raise TransferError(422, "VALIDATION_FAILED", "科目数据不完整，无法导入")
    if not isinstance(name, str) or not name.strip():
        raise TransferError(422, "VALIDATION_FAILED", "科目数据不完整，无法导入")
    if not isinstance(data, dict):
        raise TransferError(422, "VALIDATION_FAILED", "科目数据不完整，无法导入")


def _read_source_entries(archive: zipfile.ZipFile, names: dict[str, str]) -> dict[str, bytes]:
    entries: dict[str, bytes] = {}
    for normalized, original in names.items():
        if not normalized.startswith("sources/"):
            continue
        relative = normalized.removeprefix("sources/")
        parts = Path(relative).parts
        if not relative or ".." in parts or parts[0] not in ALLOWED_SOURCE_TOP:
            raise TransferError(422, "VALIDATION_FAILED", "导入文件路径不合法")
        entries[relative] = archive.read(original)
    return entries


def _validate_ready_version_files(subject: dict, source_entries: dict[str, bytes]) -> None:
    for version in subject.get("data", {}).get("source_versions", []) or []:
        if not isinstance(version, dict) or version.get("status") != "ready":
            continue
        version_id = version.get("id")
        if not version_id:
            raise TransferError(422, "VALIDATION_FAILED", "资料版本缺少原文件或解析索引，无法导入")
        has_file = f"source-files/{version_id}.bin" in source_entries
        has_index = f"source-index/{version_id}.json" in source_entries
        if not has_file or not has_index:
            raise TransferError(422, "VALIDATION_FAILED", "资料版本缺少原文件或解析索引，无法导入")
