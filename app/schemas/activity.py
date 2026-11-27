from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.core.enums import ActivityType, LeadStatus
from app.schemas.common import PaginationMeta, UTCDatetime, _ensure_utc

# Allowance for clocks on client devices running slightly ahead of the server.
MAX_FUTURE_SKEW = timedelta(minutes=5)

# Input-only type: rejects a datetime without a time zone (422), then converts to UTC.
# Kept separate from UTCDatetime, which is also used when reading stored values.
AwareUTCDatetime = Annotated[AwareDatetime, AfterValidator(_ensure_utc)]


class ActivityCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    activity_type: ActivityType
    summary: str = Field(..., min_length=1, max_length=255)
    notes: str | None = None
    performed_by: str = Field(..., min_length=1, max_length=150)
    outcome: str | None = Field(default=None, max_length=100)
    occurred_at: AwareUTCDatetime | None = None
    new_lead_status: LeadStatus | None = None

    @field_validator("outcome", "notes", mode="before")
    @classmethod
    def _empty_string_to_none(cls, value: str | None) -> str | None:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("occurred_at")
    @classmethod
    def _reject_future_occurred_at(cls, value: datetime | None) -> datetime | None:
        if value is not None and value > datetime.now(UTC) + MAX_FUTURE_SKEW:
            raise ValueError("occurred_at cannot be in the future")
        return value


class ActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lead_id: UUID
    activity_type: ActivityType
    summary: str
    notes: str | None
    performed_by: str
    outcome: str | None
    occurred_at: UTCDatetime
    created_at: UTCDatetime


class LeadSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: LeadStatus
    last_contacted_at: UTCDatetime | None
    updated_at: UTCDatetime
    version: int


class ActivityCreatedResponse(BaseModel):
    activity: ActivityResponse
    lead_snapshot: LeadSnapshot


class ActivityFeedResponse(BaseModel):
    items: list[ActivityResponse]
    pagination: PaginationMeta
