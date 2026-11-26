from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app.api.v1 import activities, health, leads
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.problem_details import register_exception_handlers
from app.db.session import DatabaseManager, init_db
from app.middleware.access_log import AccessLogMiddleware
from app.middleware.correlation import CorrelationIDMiddleware
from app.middleware.tenant import TenantContextMiddleware

logger = logging.getLogger("app.main")


def create_app(
    *,
    settings: Settings | None = None,
    db_manager: DatabaseManager | None = None,
) -> FastAPI:
    """Application factory supporting isolated testing and clean lifecycle management."""
    cfg = settings or get_settings()
    configure_logging(cfg.log_level)

    manager = db_manager or DatabaseManager(cfg)

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
        init_db(manager.engine)
        logger.info(
            "app.startup",
            extra={
                "event": "app.startup",
                "environment": cfg.environment,
                "db_dialect": manager.engine.dialect.name,
            },
        )
        try:
            yield
        finally:
            logger.info("app.shutdown", extra={"event": "app.shutdown"})
            manager.dispose()

    app = FastAPI(
        title=cfg.app_name,
        version=cfg.app_version,
        description=(
            "Backend REST API for Scenario C: Sales Lead Management Tool (Demand Domain). "
            "Implements Lead Inbox, Lead Details View, and Atomic Activity Logging with "
            "RFC 7807 errors, multi-tenant readiness, and zero-PII structured logging."
        ),
        lifespan=lifespan,
    )
    app.state.settings = cfg
    app.state.db_manager = manager

    # Register middleware (LIFO execution: CorrelationID -> AccessLog -> Tenant -> Router)
    app.add_middleware(
        TenantContextMiddleware,
        default_dealership_id=cfg.default_dealership_id,
    )
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(CorrelationIDMiddleware)

    # Register RFC 7807 exception handlers
    register_exception_handlers(app)

    # Register routers
    app.include_router(health.router)
    app.include_router(leads.router)
    app.include_router(activities.router)

    return app


app = create_app()
