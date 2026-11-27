from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status

from app.api.dependencies import get_activity_service, get_dealership_id
from app.core.enums import SortOrder
from app.schemas.activity import (
    ActivityCreate,
    ActivityCreatedResponse,
    ActivityFeedResponse,
)
from app.schemas.common import ProblemDetail
from app.services.activity_service import ActivityService

router = APIRouter(prefix="/api/v1/leads/{lead_id}/activities", tags=["Activities"])


@router.post(
    "",
    response_model=ActivityCreatedResponse,
    status_code=http_status.HTTP_201_CREATED,
    responses={
        400: {"model": ProblemDetail},
        404: {"model": ProblemDetail},
        409: {"model": ProblemDetail},
        422: {"model": ProblemDetail},
    },
    summary="Log Follow-Up Activity",
    description=(
        "Appends an immutable activity record and atomically updates lead status, "
        "last_contacted_at, updated_at, and version within a single transaction."
    ),
)
def log_activity(
    lead_id: UUID,
    payload: ActivityCreate,
    dealership_id: UUID = Depends(get_dealership_id),
    activity_service: ActivityService = Depends(get_activity_service),
) -> ActivityCreatedResponse:
    return activity_service.log_activity(
        dealership_id=dealership_id,
        lead_id=lead_id,
        payload=payload,
    )


@router.get(
    "",
    response_model=ActivityFeedResponse,
    responses={
        400: {"model": ProblemDetail},
        404: {"model": ProblemDetail},
        422: {"model": ProblemDetail},
    },
    summary="List Lead Activities",
    description="Paginated chronological activity feed for a specific lead.",
)
def list_activities(
    lead_id: UUID,
    activity_sort: SortOrder = Query(
        default=SortOrder.ASC,
        description="Chronological order: asc (oldest-first) or desc (newest-first).",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    dealership_id: UUID = Depends(get_dealership_id),
    activity_service: ActivityService = Depends(get_activity_service),
) -> ActivityFeedResponse:
    return activity_service.list_activities(
        dealership_id=dealership_id,
        lead_id=lead_id,
        activity_sort=activity_sort,
        page=page,
        page_size=page_size,
    )
