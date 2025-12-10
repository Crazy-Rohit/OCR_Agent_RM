from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api import ocr_routes


def create_app() -> FastAPI:
    app = FastAPI(title=settings.PROJECT_NAME)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check
    @app.get("/health")
    def health():
        return {"status": "ok"}

    # Include OCR routes under /api/v1
    app.include_router(
        ocr_routes.router,
        prefix=settings.API_V1_STR,
    )

    return app


app = create_app()
