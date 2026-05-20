from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import router


def create_app() -> FastAPI:
    """Application factory for the Image Text Translation API.

    Creates the FastAPI instance and registers all route handlers.
    No business logic lives here — this is purely app assembly.
    """
    application = FastAPI(
        title="Image Text Translation Pipeline",
        description=(
            "A stateless REST API that accepts a product image containing "
            "text in a foreign language and returns a version with all "
            "detected text replaced by its English translation."
        ),
        version="0.1.0",
    )
    application.include_router(router)
    return application


app = create_app()
