"""Seed realistic automotive dealership leads and chronological activities.

Usage:
    python -m scripts.seed           # Idempotent seed (skips existing deterministic IDs)
    python -m scripts.seed --reset   # Clears existing tables and re-seeds fresh data
"""

import argparse
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete

from app.core.config import get_settings
from app.core.enums import ActivityType, LeadSource, LeadStatus
from app.db.session import DatabaseManager, init_db
from app.models.activity import Activity
from app.models.lead import Lead

DEFAULT_DEALER_ID = UUID("11111111-1111-4111-8111-111111111111")
SECONDARY_DEALER_ID = UUID("22222222-2222-4222-8222-222222222222")

# Deterministic UUIDs for reproducible README curl walkthroughs
LEAD_OLIVER_ID = UUID("8f14e45f-ea9a-4c6e-9b2a-1d3c4b5a6e7f")
LEAD_AMELIA_ID = UUID("a2f3c4d5-1111-4222-8333-444444444401")
LEAD_LIAM_ID = UUID("a2f3c4d5-1111-4222-8333-444444444402")
LEAD_SOPHIE_ID = UUID("a2f3c4d5-1111-4222-8333-444444444403")
LEAD_HARRY_ID = UUID("a2f3c4d5-1111-4222-8333-444444444404")
LEAD_CHLOE_ID = UUID("a2f3c4d5-1111-4222-8333-444444444405")
LEAD_NOAH_ID = UUID("a2f3c4d5-1111-4222-8333-444444444406")
LEAD_ISLA_ID = UUID("a2f3c4d5-1111-4222-8333-444444444407")
LEAD_OTHER_DEALER_ID = UUID("b9e8d7c6-2222-4333-8444-555555555501")


def build_seed_dataset() -> tuple[list[Lead], list[Activity]]:
    base = datetime(2026, 11, 20, 9, 0, 0, tzinfo=UTC)

    leads = [
        # 1. TEST_DRIVE_SCHEDULED — rich multi-step history (matches SDD Section 5.3)
        Lead(
            id=LEAD_OLIVER_ID,
            dealership_id=DEFAULT_DEALER_ID,
            first_name="Oliver",
            last_name="Bennett",
            email="oliver.bennett@example.co.uk",
            phone="+447700900123",
            source=LeadSource.DEALER_WEBSITE.value,
            status=LeadStatus.TEST_DRIVE_SCHEDULED.value,
            vehicle_of_interest="2025 Audi Q4 e-tron 45 S Line",
            enquiry_notes="Interested in PCP finance options and part-exchange for a 2021 Golf.",
            assigned_to="sarah.jenkins@keyloop-dealer.co.uk",
            last_contacted_at=base + timedelta(days=3, hours=5),
            version=3,
            created_at=base + timedelta(days=3),
            updated_at=base + timedelta(days=3, hours=5, seconds=5),
        ),
        # 2. NEW — untouched hot website enquiry (for SLA triage / auto-transition testing)
        Lead(
            id=LEAD_AMELIA_ID,
            dealership_id=DEFAULT_DEALER_ID,
            first_name="Amelia",
            last_name="Clarke",
            email="amelia.clarke@example.co.uk",
            phone="+447700900456",
            source=LeadSource.DEALER_WEBSITE.value,
            status=LeadStatus.NEW.value,
            vehicle_of_interest="2025 Volvo EX30 Twin Motor",
            enquiry_notes="Looking to book a weekend test drive and compare home charger bundles.",
            assigned_to=None,
            last_contacted_at=None,
            version=1,
            created_at=base + timedelta(days=3, hours=6),
            updated_at=base + timedelta(days=3, hours=6),
        ),
        # 3. NEW — Auto Trader enquiry awaiting first outreach
        Lead(
            id=LEAD_LIAM_ID,
            dealership_id=DEFAULT_DEALER_ID,
            first_name="Liam",
            last_name="Patel",
            email="liam.patel@example.co.uk",
            phone="+447700900789",
            source=LeadSource.AUTO_TRADER.value,
            status=LeadStatus.NEW.value,
            vehicle_of_interest="2024 BMW 320i M Sport",
            enquiry_notes="Asking whether full BMW service history is available.",
            assigned_to="marcus.reed@keyloop-dealer.co.uk",
            last_contacted_at=None,
            version=1,
            created_at=base + timedelta(days=3, hours=4, minutes=30),
            updated_at=base + timedelta(days=3, hours=4, minutes=30),
        ),
        # 4. CONTACTED — initial voicemail & follow-up SMS
        Lead(
            id=LEAD_SOPHIE_ID,
            dealership_id=DEFAULT_DEALER_ID,
            first_name="Sophie",
            last_name="Williams",
            email="sophie.williams@example.co.uk",
            phone="+447700900234",
            source=LeadSource.CARWOW.value,
            status=LeadStatus.CONTACTED.value,
            vehicle_of_interest="2025 Volkswagen ID.4 Pro Match",
            enquiry_notes="Requested Carwow cash vs PCH lease comparison.",
            assigned_to="sarah.jenkins@keyloop-dealer.co.uk",
            last_contacted_at=base + timedelta(days=2, hours=3, minutes=15),
            version=2,
            created_at=base + timedelta(days=2),
            updated_at=base + timedelta(days=2, hours=3, minutes=20),
        ),
        # 5. QUALIFIED — budget confirmed, evaluating trim options
        Lead(
            id=LEAD_HARRY_ID,
            dealership_id=DEFAULT_DEALER_ID,
            first_name="Harry",
            last_name="Thompson",
            email="harry.thompson@example.co.uk",
            phone="+447700900567",
            source=LeadSource.PHONE_ENQUIRY.value,
            status=LeadStatus.QUALIFIED.value,
            vehicle_of_interest="2025 Mercedes-Benz EQB 300 AMG Line",
            enquiry_notes="Needs 7-seat electric SUV before March school holiday.",
            assigned_to="marcus.reed@keyloop-dealer.co.uk",
            last_contacted_at=base + timedelta(days=1, hours=7),
            version=3,
            created_at=base + timedelta(days=1),
            updated_at=base + timedelta(days=1, hours=7, minutes=10),
        ),
        # 6. NEGOTIATION — finance quote sent, reviewing part-exchange
        Lead(
            id=LEAD_CHLOE_ID,
            dealership_id=DEFAULT_DEALER_ID,
            first_name="Chloe",
            last_name="Davies",
            email="chloe.davies@example.co.uk",
            phone="+447700900890",
            source=LeadSource.OEM_PORTAL.value,
            status=LeadStatus.NEGOTIATION.value,
            vehicle_of_interest="2025 Range Rover Evoque P270e Dynamic SE",
            enquiry_notes="Comparing 36-month vs 48-month PCP terms.",
            assigned_to="sarah.jenkins@keyloop-dealer.co.uk",
            last_contacted_at=base + timedelta(days=2, hours=6),
            version=4,
            created_at=base,
            updated_at=base + timedelta(days=2, hours=6, minutes=2),
        ),
        # 7. CONVERTED — deal won with post-sale handover note
        Lead(
            id=LEAD_NOAH_ID,
            dealership_id=DEFAULT_DEALER_ID,
            first_name="Noah",
            last_name="Evans",
            email="noah.evans@example.co.uk",
            phone="+447700900321",
            source=LeadSource.WALK_IN.value,
            status=LeadStatus.CONVERTED.value,
            vehicle_of_interest="2025 Porsche Taycan 4S",
            enquiry_notes="Visited showroom with partner; ready for immediate stock delivery.",
            assigned_to="marcus.reed@keyloop-dealer.co.uk",
            last_contacted_at=base + timedelta(days=2, hours=4),
            version=5,
            created_at=base - timedelta(days=2),
            updated_at=base + timedelta(days=2, hours=5),
        ),
        # 8. LOST — declined due to delivery lead time
        Lead(
            id=LEAD_ISLA_ID,
            dealership_id=DEFAULT_DEALER_ID,
            first_name="Isla",
            last_name="Roberts",
            email="isla.roberts@example.co.uk",
            phone="+447700900654",
            source=LeadSource.SOCIAL_MEDIA.value,
            status=LeadStatus.LOST.value,
            vehicle_of_interest="2025 Ford Puma ST-Line X",
            enquiry_notes="Clicked Instagram winter offer ad.",
            assigned_to="sarah.jenkins@keyloop-dealer.co.uk",
            last_contacted_at=base + timedelta(hours=6),
            version=3,
            created_at=base - timedelta(days=1),
            updated_at=base + timedelta(hours=6, minutes=5),
        ),
        # 9. Secondary dealership lead — demonstrates multi-tenant isolation
        Lead(
            id=LEAD_OTHER_DEALER_ID,
            dealership_id=SECONDARY_DEALER_ID,
            first_name="George",
            last_name="Walker",
            email="george.walker@example.co.uk",
            phone="+447700900999",
            source=LeadSource.DEALER_WEBSITE.value,
            status=LeadStatus.NEW.value,
            vehicle_of_interest="2025 Kia EV6 GT-Line S",
            enquiry_notes="Enquiry routed to North London dealership branch.",
            assigned_to="alex.morgan@north-dealer.co.uk",
            last_contacted_at=None,
            version=1,
            created_at=base + timedelta(days=3, hours=1),
            updated_at=base + timedelta(days=3, hours=1),
        ),
    ]

    activities = [
        # Oliver Bennett timeline (chronological with internal note)
        Activity(
            id=UUID("a1b2c3d4-0001-4000-8000-000000000001"),
            lead_id=LEAD_OLIVER_ID,
            activity_type=ActivityType.CALL.value,
            summary="Called customer — discussed Q4 e-tron availability",
            notes="Confirmed blue metallic is in stock. Customer requested PCP illustration.",
            performed_by="sarah.jenkins@keyloop-dealer.co.uk",
            outcome="CONNECTED",
            occurred_at=base + timedelta(days=3, hours=1, minutes=15),
            created_at=base + timedelta(days=3, hours=1, minutes=17),
        ),
        Activity(
            id=UUID("a1b2c3d4-0002-4000-8000-000000000002"),
            lead_id=LEAD_OLIVER_ID,
            activity_type=ActivityType.NOTE.value,
            summary="Checked part-exchange CAP valuation for 2021 VW Golf",
            notes="Provisional trade-in valuation £14,500 subject to physical inspection.",
            performed_by="sarah.jenkins@keyloop-dealer.co.uk",
            outcome=None,
            occurred_at=base + timedelta(days=3, hours=2, minutes=30),
            created_at=base + timedelta(days=3, hours=2, minutes=30),
        ),
        Activity(
            id=UUID("a1b2c3d4-0003-4000-8000-000000000003"),
            lead_id=LEAD_OLIVER_ID,
            activity_type=ActivityType.TEST_DRIVE_SCHEDULED.value,
            summary="Scheduled test drive for Saturday at 11:00 AM",
            notes="Booked demonstrator vehicle Reg: KL25 EVX. Sent calendar invite.",
            performed_by="sarah.jenkins@keyloop-dealer.co.uk",
            outcome="BOOKED",
            occurred_at=base + timedelta(days=3, hours=5),
            created_at=base + timedelta(days=3, hours=5, seconds=5),
        ),
        # Sophie Williams timeline
        Activity(
            id=UUID("a1b2c3d4-0004-4000-8000-000000000004"),
            lead_id=LEAD_SOPHIE_ID,
            activity_type=ActivityType.CALL.value,
            summary="Initial outreach call — left voicemail",
            notes="Introduced dealership EV specialist team and offered callback slots.",
            performed_by="sarah.jenkins@keyloop-dealer.co.uk",
            outcome="VOICEMAIL",
            occurred_at=base + timedelta(days=2, hours=1),
            created_at=base + timedelta(days=2, hours=1, minutes=5),
        ),
        Activity(
            id=UUID("a1b2c3d4-0005-4000-8000-000000000005"),
            lead_id=LEAD_SOPHIE_ID,
            activity_type=ActivityType.SMS.value,
            summary="Sent follow-up SMS with direct booking link",
            notes="Customer replied asking to talk tomorrow morning at 10:00.",
            performed_by="sarah.jenkins@keyloop-dealer.co.uk",
            outcome="REPLIED",
            occurred_at=base + timedelta(days=2, hours=3, minutes=15),
            created_at=base + timedelta(days=2, hours=3, minutes=20),
        ),
        # Harry Thompson timeline (includes retroactive call logging)
        Activity(
            id=UUID("a1b2c3d4-0006-4000-8000-000000000006"),
            lead_id=LEAD_HARRY_ID,
            activity_type=ActivityType.CALL.value,
            summary="Inbound qualification call — confirmed 7-seat budget",
            notes="Budget £580/month PCP with £5k deposit. Logged 20 mins after call.",
            performed_by="marcus.reed@keyloop-dealer.co.uk",
            outcome="QUALIFIED",
            occurred_at=base + timedelta(days=1, hours=2),
            created_at=base + timedelta(days=1, hours=2, minutes=20),
        ),
        Activity(
            id=UUID("a1b2c3d4-0007-4000-8000-000000000007"),
            lead_id=LEAD_HARRY_ID,
            activity_type=ActivityType.EMAIL.value,
            summary="Sent EQB 300 brochure and stock list",
            notes="Highlighted Cosmos Black and Mountain Grey units in group stock.",
            performed_by="marcus.reed@keyloop-dealer.co.uk",
            outcome="SENT",
            occurred_at=base + timedelta(days=1, hours=7),
            created_at=base + timedelta(days=1, hours=7, minutes=10),
        ),
        # Chloe Davies timeline
        Activity(
            id=UUID("a1b2c3d4-0008-4000-8000-000000000008"),
            lead_id=LEAD_CHLOE_ID,
            activity_type=ActivityType.MEETING.value,
            summary="Showroom consultation and vehicle walkaround",
            notes="Customer loved Santorini Black interior specification.",
            performed_by="sarah.jenkins@keyloop-dealer.co.uk",
            outcome="COMPLETED",
            occurred_at=base + timedelta(days=1, hours=4),
            created_at=base + timedelta(days=1, hours=4, minutes=15),
        ),
        Activity(
            id=UUID("a1b2c3d4-0009-4000-8000-000000000009"),
            lead_id=LEAD_CHLOE_ID,
            activity_type=ActivityType.QUOTE_SENT.value,
            summary="Sent revised 48-month PCP finance quote",
            notes="Included £3,500 manufacturer deposit contribution.",
            performed_by="sarah.jenkins@keyloop-dealer.co.uk",
            outcome="SENT",
            occurred_at=base + timedelta(days=2, hours=6),
            created_at=base + timedelta(days=2, hours=6, minutes=2),
        ),
        # Noah Evans timeline (Converted + post-sale note)
        Activity(
            id=UUID("a1b2c3d4-0010-4000-8000-000000000010"),
            lead_id=LEAD_NOAH_ID,
            activity_type=ActivityType.MEETING.value,
            summary="Order form signed and £1,000 reservation deposit taken",
            notes="Deal closed for Gentian Blue Taycan 4S.",
            performed_by="marcus.reed@keyloop-dealer.co.uk",
            outcome="WON",
            occurred_at=base + timedelta(days=2, hours=4),
            created_at=base + timedelta(days=2, hours=4, minutes=3),
        ),
        Activity(
            id=UUID("a1b2c3d4-0011-4000-8000-000000000011"),
            lead_id=LEAD_NOAH_ID,
            activity_type=ActivityType.NOTE.value,
            summary="Handover preparation booked with PDI workshop",
            notes="Ceramic paint protection and Type-2 charging cable added to checklist.",
            performed_by="marcus.reed@keyloop-dealer.co.uk",
            outcome=None,
            occurred_at=base + timedelta(days=2, hours=5),
            created_at=base + timedelta(days=2, hours=5),
        ),
        # Isla Roberts timeline (Lost)
        Activity(
            id=UUID("a1b2c3d4-0012-4000-8000-000000000012"),
            lead_id=LEAD_ISLA_ID,
            activity_type=ActivityType.CALL.value,
            summary="Follow-up call — customer purchased alternative brand",
            notes="Needed immediate collection this week; preferred colour had 6-week factory wait.",
            performed_by="sarah.jenkins@keyloop-dealer.co.uk",
            outcome="LOST_TO_COMPETITOR",
            occurred_at=base + timedelta(hours=6),
            created_at=base + timedelta(hours=6, minutes=5),
        ),
    ]
    return leads, activities


def seed_database(*, reset: bool = False) -> None:
    settings = get_settings()
    db_manager = DatabaseManager(settings)
    init_db(db_manager.engine)

    leads, activities = build_seed_dataset()
    inserted_leads = 0
    inserted_activities = 0

    with db_manager.session_factory() as session:
        if reset:
            session.execute(delete(Activity))
            session.execute(delete(Lead))
            session.commit()

        for lead in leads:
            if session.get(Lead, lead.id) is None:
                session.add(lead)
                inserted_leads += 1
        session.flush()

        for activity in activities:
            if session.get(Activity, activity.id) is None:
                session.add(activity)
                inserted_activities += 1

        session.commit()

    db_manager.dispose()
    print(
        f"Seed complete ({settings.database_url}): "
        f"inserted {inserted_leads} leads and {inserted_activities} activities."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed sample automotive dealership leads and activities."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing leads and activities before seeding.",
    )
    args = parser.parse_args()
    seed_database(reset=args.reset)


if __name__ == "__main__":
    main()
