import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.core.exceptions import ServiceUnavailableError
from app.schemas.common import HealthLiveResponse, HealthReadyResponse, ProblemDetail

logger = logging.getLogger("app.health")

router = APIRouter(prefix="/health", tags=["Health"])


@router.get(
    "/live",
    response_model=HealthLiveResponse,
    summary="Liveness Probe",
    description="Confirms the application process is responsive without external I/O.",
)
def health_live() -> HealthLiveResponse:
    return HealthLiveResponse(status="live")


@router.get(
    "/ready",
    response_model=HealthReadyResponse,
    responses={503: {"model": ProblemDetail, "description": "Database unavailable"}},
    summary="Readiness Probe",
    description="Confirms active database connectivity by executing SELECT 1.",
)
def health_ready(session: Session = Depends(get_db_session)) -> HealthReadyResponse:
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:
        logger.error(
            "health.ready.failed",
            extra={
                "event": "health.ready.failed",
                "exception_class": exc.__class__.__name__,
            },
        )
        raise ServiceUnavailableError(
            "Database readiness check failed; service is not ready to accept traffic."
        ) from exc

    return HealthReadyResponse(status="ready", database="connected")
