from uuid import UUID

PROBLEM_BASE_URI = "https://api.keyloop.example/problems"


class DomainException(Exception):
    """Base exception mapped to RFC 7807 Problem Details responses."""

    status_code: int = 500
    problem_type: str = f"{PROBLEM_BASE_URI}/internal-server-error"
    title: str = "Internal Server Error"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class BadRequestError(DomainException):
    status_code = 400
    problem_type = f"{PROBLEM_BASE_URI}/bad-request"
    title = "Bad Request"


class LeadNotFoundError(DomainException):
    status_code = 404
    problem_type = f"{PROBLEM_BASE_URI}/lead-not-found"
    title = "Lead Not Found"

    def __init__(self, lead_id: UUID | str) -> None:
        super().__init__(
            f"Lead with id '{lead_id}' was not found for the active dealership."
        )
        self.lead_id = str(lead_id)


class OptimisticLockError(DomainException):
    status_code = 409
    problem_type = f"{PROBLEM_BASE_URI}/optimistic-lock-conflict"
    title = "Optimistic Lock Conflict"

    def __init__(self, lead_id: UUID | str, expected_version: int) -> None:
        super().__init__(
            f"Lead '{lead_id}' has been modified concurrently. "
            f"Expected version {expected_version} is stale; please refresh and retry."
        )
        self.lead_id = str(lead_id)
        self.expected_version = expected_version


class InvalidStatusTransitionError(DomainException):
    status_code = 409
    problem_type = f"{PROBLEM_BASE_URI}/invalid-status-transition"
    title = "Invalid Lead Status Transition"

    def __init__(self, current_status: str, target_status: str) -> None:
        super().__init__(
            f"Cannot transition lead status from '{current_status}' to '{target_status}'."
        )
        self.current_status = current_status
        self.target_status = target_status


class ServiceUnavailableError(DomainException):
    status_code = 503
    problem_type = f"{PROBLEM_BASE_URI}/service-unavailable"
    title = "Service Unavailable"
