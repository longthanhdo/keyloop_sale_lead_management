from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.enums import LeadSource, LeadStatus
from app.schemas.activity import ActivityResponse
from app.schemas.common import PaginationMeta, UTCDatetime


class LeadCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=30)
    source: LeadSource = LeadSource.DEALER_WEBSITE
    vehicle_of_interest: str | None = Field(default=None, max_length=255)
    enquiry_notes: str | None = None
    assigned_to: str | None = Field(default=None, max_length=150)

    @field_validator(
        "phone", "vehicle_of_interest", "enquiry_notes", "assigned_to", mode="before"
    )
    @classmethod
    def _empty_to_none(cls, value: str | None) -> str | None:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class LeadUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    version: int = Field(
        ...,
        ge=1,
        description="Current lead version for optimistic concurrency control.",
    )
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    vehicle_of_interest: str | None = Field(default=None, max_length=255)
    enquiry_notes: str | None = None
    assigned_to: str | None = Field(default=None, max_length=150)
    status: LeadStatus | None = None

    @field_validator(
        "phone", "vehicle_of_interest", "enquiry_notes", "assigned_to", mode="before"
    )
    @classmethod
    def _empty_to_none(cls, value: str | None) -> str | None:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class LeadInboxItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dealership_id: UUID
    first_name: str
    last_name: str
    email: str
    phone: str | None
    source: LeadSource
    status: LeadStatus
    vehicle_of_interest: str | None
    assigned_to: str | None
    last_contacted_at: UTCDatetime | None
    version: int
    created_at: UTCDatetime
    updated_at: UTCDatetime


class LeadResponse(LeadInboxItem):
    enquiry_notes: str | None


class LeadDetailResponse(LeadResponse):
    activities: list[ActivityResponse] = Field(default_factory=list)


class LeadInboxResponse(BaseModel):
    items: list[LeadInboxItem]
    pagination: PaginationMeta
