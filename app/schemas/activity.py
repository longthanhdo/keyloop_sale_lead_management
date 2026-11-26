from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import ActivityType, LeadStatus
from app.schemas.common import PaginationMeta, UTCDatetime


class ActivityCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    activity_type: ActivityType
    summary: str = Field(..., min_length=1, max_length=255)
    notes: str | None = None
    performed_by: str = Field(..., min_length=1, max_length=150)
    outcome: str | None = Field(default=None, max_length=100)
    occurred_at: UTCDatetime | None = None
    new_lead_status: LeadStatus | None = None

    @field_validator("outcome", "notes", mode="before")
    @classmethod
    def _empty_string_to_none(cls, value: str | None) -> str | None:
        if isinstance(value, str) and not value.strip():
            return None
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
