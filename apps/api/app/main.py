import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import DEFAULT_SECRET_KEY, settings
from app.core.errors import register_exception_handlers
from app.core.logging_config import configure_logging
from app.db.base import Base
from app.db.init_db import seed_data
from app.db.session import SessionLocal, engine
from app.models import entities  # noqa: F401 — register models

logger = logging.getLogger(__name__)

_PRODUCTION_ENVIRONMENTS = {"staging", "production"}
_SEED_ENVIRONMENTS = {"development", "test"}


def _ensure_sqlite_schema() -> None:
    """Local SQLite: create tables when not using Alembic."""
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)


def _validate_runtime_settings() -> None:
    environment = settings.environment.lower()
    if environment in _PRODUCTION_ENVIRONMENTS and settings.secret_key == DEFAULT_SECRET_KEY:
        raise RuntimeError("SECRET_KEY must be set to a non-default value outside development.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_runtime_settings()
    _ensure_sqlite_schema()
    if settings.environment.lower() in _SEED_ENVIRONMENTS:
        with SessionLocal() as db:
            seed_data(db)
    yield


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title=settings.app_name,
        version=settings.api_version,
        description=(
            "TalkBI backend: JWT auth, data sources, theme libraries, "
            "chat-driven charts, chart library, and dashboards."
        ),
        lifespan=lifespan,
        openapi_tags=[
            {"name": "meta", "description": "Health and service metadata"},
            {"name": "auth", "description": "Login and tokens"},
            {"name": "users", "description": "Current user profile"},
            {"name": "data-sources", "description": "Data source CRUD and Excel upload"},
            {"name": "theme-libraries", "description": "Semantic theme configuration"},
            {"name": "chat", "description": "Natural language to chart"},
            {"name": "charts", "description": "Saved chart library"},
            {"name": "dashboards", "description": "Dashboards and layout"},
        ],
    )
    register_exception_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/meta", tags=["meta"])
    def meta() -> dict:
        """Non-sensitive runtime metadata for local debugging."""
        return {
            "llm_mock_mode": settings.llm_mock_mode,
            "ollama_base_url": settings.ollama_base_url,
            "ollama_model": settings.ollama_model,
            "database_dialect": engine.dialect.name,
            "cors_origins": settings.cors_origins,
        }

    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
