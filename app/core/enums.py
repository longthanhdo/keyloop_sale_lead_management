from enum import StrEnum


class LeadStatus(StrEnum):
    NEW = "NEW"
    CONTACTED = "CONTACTED"
    QUALIFIED = "QUALIFIED"
    TEST_DRIVE_SCHEDULED = "TEST_DRIVE_SCHEDULED"
    NEGOTIATION = "NEGOTIATION"
    CONVERTED = "CONVERTED"
    LOST = "LOST"


class LeadSource(StrEnum):
    DEALER_WEBSITE = "DEALER_WEBSITE"
    AUTO_TRADER = "AUTO_TRADER"
    CARWOW = "CARWOW"
    PHONE_ENQUIRY = "PHONE_ENQUIRY"
    WALK_IN = "WALK_IN"
    OEM_PORTAL = "OEM_PORTAL"
    SOCIAL_MEDIA = "SOCIAL_MEDIA"
    OTHER = "OTHER"


class ActivityType(StrEnum):
    CALL = "CALL"
    EMAIL = "EMAIL"
    SMS = "SMS"
    TEST_DRIVE_SCHEDULED = "TEST_DRIVE_SCHEDULED"
    QUOTE_SENT = "QUOTE_SENT"
    MEETING = "MEETING"
    NOTE = "NOTE"
    STATUS_CHANGE = "STATUS_CHANGE"


class LeadSortField(StrEnum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    LAST_CONTACTED_AT = "last_contacted_at"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


# Domain lifecycle rules (aligned with System Design Document Section 2.1)
TERMINAL_LEAD_STATUSES: frozenset[LeadStatus] = frozenset(
    {LeadStatus.CONVERTED, LeadStatus.LOST}
)

# Substantive outreach interactions that advance NEW -> CONTACTED
FIRST_CONTACT_ACTIVITY_TYPES: frozenset[ActivityType] = frozenset(
    {
        ActivityType.CALL,
        ActivityType.EMAIL,
        ActivityType.SMS,
        ActivityType.QUOTE_SENT,
        ActivityType.MEETING,
    }
)

# Customer-facing outreach types that update lead.last_contacted_at
OUTREACH_ACTIVITY_TYPES: frozenset[ActivityType] = frozenset(
    {
        ActivityType.CALL,
        ActivityType.EMAIL,
        ActivityType.SMS,
        ActivityType.TEST_DRIVE_SCHEDULED,
        ActivityType.QUOTE_SENT,
        ActivityType.MEETING,
    }
)

# Statuses that automatically advance to TEST_DRIVE_SCHEDULED when a test drive is logged
PRE_TEST_DRIVE_STATUSES: frozenset[LeadStatus] = frozenset(
    {
        LeadStatus.NEW,
        LeadStatus.CONTACTED,
        LeadStatus.QUALIFIED,
    }
)

# Explicit state transition graph for PATCH /leads/{id} and new_lead_status overrides
ALLOWED_STATUS_TRANSITIONS: dict[LeadStatus, frozenset[LeadStatus]] = {
    LeadStatus.NEW: frozenset(
        {
            LeadStatus.CONTACTED,
            LeadStatus.QUALIFIED,
            LeadStatus.TEST_DRIVE_SCHEDULED,
            LeadStatus.NEGOTIATION,
            LeadStatus.LOST,
        }
    ),
    LeadStatus.CONTACTED: frozenset(
        {
            LeadStatus.QUALIFIED,
            LeadStatus.TEST_DRIVE_SCHEDULED,
            LeadStatus.NEGOTIATION,
            LeadStatus.LOST,
        }
    ),
    LeadStatus.QUALIFIED: frozenset(
        {
            LeadStatus.TEST_DRIVE_SCHEDULED,
            LeadStatus.NEGOTIATION,
            LeadStatus.LOST,
        }
    ),
    LeadStatus.TEST_DRIVE_SCHEDULED: frozenset(
        {
            LeadStatus.NEGOTIATION,
            LeadStatus.CONVERTED,
            LeadStatus.LOST,
        }
    ),
    LeadStatus.NEGOTIATION: frozenset(
        {
            LeadStatus.CONVERTED,
            LeadStatus.LOST,
        }
    ),
    LeadStatus.LOST: frozenset(
        {
            LeadStatus.CONTACTED,  # Re-engaged by customer
        }
    ),
    LeadStatus.CONVERTED: frozenset(),  # Terminal won state
}
