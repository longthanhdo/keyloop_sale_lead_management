import math
from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, PlainSerializer


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _serialize_utc(value: datetime) -> str:
    return _ensure_utc(value).isoformat().replace("+00:00", "Z")


UTCDatetime = Annotated[
    datetime,
    AfterValidator(_ensure_utc),
    PlainSerializer(_serialize_utc, return_type=str, when_used="json"),
]


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool

    @classmethod
    def from_query(
        cls, *, page: int, page_size: int, total_items: int
    ) -> "PaginationMeta":
        total_pages = math.ceil(total_items / page_size) if total_items > 0 else 0
        return cls(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1 and total_pages > 0,
        )


class ValidationErrorItem(BaseModel):
    field: str
    message: str


class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details schema for OpenAPI documentation."""

    model_config = ConfigDict(extra="allow")

    type: str
    title: str
    status: int
    detail: str
    instance: str
    correlation_id: str | None = None
    errors: list[ValidationErrorItem] | None = None


class HealthLiveResponse(BaseModel):
    status: str = "live"


class HealthReadyResponse(BaseModel):
    status: str = "ready"
    database: str = "connected"
