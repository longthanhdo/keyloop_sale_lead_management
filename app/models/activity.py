from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ActivityType
from app.db.base import Base, UTCDateTime, utc_now

if TYPE_CHECKING:
    from app.models.lead import Lead

_ACTIVITY_TYPE_VALUES = ", ".join(f"'{item.value}'" for item in ActivityType)


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    lead_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
    )
    activity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    performed_by: Mapped[str] = mapped_column(String(150), nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(100), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now
    )

    lead: Mapped["Lead"] = relationship("Lead", back_populates="activities")

    __table_args__ = (
        CheckConstraint(
            f"activity_type IN ({_ACTIVITY_TYPE_VALUES})",
            name="valid_activity_type",
        ),
        Index(
            "idx_activities_lead_chronological",
            "lead_id",
            "occurred_at",
            "created_at",
        ),
    )
