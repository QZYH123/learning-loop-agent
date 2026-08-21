import json
import time

from fastapi.testclient import TestClient

from backend.app.domain import SUBJECT_CREATE, normalize_workspace
from backend.app.main import create_app
from backend.app.pet import PetService, stage_for_ink
from backend.app.store import WorkspaceService, WorkspaceStore
from backend.tests.conftest import ImmediateFakeModelClient, make_client


TODAY = "2026-08-21"
YESTERDAY = "2026-08-20"
TWO_DAYS_AGO = "2026-08-19"


def local_ms(day: str, hour: int = 12) -> int:
    return int(time.mktime(time.strptime(f"{day} {hour:02d}:00:00", "%Y-%m-%d %H:%M:%S")) * 1000)


NOW_MS = local_ms(TODAY, 15)


def make_service(tmp_path, now_ms=NOW_MS, extra_data=None, extra_subjects=None):
    store = WorkspaceStore(tmp_path / "workspace.json")
    workspace = WorkspaceService(store)
    created = workspace.dispatch({"type": SUBJECT_CREATE, "name": "数学"})
    subject_id = created["subject_id"]
    if extra_data:
        workspace.update_subject_data(subject_id, lambda current: {**current, **extra_data})
    if extra_subjects:
        for name, data in extra_subjects:
            other = workspace.dispatch({"type": SUBJECT_CREATE, "name": name})
            workspace.update_subject_data(other["subject_id"], lambda current, payload=data: {**current, **payload})
    return PetService(workspace, now=lambda: now_ms), workspace, subject_id


def make_timed_client(tmp_path, now_ms=NOW_MS):
    app = create_app(data_dir=tmp_path / "data", model_client=ImmediateFakeModelClient(), now=lambda: now_ms)
    return TestClient(app), app


def user_messages(day: str, count: int):
    stamp = local_ms(day)
    return {
        "sessions": [{
            "id": "session-1",
            "messages": [
                {"id": f"u{index}", "role": "user", "created_at": stamp + index}
                for index in range(count)
            ] + [{"id": "a1", "role": "assistant", "created_at": stamp}],
        }],
    }


def test_empty_workspace_first_get_adopts_default_pet(tmp_path):
    before = int(time.time() * 1000)
    client, app = make_client(tmp_path)
    with client:
        response = client.get("/api/pet")
        after = int(time.time() * 1000)
        assert response.status_code == 200
        pet = response.json()
        assert pet["name"] == "小墨"
        assert pet["stage"] == 0
        assert pet["ink_total"] == 0
        assert pet["ink_today"] == 0
        assert pet["ink_to_next"] == 1
        assert pet["position_x"] == 78
        assert pet["position_y"] == 100
        assert pet["streak_days"] == 0
        assert pet["pats_today"] == 0
        assert before <= pet["adopted_at"] <= after
        assert len(pet["recent_days"]) == 7
        assert pet["recent_days"][-1]["ink"] == 0
        stored = app.state.workspace_service.snapshot()["pet"]
        assert stored["adopted_at"] == pet["adopted_at"]
        assert stored["name"] == "小墨"
        second = client.get("/api/pet").json()
        assert second["adopted_at"] == pet["adopted_at"]


def test_each_learning_event_is_one_ink_and_pats_cap_at_five(tmp_path):
    stamp = local_ms(TODAY)
    extra = {
        "sessions": [{
            "id": "session-1",
            "messages": (
                [{"id": f"u{index}", "role": "user", "created_at": stamp + index} for index in range(21)]
                + [{"id": "a1", "role": "assistant", "created_at": stamp}]
            ),
        }],
        "attempts": [{
            "id": "attempt-1",
            "completion_status": "completed",
            "completed_at": stamp,
            "feedback": [
                {"id": "f1", "correct": True, "created_at": stamp},
                {"id": "f2", "correct": True, "created_at": stamp + 1},
                {"id": "f3", "correct": False, "created_at": stamp + 2},
                {"id": "f4", "correct": None, "created_at": stamp + 3},
            ],
        }, {
            "id": "attempt-open",
            "completion_status": "in-progress",
            "completed_at": None,
            "feedback": [],
        }],
        "exams": [{"id": "exam-1", "created_at": stamp}],
        "source_versions": [
            {"id": "ready-1", "status": "ready", "processed_at": stamp, "created_at": stamp - 10},
            {"id": "busy-1", "status": "processing", "processed_at": None, "created_at": stamp},
        ],
    }
    service, workspace, _ = make_service(tmp_path, extra_data=extra)
    pet = service.get()
    assert pet["today"] == {
        "chat_messages": 21,
        "correct_answers": 2,
        "feedback_received": 4,
        "attempts_completed": 1,
        "exams_published": 1,
        "sources_ready": 1,
    }
    # 21 chat + 4 feedback + 1 attempt + 1 exam + 1 source；学习事件无日上限
    learning_ink = 21 + 4 + 1 + 1 + 1
    assert pet["ink_today"] == learning_ink
    assert pet["ink_total"] == learning_ink

    first_pat = service.pat()
    assert first_pat["pats_today"] == 1
    assert first_pat["ink_today"] == learning_ink + 1
    fifth = first_pat
    for _ in range(4):
        fifth = service.pat()
    assert fifth["pats_today"] == 5
    assert fifth["ink_today"] == learning_ink + 5
    assert fifth["recent_days"][-1]["ink"] == learning_ink + 5
    sixth = service.pat()
    assert sixth["pats_today"] == 6
    assert sixth["ink_today"] == learning_ink + 5
    assert sixth["ink_total"] == learning_ink + 5
    assert workspace.snapshot()["pet"]["pats_by_date"][TODAY] == 6


def test_streak_three_days_yesterday_continues_and_gap_resets(tmp_path):
    three_days = {
        "sessions": [{
            "id": "session-1",
            "messages": [
                {"id": "u1", "role": "user", "created_at": local_ms(TWO_DAYS_AGO)},
                {"id": "u2", "role": "user", "created_at": local_ms(YESTERDAY)},
                {"id": "u3", "role": "user", "created_at": local_ms(TODAY)},
            ],
        }],
    }
    service, _, _ = make_service(tmp_path, extra_data=three_days)
    assert service.get()["streak_days"] == 3

    yesterday_only = user_messages(YESTERDAY, 1)
    service, _, _ = make_service(tmp_path / "yesterday", extra_data=yesterday_only)
    assert service.get()["streak_days"] == 1

    gap = user_messages(TWO_DAYS_AGO, 1)
    service, _, _ = make_service(tmp_path / "gap", extra_data=gap)
    assert service.get()["streak_days"] == 0


def test_stage_thresholds_and_ink_to_next():
    assert stage_for_ink(0) == (0, 1)
    assert stage_for_ink(1) == (1, 99)
    assert stage_for_ink(99) == (1, 1)
    assert stage_for_ink(100) == (2, 200)
    assert stage_for_ink(299) == (2, 1)
    assert stage_for_ink(300) == (3, None)
    assert stage_for_ink(301) == (3, None)


def test_stage_projection_uses_one_ink_per_exam(tmp_path):
    stamp = local_ms(TODAY)
    service, _, _ = make_service(
        tmp_path,
        extra_data={"exams": [{"id": f"exam-{index}", "created_at": stamp} for index in range(100)]},
    )
    pet = service.get()
    assert pet["ink_total"] == 100
    assert pet["stage"] == 2
    assert pet["ink_to_next"] == 200


def test_badges_positive_and_negative_including_historical_streak(tmp_path):
    empty, _, _ = make_service(tmp_path / "empty")
    badges = {item["id"]: item["earned"] for item in empty.get()["badges"]}
    assert badges == {"exam_1": False, "attempt_1": False, "streak_7": False, "ink_100": False}

    historical = local_ms("2026-07-10")
    rich = {
        "exams": [{"id": "exam-1", "created_at": historical}],
        "attempts": [{"id": "attempt-1", "completed_at": historical, "completion_status": "completed", "feedback": []}],
        "sessions": [{
            "id": "session-1",
            "messages": [
                {"id": f"u{index}", "role": "user", "created_at": local_ms(f"2026-07-{day:02d}")}
                for index, day in enumerate(range(1, 8), start=1)
            ],
        }],
    }
    # 92 exams + 1 attempt + 7 historical chats = 100；今日无事件，当前 streak 为 0
    rich["exams"].extend({"id": f"exam-{index}", "created_at": historical} for index in range(2, 93))
    service, _, _ = make_service(tmp_path / "rich", extra_data=rich)
    pet = service.get()
    assert pet["streak_days"] == 0
    badges = {item["id"]: item["earned"] for item in pet["badges"]}
    assert badges["exam_1"] is True
    assert badges["attempt_1"] is True
    assert badges["streak_7"] is True
    assert pet["ink_total"] >= 100
    assert badges["ink_100"] is True
    assert [item["id"] for item in pet["badges"]] == ["exam_1", "attempt_1", "streak_7", "ink_100"]


def test_patch_validates_name_clamps_position_and_sets_hidden(tmp_path):
    client, _ = make_timed_client(tmp_path)
    with client:
        too_long = client.patch("/api/pet", json={"name": "abcdefghijklm"})
        assert too_long.status_code == 422
        blank = client.patch("/api/pet", json={"name": "   "})
        assert blank.status_code == 422
        renamed = client.patch("/api/pet", json={"name": "  墨酱  "})
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "墨酱"
        clamped_high = client.patch("/api/pet", json={"position_x": 150})
        assert clamped_high.json()["position_x"] == 100
        clamped_low = client.patch("/api/pet", json={"position_x": -3})
        assert clamped_low.json()["position_x"] == 0
        clamped_y_high = client.patch("/api/pet", json={"position_y": 160})
        assert clamped_y_high.json()["position_y"] == 100
        clamped_y_low = client.patch("/api/pet", json={"position_y": -8})
        assert clamped_y_low.json()["position_y"] == 0
        moved = client.patch("/api/pet", json={"position_y": 42})
        assert moved.json()["position_y"] == 42
        hidden = client.patch("/api/pet", json={"hidden": True})
        assert hidden.json()["hidden"] is True
        assert hidden.json()["name"] == "墨酱"
        assert hidden.json()["position_y"] == 42


def test_legacy_workspace_without_pet_key_loads(tmp_path):
    raw = {
        "schema_version": 1,
        "active_subject_id": None,
        "subjects": [],
        "models": [],
        "created_at": 1,
        "updated_at": 1,
    }
    workspace, issue = normalize_workspace(raw, now=1000)
    assert issue is None
    assert workspace["pet"]["name"] == "小墨"
    assert workspace["pet"]["adopted_at"] is None
    assert workspace["pet"]["position_y"] == 100
    assert workspace["pet"]["pats_by_date"] == {}

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "workspace.json").write_text(json.dumps(raw), encoding="utf-8")
    client, app = make_client(tmp_path)
    with client:
        assert app.state.workspace_service.snapshot()["pet"]["adopted_at"] is None
        pet = client.get("/api/pet").json()
        assert pet["name"] == "小墨"
        assert pet["stage"] == 0
        assert pet["adopted_at"] is not None


def test_pat_endpoint_and_old_pats_are_pruned(tmp_path):
    client, app = make_timed_client(tmp_path)
    with client:
        app.state.workspace_service.update_workspace(lambda workspace: {
            **workspace,
            "pet": {
                "name": "小墨",
                "adopted_at": NOW_MS,
                "position_x": 50,
                "position_y": 100,
                "hidden": False,
                "pats_by_date": {"2026-07-01": 9, TODAY: 1},
            },
        })
        pet = client.post("/api/pet/pat").json()
        assert pet["pats_today"] == 2
        assert pet["ink_today"] == 2
        stored = app.state.workspace_service.snapshot()["pet"]["pats_by_date"]
        assert "2026-07-01" not in stored
        assert stored[TODAY] == 2


def test_historical_pats_cap_and_count_as_streak_days(tmp_path):
    service, workspace, _ = make_service(tmp_path)
    workspace.update_workspace(lambda current: {
        **current,
        "pet": {
            "name": "小墨",
            "adopted_at": NOW_MS,
            "position_x": 78,
            "position_y": 100,
            "hidden": False,
            "pats_by_date": {TWO_DAYS_AGO: 9, YESTERDAY: 1},
        },
    })
    pet = service.get()
    by_date = {item["date"]: item["ink"] for item in pet["recent_days"]}
    assert by_date[TWO_DAYS_AGO] == 5
    assert by_date[YESTERDAY] == 1
    assert pet["ink_today"] == 0
    assert pet["ink_total"] == 6
    assert pet["streak_days"] == 2


def test_ink_aggregates_across_subjects(tmp_path):
    service, _, _ = make_service(
        tmp_path,
        extra_data=user_messages(TODAY, 1),
        extra_subjects=[("英语", {"exams": [{"id": "exam-en", "created_at": local_ms(TODAY)}]})],
    )
    pet = service.get()
    assert pet["ink_today"] == 1 + 1
    assert pet["today"]["chat_messages"] == 1
    assert pet["today"]["exams_published"] == 1
