"""HTTP routes for the workspace desk pet."""
from __future__ import annotations

from fastapi import APIRouter

from .api_models import ErrorResponse, Pet, PetPatch


def create_pet_router(pet_service) -> APIRouter:
    router = APIRouter()

    @router.get("/api/pet", operation_id="getPet", response_model=Pet)
    def get_pet():
        return pet_service.get()

    @router.patch(
        "/api/pet",
        operation_id="updatePet",
        response_model=Pet,
        responses={422: {"model": ErrorResponse}},
    )
    def update_pet(payload: PetPatch):
        return pet_service.update(payload.model_dump(exclude_unset=True))

    @router.post("/api/pet/pat", operation_id="patPet", response_model=Pet)
    def pat_pet():
        return pet_service.pat()

    return router
