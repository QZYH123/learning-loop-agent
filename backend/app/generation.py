"""Async orchestration for chat generation tasks."""
from __future__ import annotations

import asyncio
import uuid

from .domain import CHAT_COMPLETE, CHAT_FAIL, CHAT_STOP
from .model_client import ModelClientError


class GenerationManager:
    def __init__(self, service, model_client):
        self.service = service
        self.model_client = model_client
        self._generations: dict[str, asyncio.Task] = {}
        self._records: dict[str, dict] = {}

    def start(self, subject_id: str, request: dict) -> str:
        generation_id = f"generation-{uuid.uuid4().hex}"
        task = asyncio.create_task(self._run(generation_id, subject_id, request))
        self._generations[generation_id] = task
        self._records[generation_id] = {
            "subject_id": subject_id,
            "assistant_message_id": request["assistant_message_id"],
        }
        return generation_id

    def stop(self, generation_id: str) -> bool:
        task = self._generations.get(generation_id)
        if not task:
            return False
        task.cancel()
        return True

    def stop_for_subject(self, subject_id: str) -> bool:
        generation_id = next(
            (gid for gid, record in self._records.items() if record["subject_id"] == subject_id),
            None,
        )
        if not generation_id:
            return False
        return self.stop(generation_id)

    def get(self, generation_id: str) -> dict | None:
        return self._records.get(generation_id)

    def has_active_for_subject(self, subject_id: str) -> bool:
        return any(record["subject_id"] == subject_id for record in self._records.values())

    async def _run(self, generation_id: str, subject_id: str, request: dict) -> None:
        try:
            response = await self.model_client.chat(
                request["model_profile"],
                request["messages"],
            )
            self.service.dispatch(
                {
                    "type": CHAT_COMPLETE,
                    "subject_id": subject_id,
                    "message_id": request["assistant_message_id"],
                    "text": response.get("text") or "",
                }
            )
        except asyncio.CancelledError:
            self.service.dispatch(
                {
                    "type": CHAT_STOP,
                    "subject_id": subject_id,
                    "message_id": request["assistant_message_id"],
                }
            )
        except ModelClientError as exc:
            self.service.dispatch(
                {
                    "type": CHAT_FAIL,
                    "subject_id": subject_id,
                    "message_id": request["assistant_message_id"],
                    "error_code": exc.code,
                    "error_message": str(exc),
                }
            )
        except Exception as exc:  # defensive: never lose the user-visible failure
            self.service.dispatch(
                {
                    "type": CHAT_FAIL,
                    "subject_id": subject_id,
                    "message_id": request["assistant_message_id"],
                    "error_code": "MODEL_REQUEST_FAILED",
                    "error_message": str(exc) or "模型请求失败",
                }
            )
        finally:
            self._generations.pop(generation_id, None)
            self._records.pop(generation_id, None)

    async def shutdown(self) -> None:
        for task in list(self._generations.values()):
            task.cancel()
        if self._generations:
            await asyncio.gather(*list(self._generations.values()), return_exceptions=True)
