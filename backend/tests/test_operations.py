import json

from backend.app.operations import OperationManager


def test_operation_manager_recovers_interrupted_record_as_retryable_failure(tmp_path):
    path = tmp_path / "operations.json"
    path.write_text(
        json.dumps({
            "schema_version": 1,
            "operations": [{
                "id": "operation-1",
                "kind": "source-parsing",
                "status": "running",
                "cancelable": True,
                "progress": {"completed": 0, "total": 1, "message": "正在执行"},
                "subject_id": "subject-1",
                "resource": {"type": "source", "id": "source-1"},
                "result": None,
                "error": None,
                "created_at": 10,
                "updated_at": 20,
                "started_at": 20,
                "completed_at": None,
            }],
        }),
        encoding="utf-8",
    )

    manager = OperationManager(now=lambda: 1000, storage_path=path)

    operation = manager.get("operation-1")
    assert operation["status"] == "failed"
    assert operation["cancelable"] is False
    assert operation["error"]["code"] == "INTERNAL_ERROR"
    assert operation["error"]["retryable"] is True
    assert operation["completed_at"] == 1000

    persisted = json.loads(path.read_text(encoding="utf-8"))["operations"][0]
    assert persisted == operation
