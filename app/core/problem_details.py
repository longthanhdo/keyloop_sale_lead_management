import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import get_correlation_id
from app.core.exceptions import PROBLEM_BASE_URI, DomainException

logger = logging.getLogger("app.exceptions")

PROBLEM_MEDIA_TYPE = "application/problem+json"


def build_problem_response(
    *,
    request: Request,
    status_code: int,
    problem_type: str,
    title: str,
    detail: str,
    errors: list[dict[str, str]] | None = None,
) -> JSONResponse:
    correlation_id = getattr(request.state, "correlation_id", None) or get_correlation_id()
    body: dict[str, Any] = {
        "type": problem_type,
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": request.url.path,
        "correlation_id": correlation_id,
    }
    if errors is not None:
        body["errors"] = errors

    headers: dict[str, str] = {}
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id

    return JSONResponse(
        status_code=status_code,
        content=body,
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register global RFC 7807 exception handlers on the FastAPI instance."""

    @app.exception_handler(DomainException)
    async def domain_exception_handler(
        request: Request, exc: DomainException
    ) -> JSONResponse:
        logger.warning(
            "domain.exception",
            extra={
                "event": "domain.exception",
                "http_method": request.method,
                "path": request.url.path,
                "status_code": exc.status_code,
                "problem_type": exc.problem_type,
            },
        )
        return build_problem_response(
            request=request,
            status_code=exc.status_code,
            problem_type=exc.problem_type,
            title=exc.title,
            detail=exc.detail,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        raw_errors = exc.errors()
        # Treat malformed JSON syntax as 400 Bad Request per System Design Section 5.4
        if any(err.get("type") == "json_invalid" for err in raw_errors):
            return build_problem_response(
                request=request,
                status_code=400,
                problem_type=f"{PROBLEM_BASE_URI}/malformed-json",
                title="Malformed JSON Request",
                detail="Request body contains invalid JSON syntax.",
            )

        formatted_errors = [
            {
                "field": ".".join(str(part) for part in err.get("loc", ())),
                "message": err.get("msg", "Invalid value"),
            }
            for err in raw_errors
        ]

        logger.info(
            "request.validation_failed",
            extra={
                "event": "request.validation_failed",
                "http_method": request.method,
                "path": request.url.path,
                "status_code": 422,
                "error_count": len(formatted_errors),
            },
        )
        return build_problem_response(
            request=request,
            status_code=422,
            problem_type=f"{PROBLEM_BASE_URI}/validation-error",
            title="Request Validation Failed",
            detail="One or more request fields failed validation.",
            errors=formatted_errors,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        status_titles = {
            400: ("bad-request", "Bad Request"),
            404: ("not-found", "Resource Not Found"),
            405: ("method-not-allowed", "Method Not Allowed"),
            409: ("conflict", "Conflict"),
            503: ("service-unavailable", "Service Unavailable"),
        }
        slug, title = status_titles.get(
            exc.status_code, ("http-error", "HTTP Error")
        )
        return build_problem_response(
            request=request,
            status_code=exc.status_code,
            problem_type=f"{PROBLEM_BASE_URI}/{slug}",
            title=title,
            detail=str(exc.detail),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception(
            "http.unhandled_exception",
            extra={
                "event": "http.unhandled_exception",
                "http_method": request.method,
                "path": request.url.path,
                "status_code": 500,
                "exception_class": exc.__class__.__name__,
            },
        )
        return build_problem_response(
            request=request,
            status_code=500,
            problem_type=f"{PROBLEM_BASE_URI}/internal-server-error",
            title="Internal Server Error",
            detail="An unexpected internal error occurred. Reference correlation_id when contacting support.",
        )
