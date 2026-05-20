from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Basic health check endpoint.

    Returns a simple status object to confirm the API is running.
    """
    return {"status": "ok"}
