"""File-backed workspace persistence."""
from __future__ import annotations

import json
import os
import threading
import time
from copy import deepcopy
from pathlib import Path

from .domain import apply_action, initial_workspace, normalize_workspace
from .files import write_json_atomic


class WorkspaceStore:
    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.last_load_issue: str | None = None

    def load(self) -> dict:
        if not self.path.exists():
            return initial_workspace()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.last_load_issue = "本地状态已损坏，已从空工作区重新开始。"
            return initial_workspace()
        workspace, issue = normalize_workspace(raw)
        self.last_load_issue = issue
        return workspace

    def save(self, workspace: dict) -> dict:
        try:
            with self._lock:
                write_json_atomic(self.path, workspace)
            return {"ok": True}
        except OSError as exc:
            return {
                "ok": False,
                "error": {
                    "code": "STORAGE_WRITE_FAILED",
                    "message": "无法写入本地工作区文件，请检查数据目录权限。",
                    "detail": str(exc),
                },
            }

    def clear(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass


class WorkspaceService:
    """Owns the current workspace and persists every successful action."""

    def __init__(self, store: WorkspaceStore, now=None, id_factory=None):
        self.store = store
        self.now = now
        self.id_factory = id_factory
        self.workspace = store.load()
        self.last_storage_error = None
        self._lock = threading.RLock()

    def dispatch(self, action: dict) -> dict:
        with self._lock:
            result = apply_action(self.workspace, action, now=self.now, id_factory=self.id_factory)
            if not result["ok"]:
                return result
            self.workspace = result["workspace"]
            saved = self.store.save(self.workspace)
            self.last_storage_error = None if saved["ok"] else saved["error"]
            return {
                **result,
                "workspace": self.workspace,
                "persisted": saved["ok"],
                "storage_error": self.last_storage_error,
            }

    def snapshot(self) -> dict:
        with self._lock:
            return deepcopy(self.workspace)

    def update_subject_data(self, subject_id: str, update) -> dict | None:
        with self._lock:
            subject = next((item for item in self.workspace.get("subjects", []) if item["id"] == subject_id), None)
            if not subject:
                return None
            timestamp = int(time.time() * 1000)
            data = update(deepcopy(subject.get("data", {})))
            updated_subject = {**subject, "data": data, "updated_at": timestamp}
            self.workspace = {
                **self.workspace,
                "subjects": [
                    updated_subject if item["id"] == subject_id else item
                    for item in self.workspace.get("subjects", [])
                ],
                "updated_at": timestamp,
            }
            saved = self.store.save(self.workspace)
            self.last_storage_error = None if saved["ok"] else saved["error"]
            return deepcopy(data)

    def update_workspace(self, update) -> dict:
        """Persist a root-level workspace update for cross-subject settings."""
        with self._lock:
            current = deepcopy(self.workspace)
            updated = update(current)
            self.workspace = updated
            timestamp = int(time.time() * 1000)
            self.workspace["updated_at"] = timestamp
            saved = self.store.save(self.workspace)
            self.last_storage_error = None if saved["ok"] else saved["error"]
            return deepcopy(self.workspace)
