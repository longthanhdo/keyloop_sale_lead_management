from collections.abc import Generator
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.activity_service import ActivityService
from app.services.lead_service import LeadService


def get_db_session(request: Request) -> Generator[Session, None, None]:
    db_manager = request.app.state.db_manager
    yield from db_manager.get_session()


def get_dealership_id(request: Request) -> UUID:
    dealership_id: UUID | None = getattr(request.state, "dealership_id", None)
    if dealership_id is not None:
        return dealership_id
    return get_settings().default_dealership_id


def get_lead_service(
    session: Session = Depends(get_db_session),
) -> LeadService:
    return LeadService(session)


def get_activity_service(
    session: Session = Depends(get_db_session),
) -> ActivityService:
    return ActivityService(session)
