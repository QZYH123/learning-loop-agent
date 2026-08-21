"""Workspace-level desk pet: persisted display state plus a read-only ink projection."""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import date, timedelta

from .domain import DEFAULT_PET_NAME, PET_NAME_MAX_LENGTH, _clamp_pet_position, _normalize_pet
from .learning import LearningError

PATS_RETENTION_DAYS = 30
PAT_DAILY_CAP = 5


def local_date_from_ms(ms: int) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ms / 1000.0))


def stage_for_ink(ink_total: int) -> tuple[int, int | None]:
    if ink_total >= 300:
        return 3, None
    if ink_total >= 100:
        return 2, 300 - ink_total
    if ink_total >= 1:
        return 1, 100 - ink_total
    return 0, 1


def current_streak(event_dates: set[str], today: str) -> int:
    today_d = date.fromisoformat(today)
    yesterday = (today_d - timedelta(days=1)).isoformat()
    if today in event_dates:
        start = today_d
    elif yesterday in event_dates:
        start = today_d - timedelta(days=1)
    else:
        return 0
    streak = 0
    cursor = start
    while cursor.isoformat() in event_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def longest_streak(event_dates: set[str]) -> int:
    if not event_dates:
        return 0
    ordered = sorted(date.fromisoformat(item) for item in event_dates)
    best = 1
    run = 1
    previous = ordered[0]
    for current in ordered[1:]:
        if current == previous + timedelta(days=1):
            run += 1
            best = max(best, run)
        else:
            run = 1
        previous = current
    return best


def _is_timestamp(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _prune_pats(pats: dict, today: str) -> dict:
    today_d = date.fromisoformat(today)
    kept = {}
    for key, value in pats.items():
        try:
            day = date.fromisoformat(key)
        except ValueError:
            continue
        delta = (today_d - day).days
        if 0 <= delta < PATS_RETENTION_DAYS:
            kept[key] = int(value)
    return kept


def _collect_events(workspace: dict) -> list[tuple[str, str]]:
    events = []
    for subject in workspace.get("subjects") or []:
        if not isinstance(subject, dict):
            continue
        data = subject.get("data")
        if not isinstance(data, dict):
            continue
        for session in data.get("sessions") or []:
            if not isinstance(session, dict):
                continue
            for message in session.get("messages") or []:
                if not isinstance(message, dict) or message.get("role") != "user":
                    continue
                created_at = message.get("created_at")
                if _is_timestamp(created_at):
                    events.append(("chat", local_date_from_ms(int(created_at))))
        for attempt in data.get("attempts") or []:
            if not isinstance(attempt, dict):
                continue
            for feedback in attempt.get("feedback") or []:
                if not isinstance(feedback, dict):
                    continue
                created_at = feedback.get("created_at")
                if not _is_timestamp(created_at):
                    continue
                kind = "correct" if feedback.get("correct") is True else "other_feedback"
                events.append((kind, local_date_from_ms(int(created_at))))
            completed_at = attempt.get("completed_at")
            if _is_timestamp(completed_at):
                events.append(("attempt", local_date_from_ms(int(completed_at))))
        for exam in data.get("exams") or []:
            if not isinstance(exam, dict):
                continue
            created_at = exam.get("created_at")
            if _is_timestamp(created_at):
                events.append(("exam", local_date_from_ms(int(created_at))))
        for version in data.get("source_versions") or []:
            if not isinstance(version, dict) or version.get("status") != "ready":
                continue
            timestamp = version.get("processed_at")
            if not _is_timestamp(timestamp):
                timestamp = version.get("created_at")
            if _is_timestamp(timestamp):
                events.append(("source", local_date_from_ms(int(timestamp))))
    return events


def project_ink(workspace: dict, today: str) -> dict:
    counts = defaultdict(lambda: defaultdict(int))
    for kind, day in _collect_events(workspace):
        counts[day][kind] += 1

    pet = _normalize_pet(workspace.get("pet"))
    for day, value in (pet.get("pats_by_date") or {}).items():
        counts[day]["pat"] += int(value)

    ink_by_date = {}
    for day, kinds in counts.items():
        ink_by_date[day] = (
            kinds["chat"]
            + kinds["correct"]
            + kinds["other_feedback"]
            + kinds["attempt"]
            + kinds["exam"]
            + kinds["source"]
            + min(kinds["pat"], PAT_DAILY_CAP)
        )

    today_counts = counts[today]
    ink_total = sum(ink_by_date.values())
    ink_today = ink_by_date.get(today, 0)
    stage, ink_to_next = stage_for_ink(ink_total)
    event_dates = {day for day, ink in ink_by_date.items() if ink > 0}
    today_d = date.fromisoformat(today)
    recent_days = []
    for offset in range(6, -1, -1):
        day = (today_d - timedelta(days=offset)).isoformat()
        recent_days.append({"date": day, "ink": ink_by_date.get(day, 0)})
    exam_count = sum(kinds["exam"] for kinds in counts.values())
    attempt_count = sum(kinds["attempt"] for kinds in counts.values())
    badges = [
        {"id": "exam_1", "earned": exam_count >= 1},
        {"id": "attempt_1", "earned": attempt_count >= 1},
        {"id": "streak_7", "earned": longest_streak(event_dates) >= 7},
        {"id": "ink_100", "earned": ink_total >= 100},
    ]
    return {
        "ink_total": ink_total,
        "ink_today": ink_today,
        "stage": stage,
        "ink_to_next": ink_to_next,
        "streak_days": current_streak(event_dates, today),
        "pats_today": int((pet.get("pats_by_date") or {}).get(today, 0)),
        "today": {
            "chat_messages": today_counts["chat"],
            "correct_answers": today_counts["correct"],
            "feedback_received": today_counts["correct"] + today_counts["other_feedback"],
            "attempts_completed": today_counts["attempt"],
            "exams_published": today_counts["exam"],
            "sources_ready": today_counts["source"],
        },
        "recent_days": recent_days,
        "badges": badges,
    }


class PetService:
    def __init__(self, workspace_service, now=None):
        self.workspace_service = workspace_service
        self.now = now or (lambda: int(time.time() * 1000))

    def _now_ms(self) -> int:
        value = self.now()
        return int(value)

    def _today(self) -> str:
        return local_date_from_ms(self._now_ms())

    def _mutate(self, *, adopt=False, patch=None, pat=False) -> dict:
        now_ms = self._now_ms()
        today = local_date_from_ms(now_ms)

        def update(workspace):
            pet = _normalize_pet(workspace.get("pet"))
            if adopt and pet.get("adopted_at") is None:
                pet["adopted_at"] = now_ms
            if patch:
                if "name" in patch and patch["name"] is not None:
                    name = patch["name"].strip() if isinstance(patch["name"], str) else ""
                    if not name or len(name) > PET_NAME_MAX_LENGTH:
                        raise LearningError(422, "VALIDATION_FAILED", "名字需为 1–12 个字符")
                    pet["name"] = name
                if "position_x" in patch and patch["position_x"] is not None:
                    pet["position_x"] = _clamp_pet_position(patch["position_x"])
                if "position_y" in patch and patch["position_y"] is not None:
                    pet["position_y"] = _clamp_pet_position(patch["position_y"])
                if "hidden" in patch and patch["hidden"] is not None:
                    pet["hidden"] = bool(patch["hidden"])
            pats = _prune_pats(pet.get("pats_by_date") or {}, today)
            if pat:
                pats[today] = pats.get(today, 0) + 1
            pet["pats_by_date"] = pats
            workspace["pet"] = pet
            return workspace

        return self.workspace_service.update_workspace(update)

    def _view(self, workspace: dict) -> dict:
        pet = _normalize_pet(workspace.get("pet"))
        projection = project_ink(workspace, self._today())
        return {
            "name": pet.get("name") or DEFAULT_PET_NAME,
            "adopted_at": pet.get("adopted_at"),
            "position_x": pet.get("position_x"),
            "position_y": pet.get("position_y"),
            "hidden": bool(pet.get("hidden")),
            **projection,
        }

    def get(self) -> dict:
        workspace = self._mutate(adopt=True)
        return self._view(workspace)

    def update(self, patch: dict) -> dict:
        workspace = self._mutate(adopt=True, patch=patch)
        return self._view(workspace)

    def pat(self) -> dict:
        workspace = self._mutate(adopt=True, pat=True)
        return self._view(workspace)
