from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from fastapi import status as http_status
from fastapi.exceptions import RequestValidationError

from app.api.dependencies import get_dealership_id, get_lead_service
from app.core.enums import LeadSortField, LeadSource, LeadStatus, SortOrder
from app.schemas.common import ProblemDetail
from app.schemas.lead import (
    LeadCreate,
    LeadDetailResponse,
    LeadInboxResponse,
    LeadResponse,
    LeadUpdate,
)
from app.services.lead_service import LeadService

router = APIRouter(prefix="/api/v1/leads", tags=["Leads"])


def _parse_status_filters(raw_statuses: list[str] | None) -> list[LeadStatus] | None:
    """Support both repeatable (?status=NEW&status=CONTACTED) and comma-separated (?status=NEW,CONTACTED)."""
    if not raw_statuses:
        return None

    parsed: list[LeadStatus] = []
    valid_values = ", ".join(f"'{s.value}'" for s in LeadStatus)
    for raw in raw_statuses:
        for token in raw.split(","):
            cleaned = token.strip()
            if not cleaned:
                continue
            try:
                parsed.append(LeadStatus(cleaned))
            except ValueError as exc:
                raise RequestValidationError(
                    [
                        {
                            "loc": ("query", "status"),
                            "msg": f"Input should be {valid_values}",
                            "type": "enum",
                            "input": cleaned,
                        }
                    ]
                ) from exc
    return parsed or None


@router.get(
    "",
    response_model=LeadInboxResponse,
    responses={
        400: {"model": ProblemDetail},
        422: {"model": ProblemDetail},
    },
    summary="Lead Inbox",
    description="Paginated, filterable, sortable list of sales leads scoped to the active dealership.",
)
def list_leads(
    status: list[str] | None = Query(
        default=None,
        description="Filter by lead status (repeatable or comma-separated).",
    ),
    source: LeadSource | None = Query(
        default=None, description="Filter by lead acquisition source."
    ),
    assigned_to: str | None = Query(
        default=None, description="Filter by assigned sales executive."
    ),
    search: str | None = Query(
        default=None,
        description="Case-insensitive partial match on customer name, email, or vehicle_of_interest.",
    ),
    sort_by: LeadSortField = Query(
        default=LeadSortField.CREATED_AT,
        description="Field to sort by.",
    ),
    sort_order: SortOrder = Query(
        default=SortOrder.DESC,
        description="Sort direction (asc or desc).",
    ),
    page: int = Query(default=1, ge=1, description="1-based page number."),
    page_size: int = Query(
        default=20, ge=1, le=100, description="Number of leads per page (max 100)."
    ),
    dealership_id: UUID = Depends(get_dealership_id),
    lead_service: LeadService = Depends(get_lead_service),
) -> LeadInboxResponse:
    parsed_statuses = _parse_status_filters(status)
    return lead_service.list_leads(
        dealership_id=dealership_id,
        statuses=parsed_statuses,
        source=source,
        assigned_to=assigned_to,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=LeadResponse,
    status_code=http_status.HTTP_201_CREATED,
    responses={
        400: {"model": ProblemDetail},
        422: {"model": ProblemDetail},
    },
    summary="Create Sales Lead",
    description="Ingests a new sales lead with default status=NEW, last_contacted_at=null, version=1.",
)
def create_lead(
    payload: LeadCreate,
    response: Response,
    dealership_id: UUID = Depends(get_dealership_id),
    lead_service: LeadService = Depends(get_lead_service),
) -> LeadResponse:
    created = lead_service.create_lead(
        dealership_id=dealership_id,
        payload=payload,
    )
    response.headers["Location"] = f"/api/v1/leads/{created.id}"
    return created


@router.get(
    "/{lead_id}",
    response_model=LeadDetailResponse,
    responses={
        400: {"model": ProblemDetail},
        404: {"model": ProblemDetail},
        422: {"model": ProblemDetail},
    },
    summary="Lead Details View",
    description="Returns complete lead profile and chronologically ordered activities.",
)
def get_lead_detail(
    lead_id: UUID,
    activity_sort: SortOrder = Query(
        default=SortOrder.ASC,
        description="Chronological order for activities: asc (oldest-first) or desc (newest-first).",
    ),
    dealership_id: UUID = Depends(get_dealership_id),
    lead_service: LeadService = Depends(get_lead_service),
) -> LeadDetailResponse:
    return lead_service.get_lead_detail(
        dealership_id=dealership_id,
        lead_id=lead_id,
        activity_sort=activity_sort,
    )


@router.patch(
    "/{lead_id}",
    response_model=LeadResponse,
    responses={
        400: {"model": ProblemDetail},
        404: {"model": ProblemDetail},
        409: {"model": ProblemDetail},
        422: {"model": ProblemDetail},
    },
    summary="Update Sales Lead",
    description="Partially updates lead status, assignee, or contact details with optimistic locking.",
)
def update_lead(
    lead_id: UUID,
    payload: LeadUpdate,
    dealership_id: UUID = Depends(get_dealership_id),
    lead_service: LeadService = Depends(get_lead_service),
) -> LeadResponse:
    return lead_service.update_lead(
        dealership_id=dealership_id,
        lead_id=lead_id,
        payload=payload,
    )
