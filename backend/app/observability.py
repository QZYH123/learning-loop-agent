"""Durable orchestration telemetry and fixed model evaluation suites."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from .api_models import ContractModel, ModelSnapshot, OperationKind, ResourceRef
from .files import write_json_atomic
from .learning import LearningError
from .model_client import ModelClientError
from .operations import OperationFailure


STAGE_NAMES = Literal["parse", "retrieve", "model-call", "structure-validation", "retry", "apply-change", "undo", "render", "export", "tool-call"]
RUN_STATUSES = Literal["running", "succeeded", "failed", "canceled"]
OPERATION_KINDS = OperationKind


class OrchestrationCounters(ContractModel):
    cache_hits: int = Field(default=0, ge=0)
    cache_misses: int = Field(default=0, ge=0)
    retrieval_hits: int = Field(default=0, ge=0)
    model_calls: int = Field(default=0, ge=0)
    validation_failures: int = Field(default=0, ge=0)
    retries: int = Field(default=0, ge=0)


class OrchestrationStage(ContractModel):
    name: STAGE_NAMES
    status: Literal["succeeded", "failed", "canceled", "skipped"]
    started_at: int
    completed_at: int | None
    outer_elapsed_ms: int = Field(ge=0)
    model_wait_ms: int = Field(ge=0)
    counters: OrchestrationCounters


class OrchestrationEvent(ContractModel):
    id: str
    type: str
    timestamp: int
    attributes: dict[str, str | int | float | bool | None]


class OrchestrationRun(ContractModel):
    id: str
    operation_id: str
    category: OPERATION_KINDS
    status: RUN_STATUSES
    subject_id: str | None
    resource: ResourceRef | None
    stages: list[OrchestrationStage]
    events: list[OrchestrationEvent]
    outer_elapsed_ms: int = Field(ge=0)
    model_wait_ms: int = Field(ge=0)
    created_at: int
    updated_at: int


class OrchestrationRunList(ContractModel):
    items: list[OrchestrationRun]


class EvaluationSuite(ContractModel):
    id: str
    name: str
    version: str
    sample_count: int = Field(ge=1)
    checks: list[Literal["citation-accuracy", "answer-correctness", "answer-leakage", "question-structure", "scoring-point-coverage"]]


class EvaluationSuiteList(ContractModel):
    items: list[EvaluationSuite]


class EvaluationRunInput(ContractModel):
    model_id: str
    sample_ids: set[str] = None


class AggregateOrchestrationMetrics(ContractModel):
    sample_count: int = Field(ge=0)
    duplicate_parses: int = Field(ge=0)
    duplicate_model_calls: int = Field(ge=0)
    cache_hit_rate: float | None = Field(default=None, ge=0, le=1)
    structure_validation_failure_rate: float | None = Field(default=None, ge=0, le=1)
    outer_elapsed_ms: int = Field(ge=0)
    model_wait_ms: int = Field(ge=0)


class ModelResultObservations(ContractModel):
    answer_accuracy: float | None = Field(default=None, ge=0, le=1)
    citation_accuracy: float | None = Field(default=None, ge=0, le=1)
    scoring_point_coverage: float | None = Field(default=None, ge=0, le=1)
    answer_leakage_rate: float | None = Field(default=None, ge=0, le=1)
    user_modification_rate: float | None = Field(default=None, ge=0, le=1)


class EvaluationRun(ContractModel):
    id: str
    suite_id: str
    suite_version: str
    model: ModelSnapshot
    status: Literal["queued", "running", "complete", "failed", "canceled"]
    orchestration_metrics: AggregateOrchestrationMetrics
    model_observations: ModelResultObservations
    created_at: int
    updated_at: int


DEFAULT_STAGES = {
    "model-verification": ["model-call"],
    "source-parsing": ["parse"],
    "chat-generation": ["retrieve", "model-call"],
    "crash-course-generation": ["retrieve", "model-call", "structure-validation"],
    "blueprint-parsing": ["retrieve", "model-call", "structure-validation"],
    "exam-generation": ["retrieve", "model-call", "structure-validation"],
    "question-retry": ["retry", "retrieve", "model-call", "structure-validation"],
    "subjective-feedback": ["model-call", "structure-validation"],
    "attempt-grading": ["model-call", "structure-validation"],
    "exam-revision": ["model-call", "structure-validation"],
    "ai-document-generation": ["retrieve", "model-call"],
    "ai-document-revision": ["model-call", "structure-validation"],
    "exam-export": ["render", "export"],
    "evaluation": ["model-call", "structure-validation"],
}


class ObservabilityService:
    def __init__(self, storage_path: str | os.PathLike, now=None, id_factory=None):
        self.storage_path = Path(storage_path)
        self._now = now or (lambda: int(time.time() * 1000))
        self._ids = id_factory or (lambda prefix: f"{prefix}-{uuid.uuid4().hex}")
        self._lock = threading.RLock()
        payload = self._load()
        self._runs = {item["id"]: item for item in payload.get("orchestration_runs", [])}
        self._operation_runs = {item["operation_id"]: item["id"] for item in self._runs.values()}
        self._evaluation_runs = {item["id"]: item for item in payload.get("evaluation_runs", [])}
        self._recover_interrupted()

    def operation_created(self, operation: dict) -> None:
        timestamp = self._now()
        run = {
            "id": self._ids("run"),
            "operation_id": operation["id"],
            "category": operation["kind"],
            "status": "running",
            "subject_id": operation.get("subject_id"),
            "resource": copy.deepcopy(operation.get("resource")),
            "stages": [],
            "events": [self._event("operation.created", {"kind": operation["kind"], "status": "queued"}, timestamp)],
            "outer_elapsed_ms": 0,
            "model_wait_ms": 0,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        with self._lock:
            self._runs[run["id"]] = run
            self._operation_runs[operation["id"]] = run["id"]
            self._persist_locked()

    def operation_started(self, operation: dict) -> None:
        self._append_event(operation["id"], "operation.started", {"status": "running"})

    def operation_finished(self, operation: dict) -> None:
        with self._lock:
            run = self._run_for_operation(operation["id"])
            if run is None:
                return
            timestamp = operation.get("completed_at") or self._now()
            started_at = operation.get("started_at") or operation["created_at"]
            outer_elapsed = max(0, timestamp - started_at)
            final_status = operation["status"] if operation["status"] in {"succeeded", "failed", "canceled"} else "failed"
            existing_names = {item["name"] for item in run["stages"]}
            missing = [name for name in DEFAULT_STAGES.get(operation["kind"], []) if name not in existing_names]
            non_model_elapsed = max(0, outer_elapsed - sum(item["model_wait_ms"] for item in run["stages"]))
            recorded_failure = any(item["status"] in {"failed", "canceled"} for item in run["stages"])
            for index, name in enumerate(missing):
                elapsed = non_model_elapsed if index == 0 else 0
                # 未被编排代码记录的阶段没有执行证据；成功运行也只能标为 skipped。
                # 失败/取消时，第一个缺失阶段是最接近故障点的阶段，其余阶段尚未执行。
                stage_status = "skipped" if final_status == "succeeded" or recorded_failure or index > 0 else final_status
                run["stages"].append(self._stage(
                    name,
                    stage_status,
                    started_at,
                    timestamp,
                    elapsed,
                    0,
                    {},
                ))
            run["status"] = final_status
            run["outer_elapsed_ms"] = outer_elapsed
            run["model_wait_ms"] = min(outer_elapsed, sum(item["model_wait_ms"] for item in run["stages"]))
            run["events"].append(self._event("operation.completed", {"status": final_status}, timestamp))
            run["updated_at"] = timestamp
            self._persist_locked()

    def stage_recorded(
        self,
        operation_id: str,
        *,
        name: str,
        status: str,
        started_at: int | None,
        completed_at: int | None,
        outer_elapsed_ms: int,
        model_wait_ms: int,
        counters: dict,
        attributes: dict | None = None,
    ) -> None:
        with self._lock:
            run = self._run_for_operation(operation_id)
            if run is None:
                return
            completed = completed_at or self._now()
            started = started_at or max(run["created_at"], completed - outer_elapsed_ms)
            run["stages"].append(self._stage(name, status, started, completed, outer_elapsed_ms, model_wait_ms, counters))
            run["model_wait_ms"] = sum(item["model_wait_ms"] for item in run["stages"])
            event_attributes = {"stage": name, "status": status, **(attributes or {})}
            run["events"].append(self._event("stage.completed", event_attributes, completed))
            run["updated_at"] = completed
            self._persist_locked()

    def action_recorded(self, *, category: str, subject_id: str | None, resource: dict | None, stage: str, attributes: dict) -> None:
        timestamp = self._now()
        run = {
            "id": self._ids("run"),
            "operation_id": self._ids("action"),
            "category": category,
            "status": "succeeded",
            "subject_id": subject_id,
            "resource": copy.deepcopy(resource),
            "stages": [self._stage(stage, "succeeded", timestamp, timestamp, 0, 0, {})],
            "events": [
                self._event("action.completed", {"stage": stage, **attributes}, timestamp),
            ],
            "outer_elapsed_ms": 0,
            "model_wait_ms": 0,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        with self._lock:
            self._runs[run["id"]] = run
            self._operation_runs[run["operation_id"]] = run["id"]
            self._persist_locked()

    def list_runs(self, subject_id: str | None = None, category: str | None = None) -> list[dict]:
        with self._lock:
            items = [
                copy.deepcopy(item)
                for item in self._runs.values()
                if (subject_id is None or item.get("subject_id") == subject_id)
                and (category is None or item["category"] == category)
            ]
        return sorted(items, key=lambda item: item["created_at"], reverse=True)

    def get_run(self, run_id: str) -> dict:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                raise LearningError(404, "RESOURCE_NOT_FOUND", "编排运行不存在")
            return copy.deepcopy(run)

    def create_evaluation_run(self, run: dict) -> None:
        with self._lock:
            self._evaluation_runs[run["id"]] = copy.deepcopy(run)
            self._persist_locked()

    def update_evaluation_run(self, run_id: str, **changes) -> dict:
        with self._lock:
            current = self._evaluation_runs.get(run_id)
            if current is None:
                raise LearningError(404, "RESOURCE_NOT_FOUND", "评估运行不存在")
            updated = {**current, **copy.deepcopy(changes), "updated_at": self._now()}
            self._evaluation_runs[run_id] = updated
            self._persist_locked()
            return copy.deepcopy(updated)

    def get_evaluation_run(self, run_id: str) -> dict:
        with self._lock:
            run = self._evaluation_runs.get(run_id)
            if run is None:
                raise LearningError(404, "RESOURCE_NOT_FOUND", "评估运行不存在")
            return copy.deepcopy(run)

    def evaluation_active(self, suite_id: str) -> bool:
        with self._lock:
            return any(item["suite_id"] == suite_id and item["status"] in {"queued", "running"} for item in self._evaluation_runs.values())

    def _append_event(self, operation_id: str, event_type: str, attributes: dict) -> None:
        with self._lock:
            run = self._run_for_operation(operation_id)
            if run is None:
                return
            timestamp = self._now()
            run["events"].append(self._event(event_type, attributes, timestamp))
            run["updated_at"] = timestamp
            self._persist_locked()

    def _run_for_operation(self, operation_id: str) -> dict | None:
        run_id = self._operation_runs.get(operation_id)
        return self._runs.get(run_id) if run_id else None

    def _event(self, event_type: str, attributes: dict, timestamp: int) -> dict:
        return {
            "id": self._ids("event"),
            "type": event_type,
            "timestamp": timestamp,
            "attributes": self._safe_attributes(attributes),
        }

    @staticmethod
    def _safe_attributes(attributes: dict) -> dict:
        blocked = {"api_key", "authorization", "prompt", "messages", "content", "source_text", "document"}
        safe = {}
        for key, value in attributes.items():
            if key.casefold() in blocked or not isinstance(value, (str, int, float, bool, type(None))):
                continue
            safe[key] = value[:200] if isinstance(value, str) else value
        return safe

    @staticmethod
    def _stage(name: str, status: str, started_at: int, completed_at: int, outer_elapsed_ms: int, model_wait_ms: int, counters: dict) -> dict:
        normalized_counters = {
            key: max(0, int(counters.get(key, 0)))
            for key in ("cache_hits", "cache_misses", "retrieval_hits", "model_calls", "validation_failures", "retries")
        }
        return {
            "name": name,
            "status": status,
            "started_at": started_at,
            "completed_at": completed_at,
            "outer_elapsed_ms": max(0, int(outer_elapsed_ms)),
            "model_wait_ms": max(0, int(model_wait_ms)),
            "counters": normalized_counters,
        }

    def _recover_interrupted(self) -> None:
        timestamp = self._now()
        changed = False
        for run in self._runs.values():
            if run["status"] == "running":
                run.update({"status": "failed", "updated_at": timestamp})
                run["events"].append(self._event("operation.recovered", {"status": "failed"}, timestamp))
                changed = True
        for run in self._evaluation_runs.values():
            if run["status"] in {"queued", "running"}:
                run.update({"status": "failed", "updated_at": timestamp})
                changed = True
        if changed:
            self._persist_locked()

    def _load(self) -> dict:
        if not self.storage_path.exists():
            return {}
        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _persist_locked(self) -> None:
        write_json_atomic(
            self.storage_path,
            {
                "schema_version": 1,
                "orchestration_runs": list(self._runs.values()),
                "evaluation_runs": list(self._evaluation_runs.values()),
            },
        )


EVALUATION_SUITES = [{
    "id": "core-learning-workflows",
    "name": "核心学习工作流固定评估",
    "version": "1.0.0",
    "sample_count": 5,
    "checks": [
        "citation-accuracy",
        "answer-correctness",
        "answer-leakage",
        "question-structure",
        "scoring-point-coverage",
    ],
}]


EVALUATION_SAMPLES = [
    {
        "id": "answer-basic-arithmetic",
        "check": "answer-correctness",
        "prompt": "回答 2 + 2，只返回 JSON：{\"answer\":\"...\"}。",
        "expected": "4",
    },
    {
        "id": "citation-fixed-context",
        "check": "citation-accuracy",
        "prompt": "资料 [source-limit]: 极限描述函数在某点附近的行为。只返回 JSON：{\"answer\":\"...\",\"citation_ids\":[\"...\"]}。",
        "expected": ["source-limit"],
    },
    {
        "id": "question-answer-isolation",
        "check": "answer-leakage",
        "prompt": "生成一道题目版选择题，只返回 JSON，字段仅允许 type、stem、options、score、answer_area，禁止答案、解析和依据。",
    },
    {
        "id": "question-required-structure",
        "check": "question-structure",
        "prompt": "生成一道完整选择题，只返回 JSON，必须含 type、stem、options、answer、explanation、knowledge_points。",
    },
    {
        "id": "subjective-scoring-points",
        "check": "scoring-point-coverage",
        "prompt": "评分点 point-nearby：提到附近行为。答案：极限描述附近行为。只返回 JSON：{\"matched_point_ids\":[\"...\"],\"missed_point_ids\":[]}。",
        "expected": ["point-nearby"],
    },
]


class EvaluationService:
    def __init__(self, learning, observability, now=None, id_factory=None):
        self.learning = learning
        self.operations = learning.operations
        self.model_client = learning.model_client
        self.observability = observability
        self._now = now or (lambda: int(time.time() * 1000))
        self._ids = id_factory or (lambda prefix: f"{prefix}-{uuid.uuid4().hex}")

    def list_suites(self) -> list[dict]:
        return copy.deepcopy(EVALUATION_SUITES)

    def run_suite(self, suite_id: str, payload: dict) -> dict:
        suite = next((item for item in EVALUATION_SUITES if item["id"] == suite_id), None)
        if suite is None:
            raise LearningError(404, "RESOURCE_NOT_FOUND", "固定评估样例集不存在")
        if self.observability.evaluation_active(suite_id):
            raise LearningError(409, "EVALUATION_ALREADY_RUNNING", "该固定评估样例集正在运行")
        profile = self.learning._model(payload["model_id"])
        samples = EVALUATION_SAMPLES
        if payload.get("sample_ids") is not None:
            selected = set(payload["sample_ids"])
            known = {item["id"] for item in EVALUATION_SAMPLES}
            if not selected or not selected <= known:
                raise LearningError(422, "VALIDATION_FAILED", "评估样例 ID 无效")
            samples = [item for item in EVALUATION_SAMPLES if item["id"] in selected]

        run_id = self._ids("evaluation-run")
        timestamp = self._now()
        run = {
            "id": run_id,
            "suite_id": suite_id,
            "suite_version": suite["version"],
            "model": self.learning._model_snapshot(profile),
            "status": "queued",
            "orchestration_metrics": self._empty_metrics(len(samples)),
            "model_observations": self._empty_observations(),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        self.observability.create_evaluation_run(run)
        resource = {"type": "evaluation-run", "id": run_id}
        operation_holder = {}

        async def worker():
            self.observability.update_evaluation_run(run_id, status="running")
            started = time.perf_counter()
            model_wait_ms = 0
            validation_failures = 0
            prompt_hashes = []
            scores: dict[str, list[float]] = {}
            try:
                for index, sample in enumerate(samples, start=1):
                    prompt_hashes.append(hashlib.sha256(sample["prompt"].encode("utf-8")).hexdigest())
                    model_started = time.perf_counter()
                    try:
                        response = await self.model_client.chat(profile, [{"role": "user", "content": sample["prompt"]}])
                    except ModelClientError:
                        model_wait_ms += max(0, round((time.perf_counter() - model_started) * 1000))
                        score = 0.0
                    else:
                        model_wait_ms += max(0, round((time.perf_counter() - model_started) * 1000))
                        validation_started = time.perf_counter()
                        try:
                            result = json.loads(response["text"])
                            score = self._score_sample(sample, result)
                        except (json.JSONDecodeError, TypeError, ValueError, KeyError):
                            validation_failures += 1
                            self.operations.record_stage(
                                "structure-validation",
                                status="failed",
                                outer_elapsed_ms=max(0, round((time.perf_counter() - validation_started) * 1000)),
                                counters={"validation_failures": 1},
                            )
                            score = 0.0
                        else:
                            self.operations.record_stage(
                                "structure-validation",
                                status="succeeded",
                                outer_elapsed_ms=max(0, round((time.perf_counter() - validation_started) * 1000)),
                                counters={},
                            )
                    scores.setdefault(sample["check"], []).append(score)
                    self.operations.update_progress(operation_holder["id"], index, len(samples), f"已评估 {index}/{len(samples)} 个固定样例")

                outer_elapsed_ms = max(0, round((time.perf_counter() - started) * 1000))
                duplicate_calls = len(prompt_hashes) - len(set(prompt_hashes))
                metrics = {
                    "sample_count": len(samples),
                    "duplicate_parses": 0,
                    "duplicate_model_calls": duplicate_calls,
                    "cache_hit_rate": None,
                    "structure_validation_failure_rate": validation_failures / len(samples) if samples else None,
                    "outer_elapsed_ms": outer_elapsed_ms,
                    "model_wait_ms": model_wait_ms,
                }
                observations = {
                    "answer_accuracy": self._average(scores.get("answer-correctness")),
                    "citation_accuracy": self._average(scores.get("citation-accuracy")),
                    "scoring_point_coverage": self._average(scores.get("scoring-point-coverage")),
                    "answer_leakage_rate": 1 - self._average(scores["answer-leakage"]) if scores.get("answer-leakage") else None,
                    "user_modification_rate": None,
                }
                self.observability.update_evaluation_run(
                    run_id,
                    status="complete",
                    orchestration_metrics=metrics,
                    model_observations=observations,
                )
                return resource
            except asyncio.CancelledError:
                self.observability.update_evaluation_run(run_id, status="canceled")
                raise
            except Exception as exc:
                self.observability.update_evaluation_run(run_id, status="failed")
                raise OperationFailure("INTERNAL_ERROR", "固定评估运行失败", retryable=True) from exc

        operation = self.operations.start("evaluation", worker, resource=resource, total=len(samples))
        operation_holder["id"] = operation["id"]
        return {"operation": operation, "resource": resource}

    def get_run(self, run_id: str) -> dict:
        return self.observability.get_evaluation_run(run_id)

    @staticmethod
    def _score_sample(sample: dict, result: Any) -> float:
        if not isinstance(result, dict):
            return 0.0
        check = sample["check"]
        if check == "answer-correctness":
            return float(str(result.get("answer", "")).strip().casefold() == sample["expected"].casefold())
        if check == "citation-accuracy":
            return float(set(result.get("citation_ids", [])) == set(sample["expected"]))
        if check == "answer-leakage":
            forbidden = {"answer", "explanation", "evidence", "solution", "knowledge_points"}
            return float(not EvaluationService._contains_key(result, forbidden))
        if check == "question-structure":
            required = {"type", "stem", "options", "answer", "explanation", "knowledge_points"}
            return float(required <= set(result))
        matched = set(result.get("matched_point_ids", []))
        missed = set(result.get("missed_point_ids", []))
        expected = set(sample["expected"])
        return len(matched & expected) / len(expected) if not (matched & missed) else 0.0

    @staticmethod
    def _contains_key(value: Any, forbidden: set[str]) -> bool:
        if isinstance(value, dict):
            return bool(set(value) & forbidden) or any(EvaluationService._contains_key(item, forbidden) for item in value.values())
        if isinstance(value, list):
            return any(EvaluationService._contains_key(item, forbidden) for item in value)
        return False

    @staticmethod
    def _average(values: list[float] | None) -> float | None:
        return sum(values) / len(values) if values else None

    @staticmethod
    def _empty_metrics(sample_count: int) -> dict:
        return {
            "sample_count": sample_count,
            "duplicate_parses": 0,
            "duplicate_model_calls": 0,
            "cache_hit_rate": None,
            "structure_validation_failure_rate": None,
            "outer_elapsed_ms": 0,
            "model_wait_ms": 0,
        }

    @staticmethod
    def _empty_observations() -> dict:
        return {
            "answer_accuracy": None,
            "citation_accuracy": None,
            "scoring_point_coverage": None,
            "answer_leakage_rate": None,
            "user_modification_rate": None,
        }
