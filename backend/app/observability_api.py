"""HTTP routes for orchestration runs and fixed evaluations."""
from __future__ import annotations

from fastapi import APIRouter, Query

from .api_models import ErrorResponse, OperationAccepted
from .observability import (
    EvaluationRun,
    EvaluationRunInput,
    EvaluationSuiteList,
    OPERATION_KINDS,
    OrchestrationRun,
    OrchestrationRunList,
)


def create_observability_router(observability, evaluations) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/orchestration-runs",
        operation_id="listOrchestrationRuns",
        response_model=OrchestrationRunList,
    )
    def list_runs(subject_id: str | None = Query(default=None), category: OPERATION_KINDS | None = Query(default=None)):
        return {"items": observability.list_runs(subject_id=subject_id, category=category)}

    @router.get(
        "/api/orchestration-runs/{run_id}",
        operation_id="getOrchestrationRun",
        response_model=OrchestrationRun,
        responses={404: {"model": ErrorResponse}},
    )
    def get_run(run_id: str):
        return observability.get_run(run_id)

    @router.get(
        "/api/evaluation-suites",
        operation_id="listEvaluationSuites",
        response_model=EvaluationSuiteList,
    )
    def list_suites():
        return {"items": evaluations.list_suites()}

    @router.post(
        "/api/evaluation-suites/{suite_id}/runs",
        operation_id="runEvaluationSuite",
        status_code=202,
        response_model=OperationAccepted,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def run_suite(suite_id: str, payload: EvaluationRunInput):
        return evaluations.run_suite(suite_id, payload.model_dump(exclude_none=True))

    @router.get(
        "/api/evaluation-runs/{evaluation_run_id}",
        operation_id="getEvaluationRun",
        response_model=EvaluationRun,
        responses={404: {"model": ErrorResponse}},
    )
    def get_evaluation_run(evaluation_run_id: str):
        return evaluations.get_run(evaluation_run_id)

    return router
