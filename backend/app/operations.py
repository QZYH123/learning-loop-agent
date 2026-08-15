"""Durable lifecycle for contract-defined asynchronous operations."""
from __future__ import annotations

import asyncio
import copy
import json
import os
import tempfile
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from pathlib import Path


TERMINAL_STATUSES = {"succeeded", "failed", "canceled"}
CURRENT_OPERATION_ID: ContextVar[str | None] = ContextVar("current_operation_id", default=None)


class OperationFailure(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.details = details or {}


class OperationManager:
    def __init__(self, now=None, id_factory=None, storage_path: str | os.PathLike | None = None):
        self._now = now or (lambda: int(time.time() * 1000))
        self._ids = id_factory or (lambda: f"operation-{uuid.uuid4().hex}")
        self._storage_path = Path(storage_path) if storage_path is not None else None
        self._records: dict[str, dict] = self._load_records()
        self._tasks: dict[str, asyncio.Task] = {}
        self._lock = threading.RLock()
        self._observer = None
        self.last_storage_error: str | None = None
        self._recover_interrupted()

    def set_observer(self, observer) -> None:
        self._observer = observer

    def start(
        self,
        kind: str,
        worker: Callable[[], Awaitable[dict | None]],
        *,
        subject_id: str | None = None,
        resource: dict | None = None,
        total: int | None = 1,
    ) -> dict:
        operation_id = self._ids()
        timestamp = self._now()
        record = {
            "id": operation_id,
            "kind": kind,
            "status": "queued",
            "cancelable": True,
            "progress": {"completed": 0, "total": total, "message": "等待执行"},
            "subject_id": subject_id,
            "resource": copy.deepcopy(resource),
            "result": None,
            "error": None,
            "created_at": timestamp,
            "updated_at": timestamp,
            "started_at": None,
            "completed_at": None,
        }
        with self._lock:
            self._records[operation_id] = record
            self._persist_locked()
            self._notify("operation_created", copy.deepcopy(record))
            self._tasks[operation_id] = asyncio.create_task(self._run(operation_id, worker))
        return copy.deepcopy(record)

    def get(self, operation_id: str) -> dict | None:
        with self._lock:
            record = self._records.get(operation_id)
            return copy.deepcopy(record) if record else None

    def cancel(self, operation_id: str) -> dict:
        with self._lock:
            record = self._records.get(operation_id)
            if not record:
                raise OperationFailure("RESOURCE_NOT_FOUND", "异步任务不存在")
            if record["status"] in TERMINAL_STATUSES or not record["cancelable"]:
                raise OperationFailure("OPERATION_NOT_CANCELABLE", "当前任务无法取消")
            task = self._tasks.get(operation_id)
            if not task:
                raise OperationFailure("OPERATION_NOT_CANCELABLE", "当前任务无法取消")
            self._update_locked(
                operation_id,
                status="canceling",
                progress={**record["progress"], "message": "正在取消"},
            )
            task.cancel()
            return copy.deepcopy(self._records[operation_id])

    def has_active(self, resource_type: str, resource_id: str) -> bool:
        with self._lock:
            return any(
                record["status"] not in TERMINAL_STATUSES
                and record.get("resource") == {"type": resource_type, "id": resource_id}
                for record in self._records.values()
            )

    def has_active_for_subject(self, subject_id: str) -> bool:
        with self._lock:
            return any(
                record["status"] not in TERMINAL_STATUSES and record.get("subject_id") == subject_id
                for record in self._records.values()
            )

    def active_for_subject(self, subject_id: str, kind: str | None = None) -> dict | None:
        with self._lock:
            record = next(
                (
                    item
                    for item in self._records.values()
                    if item["status"] not in TERMINAL_STATUSES
                    and item.get("subject_id") == subject_id
                    and (kind is None or item.get("kind") == kind)
                ),
                None,
            )
            return copy.deepcopy(record) if record else None

    def update_progress(self, operation_id: str, completed: int, total: int | None, message: str) -> None:
        with self._lock:
            if operation_id in self._records and self._records[operation_id]["status"] not in TERMINAL_STATUSES:
                self._update_locked(
                    operation_id,
                    progress={"completed": completed, "total": total, "message": message},
                )

    def record_stage(
        self,
        name: str,
        *,
        status: str = "succeeded",
        started_at: int | None = None,
        completed_at: int | None = None,
        outer_elapsed_ms: int = 0,
        model_wait_ms: int = 0,
        counters: dict | None = None,
    ) -> None:
        operation_id = CURRENT_OPERATION_ID.get()
        if operation_id:
            self._notify(
                "stage_recorded",
                operation_id,
                name=name,
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                outer_elapsed_ms=outer_elapsed_ms,
                model_wait_ms=model_wait_ms,
                counters=counters or {},
            )

    def record_action(self, category: str, *, subject_id: str | None, resource: dict | None, stage: str, attributes: dict | None = None) -> None:
        self._notify(
            "action_recorded",
            category=category,
            subject_id=subject_id,
            resource=copy.deepcopy(resource),
            stage=stage,
            attributes=attributes or {},
        )

    async def _run(self, operation_id: str, worker: Callable[[], Awaitable[dict | None]]) -> None:
        timestamp = self._now()
        with self._lock:
            record = self._records[operation_id]
            self._update_locked(
                operation_id,
                status="running",
                started_at=timestamp,
                progress={**record["progress"], "message": "正在执行"},
            )
            running_record = copy.deepcopy(self._records[operation_id])
        self._notify("operation_started", running_record)
        context_token = CURRENT_OPERATION_ID.set(operation_id)
        try:
            result = await worker()
            timestamp = self._now()
            with self._lock:
                record = self._records[operation_id]
                total = record["progress"]["total"]
                self._update_locked(
                    operation_id,
                    status="succeeded",
                    cancelable=False,
                    result=copy.deepcopy(result),
                    completed_at=timestamp,
                    progress={"completed": total or 1, "total": total, "message": "已完成"},
                )
        except asyncio.CancelledError:
            timestamp = self._now()
            with self._lock:
                record = self._records[operation_id]
                self._update_locked(
                    operation_id,
                    status="canceled",
                    cancelable=False,
                    completed_at=timestamp,
                    progress={**record["progress"], "message": "已取消"},
                )
        except OperationFailure as exc:
            self._fail(operation_id, exc)
        except Exception:
            self._fail(operation_id, OperationFailure("INTERNAL_ERROR", "异步任务执行失败"))
        finally:
            CURRENT_OPERATION_ID.reset(context_token)
            with self._lock:
                self._tasks.pop(operation_id, None)
                completed_record = copy.deepcopy(self._records[operation_id])
            self._notify("operation_finished", completed_record)

    def _fail(self, operation_id: str, failure: OperationFailure) -> None:
        timestamp = self._now()
        with self._lock:
            record = self._records[operation_id]
            self._update_locked(
                operation_id,
                status="failed",
                cancelable=False,
                error={
                    "code": failure.code,
                    "message": str(failure),
                    "retryable": failure.retryable,
                    "details": failure.details,
                },
                completed_at=timestamp,
                progress={**record["progress"], "message": "执行失败"},
            )

    def _update_locked(self, operation_id: str, **changes) -> None:
        self._records[operation_id] = {
            **self._records[operation_id],
            **changes,
            "updated_at": self._now(),
        }
        self._persist_locked()

    def _load_records(self) -> dict[str, dict]:
        if self._storage_path is None or not self._storage_path.exists():
            return {}
        try:
            payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        records = payload.get("operations") if isinstance(payload, dict) else None
        if not isinstance(records, list):
            return {}
        return {
            record["id"]: record
            for record in records
            if isinstance(record, dict) and isinstance(record.get("id"), str) and record["id"]
        }

    def _recover_interrupted(self) -> None:
        timestamp = self._now()
        recovered = False
        for operation_id, record in list(self._records.items()):
            if record.get("status") in TERMINAL_STATUSES:
                continue
            progress = record.get("progress") if isinstance(record.get("progress"), dict) else {}
            self._records[operation_id] = {
                **record,
                "status": "failed",
                "cancelable": False,
                "progress": {**progress, "message": "服务重启，任务已中断"},
                "result": None,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "异步任务因服务重启中断，请重试",
                    "retryable": True,
                    "details": {},
                },
                "updated_at": timestamp,
                "completed_at": timestamp,
            }
            recovered = True
        if recovered:
            self._persist_locked()

    def _persist_locked(self) -> None:
        if self._storage_path is None:
            return
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(
                prefix=f"{self._storage_path.name}-",
                suffix=".tmp",
                dir=self._storage_path.parent,
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(
                        {"schema_version": 1, "operations": list(self._records.values())},
                        handle,
                        ensure_ascii=False,
                        indent=2,
                    )
                    handle.write("\n")
                os.replace(temp_name, self._storage_path)
                self.last_storage_error = None
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
        except OSError as exc:
            self.last_storage_error = str(exc)

    def _notify(self, method: str, *args, **kwargs) -> None:
        observer = self._observer
        callback = getattr(observer, method, None) if observer is not None else None
        if callback is None:
            return
        try:
            callback(*args, **kwargs)
        except Exception:
            # Observability must never change the outcome of the operation it observes.
            return

    async def shutdown(self) -> None:
        with self._lock:
            tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
