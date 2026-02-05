from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import ocr_routes, meta_routes
from app.core.config import settings
from app.core.telemetry import RequestTelemetryMiddleware


def create_app() -> FastAPI:
    app = FastAPI(title=settings.PROJECT_NAME)

    # Structured request logging + request_id
    app.add_middleware(RequestTelemetryMiddleware)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    # Existing OCR APIs remain under /api/v1
    app.include_router(ocr_routes.router, prefix=settings.API_V1_STR)

    # V1 meta endpoints (non-breaking additive)
    app.include_router(meta_routes.router)
    return app


app = create_app()
