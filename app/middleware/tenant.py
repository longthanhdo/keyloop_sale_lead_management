from uuid import UUID

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.context import dealership_id_ctx
from app.core.exceptions import PROBLEM_BASE_URI
from app.core.problem_details import build_problem_response

DEALER_ID_HEADER = "X-Dealer-ID"


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Extracts and validates X-Dealer-ID header, falling back to MVP default dealership."""

    def __init__(self, app: ASGIApp, *, default_dealership_id: UUID) -> None:
        super().__init__(app)
        self.default_dealership_id = default_dealership_id

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        raw_header = request.headers.get(DEALER_ID_HEADER)
        if raw_header is not None and raw_header.strip():
            try:
                dealership_id = UUID(raw_header.strip())
            except ValueError:
                return build_problem_response(
                    request=request,
                    status_code=400,
                    problem_type=f"{PROBLEM_BASE_URI}/invalid-dealer-header",
                    title="Invalid Dealership Header",
                    detail=f"Header '{DEALER_ID_HEADER}' must be a valid UUID.",
                )
        else:
            dealership_id = self.default_dealership_id

        request.state.dealership_id = dealership_id
        token = dealership_id_ctx.set(str(dealership_id))
        try:
            return await call_next(request)
        finally:
            dealership_id_ctx.reset(token)
