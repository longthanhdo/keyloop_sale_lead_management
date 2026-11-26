import io
import json
import logging
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter


def test_correlation_id_propagation_and_auto_generation(client: TestClient) -> None:
    # Caller-provided correlation ID is echoed on success and error responses
    custom_id = "corr-keyloop-12345"
    resp_ok = client.get("/health/live", headers={"X-Correlation-ID": custom_id})
    assert resp_ok.headers["X-Correlation-ID"] == custom_id

    resp_404 = client.get(
        "/api/v1/leads/00000000-0000-4000-8000-000000000000",
        headers={"X-Correlation-ID": custom_id},
    )
    assert resp_404.status_code == 404
    assert resp_404.headers["X-Correlation-ID"] == custom_id
    assert resp_404.json()["correlation_id"] == custom_id

    # Absent header generates a valid UUIDv4
    resp_gen = client.get("/health/live")
    generated_id = resp_gen.headers["X-Correlation-ID"]
    assert UUID(generated_id).version == 4


def test_bad_request_400_for_invalid_dealer_header_and_malformed_json(
    client: TestClient,
) -> None:
    # Invalid UUID in X-Dealer-ID -> 400 RFC 7807
    resp_dealer = client.get(
        "/api/v1/leads", headers={"X-Dealer-ID": "not-a-valid-uuid"}
    )
    assert resp_dealer.status_code == 400
    assert resp_dealer.headers["content-type"].startswith("application/problem+json")
    assert resp_dealer.json()["type"].endswith("/invalid-dealer-header")
    assert resp_dealer.json()["correlation_id"]

    # Malformed JSON syntax -> 400 RFC 7807
    resp_json = client.post(
        "/api/v1/leads",
        content="{broken json",
        headers={"Content-Type": "application/json"},
    )
    assert resp_json.status_code == 400
    assert resp_json.headers["content-type"].startswith("application/problem+json")
    assert resp_json.json()["type"].endswith("/malformed-json")


def test_unhandled_500_returns_sanitized_rfc7807(
    app: FastAPI, client: TestClient
) -> None:
    @app.get("/_test/crash")
    def crash_route() -> None:
        raise RuntimeError("Sensitive internal DB password leaked here")

    resp = client.get("/_test/crash", headers={"X-Correlation-ID": "crash-corr-1"})
    assert resp.status_code == 500
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["status"] == 500
    assert body["title"] == "Internal Server Error"
    assert body["correlation_id"] == "crash-corr-1"
    assert "password" not in body["detail"].lower()


def test_structured_json_logs_contain_envelope_and_exclude_all_pii(
    client: TestClient,
) -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    try:
        pii_email = "secret.customer@private-domain.co.uk"
        pii_phone = "+447700999888"
        pii_first = "ConfidentialFirst"
        pii_last = "ConfidentialLast"
        pii_notes = "Customer mentioned personal bank account details"

        create_resp = client.post(
            "/api/v1/leads",
            headers={"X-Correlation-ID": "pii-check-001"},
            json={
                "first_name": pii_first,
                "last_name": pii_last,
                "email": pii_email,
                "phone": pii_phone,
                "source": "DEALER_WEBSITE",
                "enquiry_notes": pii_notes,
            },
        )
        assert create_resp.status_code == 201
        lead_id = create_resp.json()["id"]

        act_resp = client.post(
            f"/api/v1/leads/{lead_id}/activities",
            headers={"X-Correlation-ID": "pii-check-002"},
            json={
                "activity_type": "CALL",
                "summary": "Called ConfidentialFirst about finance",
                "notes": pii_notes,
                "performed_by": "sarah@dealer.co.uk",
            },
        )
        assert act_resp.status_code == 201
    finally:
        root_logger.removeHandler(handler)

    raw_output = stream.getvalue()
    lines = [line for line in raw_output.splitlines() if line.strip()]
    assert len(lines) >= 2

    parsed_logs = [json.loads(line) for line in lines]
    events = {entry["event"] for entry in parsed_logs}
    assert "lead.created" in events
    assert "activity.logged" in events
    assert "http.request.completed" in events

    # Verify required envelope keys exist (including dealership_id on access & domain logs)
    for entry in parsed_logs:
        for required_key in (
            "timestamp",
            "level",
            "logger",
            "event",
            "correlation_id",
            "dealership_id",
        ):
            assert required_key in entry
        if entry["event"] in ("http.request.completed", "lead.created", "activity.logged"):
            assert entry["dealership_id"] is not None

    # Verify strict zero-PII guarantee across all emitted logs
    for forbidden_value in (pii_email, pii_phone, pii_first, pii_last, pii_notes):
        assert forbidden_value not in raw_output
