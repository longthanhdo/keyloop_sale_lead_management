from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import LeadSource, LeadStatus
from app.db.base import Base, UTCDateTime, utc_now

if TYPE_CHECKING:
    from app.models.activity import Activity

_LEAD_SOURCE_VALUES = ", ".join(f"'{item.value}'" for item in LeadSource)
_LEAD_STATUS_VALUES = ", ".join(f"'{item.value}'" for item in LeadStatus)


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    dealership_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=LeadStatus.NEW.value,
    )
    vehicle_of_interest: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enquiry_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(150), nullable=True)
    last_contacted_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    activities: Mapped[list["Activity"]] = relationship(
        "Activity",
        back_populates="lead",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint(
            f"source IN ({_LEAD_SOURCE_VALUES})",
            name="valid_lead_source",
        ),
        CheckConstraint(
            f"status IN ({_LEAD_STATUS_VALUES})",
            name="valid_lead_status",
        ),
        CheckConstraint("version >= 1", name="positive_version"),
        Index(
            "idx_leads_tenant_status_created",
            "dealership_id",
            "status",
            created_at.desc(),
        ),
        Index(
            "idx_leads_tenant_source_created",
            "dealership_id",
            "source",
            created_at.desc(),
        ),
        Index(
            "idx_leads_tenant_last_contacted",
            "dealership_id",
            "last_contacted_at",
        ),
        Index(
            "idx_leads_tenant_email",
            "dealership_id",
            "email",
        ),
    )
