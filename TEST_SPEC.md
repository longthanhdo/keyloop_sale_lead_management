# Test Specification Document: Sales Lead Management Tool (Demand Domain)

| Metadata | Details |
| :--- | :--- |
| **Document Title** | Automated Test Specification & Requirement Traceability Matrix |
| **Target Context** | Keyloop Engineering Manager Technical Assessment — Scenario C (Domain: Demand) |
| **Version** | 1.0.0 |
| **Companion Blueprint** | [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) (`v1.0.0`) |
| **Test Framework** | Python 3.12+, Pytest 8.x, FastAPI `TestClient` / HTTPX, SQLAlchemy 2.0 |
| **Total Automated Cases** | **50** (`25` Domain/Service Unit Tests + `25` End-to-End API Integration Tests) |

---

## 1. Test Strategy & Architecture

To guarantee production-grade reliability without brittle external dependencies, the test suite follows a **two-tier testing pyramid** with strict per-test database isolation:

1. **Zero Shared State (`tests/conftest.py`)**:
   - Every test function receives a fresh in-memory SQLite instance (`sqlite:///:memory:` with `StaticPool`) initialized via `Base.metadata.create_all()`.
   - Every connection executes `PRAGMA foreign_keys = ON;` on connect to maintain referential integrity parity with PostgreSQL 16.
2. **Tier 1 — Domain & Service Layer Unit Suite (`tests/test_business_logic.py` — 25 cases)**:
   - Directly exercises `validate_status_transition`, `ActivityService` resolution helpers, `LeadService` partial-update semantics, and SQLAlchemy `before_cursor_execute` query-counting hooks without HTTP transport overhead.
3. **Tier 2 — HTTP API Integration, Transaction & Observability Suite (`25 cases` across 4 modules)**:
   - Exercises the full ASGI stack (`CorrelationIDMiddleware` → `AccessLogMiddleware` → `TenantContextMiddleware` → RFC 7807 Exception Handlers → Routers → Services → Repositories → SQLite) to validate wire contracts, ACID rollbacks, multi-tenant isolation, and GDPR zero-PII logging.

---

## 2. Requirement Traceability Matrix

| System Design / Assessment Requirement | SDD Reference | Verifying Test IDs |
| :--- | :---: | :--- |
| Lead creation defaults (`status=NEW`, `last_contacted_at=null`, `version=1`, UTC `Z`, `Location` header) | §5.3.4 | `TC-LEAD-01` |
| Lead Inbox filtering (`status`, `source`, `assigned_to`, `search`), SLA sorting (`NULLS FIRST`), pagination | §3.2, §4.3, §5.3.1 | `TC-LEAD-02` |
| Multi-tenant isolation (`X-Dealer-ID`) & soft-delete exclusion (`deleted_at IS NULL`) | §2.4, §2.5, §5.4 | `TC-BL-24`, `TC-LEAD-02`, `TC-LEAD-03`, `TC-ACT-11` |
| Lead Details View & bounded N+1 query prevention (`selectinload` = 2 `SELECT`s) | §3.2, §4.2 | `TC-BL-25`, `TC-ACT-08` |
| Lead lifecycle state machine (valid paths, invalid paths, `LOST -> CONTACTED` reopen) | §2.1 | `TC-BL-01`..`TC-BL-21`, `TC-LEAD-05` |
| Optimistic concurrency control (`version` check & `409 Conflict` on stale writes) | §4.2, §5.4 | `TC-BL-24`, `TC-LEAD-04` |
| Atomic activity logging + auto status progression (`NEW -> CONTACTED`, `TEST_DRIVE_SCHEDULED`) | §2.1, §3.2, §5.3.3 | `TC-ACT-01`..`TC-ACT-06`, `TC-BL-22` |
| Internal `NOTE` invariance (does not mutate `status` or `last_contacted_at`) | §2.1 | `TC-BL-23`, `TC-ACT-07` |
| Chronological ordering (`asc`/`desc`), retroactive `occurred_at` & monotonic `last_contacted_at` | §2.3, §5.3.2 | `TC-BL-23`, `TC-ACT-08` |
| Single-transaction rollback on rejected `new_lead_status` override & terminal-state safety | §2.1, §3.2 | `TC-ACT-09`, `TC-ACT-10` |
| Liveness (`/health/live`), Readiness (`/health/ready` `200`/`503`) & SQLite FK enforcement | §4.2, §7.2 | `TC-HLTH-01`..`TC-HLTH-04` |
| RFC 7807 (`application/problem+json`) across `400`, `404`, `409`, `422`, `500`, `503` | §5.3.5, §5.4, §7.3 | `TC-LEAD-03`..`TC-LEAD-06`, `TC-ACT-09`, `TC-ACT-11`, `TC-HLTH-03`, `TC-OBS-01`..`TC-OBS-03` |
| `X-Correlation-ID` propagation & structured JSON logging with strict zero-PII scrubbing | §7.1 | `TC-OBS-01`, `TC-OBS-04` |

---

## 3. Formal Test Case Specifications

### 3.1 Suite A — Domain & Service Business Logic (`tests/test_business_logic.py`)

| Test ID | Pytest Function & Parameter | Preconditions | Inputs / Action | Expected Result |
| :--- | :--- | :--- | :--- | :--- |
| `TC-BL-01` | `test_validate_status_transition_allows_valid_paths[NEW-NEW]` | Lead status is `NEW`. | `validate_status_transition(NEW, NEW)` | Succeeds (idempotent no-op, no exception raised). |
| `TC-BL-02` | `test_validate_status_transition_allows_valid_paths[NEW-CONTACTED]` | Lead status is `NEW`. | `validate_status_transition(NEW, CONTACTED)` | Succeeds without error. |
| `TC-BL-03` | `test_validate_status_transition_allows_valid_paths[NEW-QUALIFIED]` | Lead status is `NEW`. | `validate_status_transition(NEW, QUALIFIED)` | Succeeds without error. |
| `TC-BL-04` | `test_validate_status_transition_allows_valid_paths[NEW-TEST_DRIVE_SCHEDULED]` | Lead status is `NEW`. | `validate_status_transition(NEW, TEST_DRIVE_SCHEDULED)` | Succeeds without error. |
| `TC-BL-05` | `test_validate_status_transition_allows_valid_paths[NEW-LOST]` | Lead status is `NEW`. | `validate_status_transition(NEW, LOST)` | Succeeds without error. |
| `TC-BL-06` | `test_validate_status_transition_allows_valid_paths[CONTACTED-QUALIFIED]` | Lead status is `CONTACTED`. | `validate_status_transition(CONTACTED, QUALIFIED)` | Succeeds without error. |
| `TC-BL-07` | `test_validate_status_transition_allows_valid_paths[QUALIFIED-TEST_DRIVE_SCHEDULED]` | Lead status is `QUALIFIED`. | `validate_status_transition(QUALIFIED, TEST_DRIVE_SCHEDULED)` | Succeeds without error. |
| `TC-BL-08` | `test_validate_status_transition_allows_valid_paths[TEST_DRIVE_SCHEDULED-NEGOTIATION]` | Lead status is `TEST_DRIVE_SCHEDULED`. | `validate_status_transition(TEST_DRIVE_SCHEDULED, NEGOTIATION)` | Succeeds without error. |
| `TC-BL-09` | `test_validate_status_transition_allows_valid_paths[TEST_DRIVE_SCHEDULED-CONVERTED]` | Lead status is `TEST_DRIVE_SCHEDULED`. | `validate_status_transition(TEST_DRIVE_SCHEDULED, CONVERTED)` | Succeeds without error. |
| `TC-BL-10` | `test_validate_status_transition_allows_valid_paths[NEGOTIATION-CONVERTED]` | Lead status is `NEGOTIATION`. | `validate_status_transition(NEGOTIATION, CONVERTED)` | Succeeds without error. |
| `TC-BL-11` | `test_validate_status_transition_allows_valid_paths[NEGOTIATION-LOST]` | Lead status is `NEGOTIATION`. | `validate_status_transition(NEGOTIATION, LOST)` | Succeeds without error. |
| `TC-BL-12` | `test_validate_status_transition_allows_valid_paths[LOST-CONTACTED]` | Lead status is `LOST`. | `validate_status_transition(LOST, CONTACTED)` | Succeeds (customer re-engagement path permitted). |
| `TC-BL-13` | `test_validate_status_transition_rejects_invalid_paths[NEW-CONVERTED]` | Lead status is `NEW`. | `validate_status_transition(NEW, CONVERTED)` | Raises `InvalidStatusTransitionError` (`NEW` → `CONVERTED`). |
| `TC-BL-14` | `test_validate_status_transition_rejects_invalid_paths[CONTACTED-CONVERTED]` | Lead status is `CONTACTED`. | `validate_status_transition(CONTACTED, CONVERTED)` | Raises `InvalidStatusTransitionError`. |
| `TC-BL-15` | `test_validate_status_transition_rejects_invalid_paths[QUALIFIED-CONVERTED]` | Lead status is `QUALIFIED`. | `validate_status_transition(QUALIFIED, CONVERTED)` | Raises `InvalidStatusTransitionError`. |
| `TC-BL-16` | `test_validate_status_transition_rejects_invalid_paths[CONVERTED-NEW]` | Lead status is terminal `CONVERTED`. | `validate_status_transition(CONVERTED, NEW)` | Raises `InvalidStatusTransitionError`. |
| `TC-BL-17` | `test_validate_status_transition_rejects_invalid_paths[CONVERTED-LOST]` | Lead status is terminal `CONVERTED`. | `validate_status_transition(CONVERTED, LOST)` | Raises `InvalidStatusTransitionError`. |
| `TC-BL-18` | `test_validate_status_transition_rejects_invalid_paths[CONVERTED-NEGOTIATION]` | Lead status is terminal `CONVERTED`. | `validate_status_transition(CONVERTED, NEGOTIATION)` | Raises `InvalidStatusTransitionError`. |
| `TC-BL-19` | `test_validate_status_transition_rejects_invalid_paths[LOST-CONVERTED]` | Lead status is `LOST`. | `validate_status_transition(LOST, CONVERTED)` | Raises `InvalidStatusTransitionError`. |
| `TC-BL-20` | `test_validate_status_transition_rejects_invalid_paths[LOST-NEW]` | Lead status is `LOST`. | `validate_status_transition(LOST, NEW)` | Raises `InvalidStatusTransitionError`. |
| `TC-BL-21` | `test_validate_status_transition_rejects_invalid_paths[NEGOTIATION-NEW]` | Lead status is `NEGOTIATION`. | `validate_status_transition(NEGOTIATION, NEW)` | Raises `InvalidStatusTransitionError`. |
| `TC-BL-22` | `test_resolve_next_status_prevents_backward_regression_on_advanced_leads` | Leads in `QUALIFIED`, `NEGOTIATION`, and `LOST`. | Call `ActivityService._resolve_next_status` with `CALL` / `TEST_DRIVE_SCHEDULED` and `explicit_override=None`. | Returns existing status (`QUALIFIED`, `NEGOTIATION`, `LOST`) without backward regression. |
| `TC-BL-23` | `test_resolve_last_contacted_at_monotonicity_and_note_invariance` | Timestamps `t0 < t1 < t2`. | Call `_resolve_last_contacted_at` for first `CALL` (`t1`), newer `EMAIL` (`t2`), retroactive `SMS` (`t0`), `NOTE`, and `STATUS_CHANGE`. | Initializes to `t1`, advances to `t2`, retains `t2` on retroactive `t0`, and leaves value unchanged on `NOTE` / `STATUS_CHANGE`. |
| `TC-BL-24` | `test_lead_service_partial_update_preserves_omitted_and_clears_explicit_null` | Lead persisted at `version=1` with `assigned_to` and `vehicle_of_interest` populated. | 1) `update_lead(version=1, assigned_to=None)`<br>2) `update_lead` with wrong `dealership_id`<br>3) `update_lead` with stale `version=1` | 1) Clears `assigned_to` to `None`, preserves `vehicle_of_interest`, increments `version=2`.<br>2) Raises `LeadNotFoundError`.<br>3) Raises `OptimisticLockError`. |
| `TC-BL-25` | `test_get_lead_detail_executes_bounded_queries_no_n_plus_one` | Lead persisted with `12` child `Activity` records; SQLAlchemy cursor listener attached. | `LeadService.get_lead_detail(lead_id, activity_sort=ASC)` | Returns all `12` activities while executing **strictly 2 `SELECT` statements** (`leads` + `selectinload` `activities`). |

---

### 3.2 Suite B — Lead Management API (`tests/test_leads_api.py`)

| Test ID | Pytest Function | Preconditions | Inputs / Action | Expected Result |
| :--- | :--- | :--- | :--- | :--- |
| `TC-LEAD-01` | `test_create_lead_sets_defaults_and_location_header` | Empty default dealership DB. | `POST /api/v1/leads` with customer profile & `DEALER_WEBSITE` source. | `201 Created`; `Location: /api/v1/leads/{id}`; `status="NEW"`, `last_contacted_at=null`, `version=1`, `dealership_id` set to default tenant, UTC timestamps suffixed with `Z`. |
| `TC-LEAD-02` | `test_lead_inbox_filtering_searching_sorting_and_pagination` | 3 leads in default dealership (1 transitioned to `CONTACTED` via `CALL`, 2 untouched `NEW`) + 1 lead in secondary dealership. | `GET /api/v1/leads` with:<br>• `page=1&page_size=2`<br>• `status=CONTACTED` & `status=NEW,CONTACTED`<br>• `source=AUTO_TRADER&assigned_to=...`<br>• `search=audi q4` & `search=sophie williams`<br>• `sort_by=last_contacted_at&sort_order=asc` | `200 OK`; secondary dealership lead excluded; accurate `pagination` metadata (`total_items=3`, `total_pages=2`, `has_next=true`); exact filter/search matches; SLA sort places `last_contacted_at=null` leads first. |
| `TC-LEAD-03` | `test_get_lead_detail_404_for_missing_wrong_tenant_or_soft_deleted` | 1 active lead in default dealership. | 1) `GET /api/v1/leads/{random_uuid}`<br>2) `GET /api/v1/leads/{id}` with `X-Dealer-ID` of secondary dealership<br>3) Set `deleted_at`, then `GET /api/v1/leads/{id}` & `GET /api/v1/leads` | All detail lookups return `404 Not Found` (`application/problem+json`, `type=.../lead-not-found`); soft-deleted lead disappears from inbox (`total_items=0`). |
| `TC-LEAD-04` | `test_patch_lead_happy_path_and_optimistic_lock_conflict` | Active `NEW` lead at `version=1`. | 1) `PATCH /api/v1/leads/{id}` with `{"version": 1, "status": "CONTACTED", "assigned_to": "..."}`<br>2) Repeat `PATCH` with stale `{"version": 1, "status": "QUALIFIED"}` | 1) `200 OK`, `status="CONTACTED"`, `version=2`.<br>2) `409 Conflict` (`application/problem+json`, `type=.../optimistic-lock-conflict`). |
| `TC-LEAD-05` | `test_patch_lead_invalid_status_transition_returns_409` | Active `NEW` lead at `version=1`. | 1) `PATCH` `NEW -> CONVERTED`<br>2) `PATCH` `NEW -> LOST` (`v1 -> v2`), then `LOST -> CONTACTED` (`v2 -> v3`) | 1) `409 Conflict` (`type=.../invalid-status-transition`).<br>2) Both valid transitions return `200 OK` and end in `status="CONTACTED"`. |
| `TC-LEAD-06` | `test_lead_validation_errors_return_422_rfc7807` | Running API client. | 1) `POST /api/v1/leads` with invalid email & invalid `source`<br>2) `GET /api/v1/leads?page_size=250`<br>3) `GET /api/v1/leads?status=BOGUS` | All return `422 Unprocessable Entity` (`application/problem+json`) with structured `errors` array pinpointing `body.email`, `body.source`, and `query.status`. |

---

### 3.3 Suite C — Activity Logging & Atomic Synchronization API (`tests/test_activities_api.py`)

| Test ID | Pytest Function & Parameter | Preconditions | Inputs / Action | Expected Result |
| :--- | :--- | :--- | :--- | :--- |
| `TC-ACT-01` | `test_outreach_activity_on_new_lead_auto_transitions_to_contacted[CALL]` | Active `NEW` lead (`version=1`, `last_contacted_at=null`). | `POST /api/v1/leads/{id}/activities` with `activity_type="CALL"` and `occurred_at`. | `201 Created`; `lead_snapshot` shows `status="CONTACTED"`, `last_contacted_at=occurred_at`, `version=2`. |
| `TC-ACT-02` | `test_outreach_activity_on_new_lead_auto_transitions_to_contacted[EMAIL]` | Active `NEW` lead (`version=1`). | `POST .../activities` with `activity_type="EMAIL"`. | `201 Created`; `lead_snapshot` transitions `NEW -> CONTACTED`, sets `last_contacted_at`, `version=2`. |
| `TC-ACT-03` | `test_outreach_activity_on_new_lead_auto_transitions_to_contacted[SMS]` | Active `NEW` lead (`version=1`). | `POST .../activities` with `activity_type="SMS"`. | `201 Created`; `lead_snapshot` transitions `NEW -> CONTACTED`, sets `last_contacted_at`, `version=2`. |
| `TC-ACT-04` | `test_outreach_activity_on_new_lead_auto_transitions_to_contacted[QUOTE_SENT]` | Active `NEW` lead (`version=1`). | `POST .../activities` with `activity_type="QUOTE_SENT"`. | `201 Created`; `lead_snapshot` transitions `NEW -> CONTACTED`, sets `last_contacted_at`, `version=2`. |
| `TC-ACT-05` | `test_outreach_activity_on_new_lead_auto_transitions_to_contacted[MEETING]` | Active `NEW` lead (`version=1`). | `POST .../activities` with `activity_type="MEETING"`. | `201 Created`; `lead_snapshot` transitions `NEW -> CONTACTED`, sets `last_contacted_at`, `version=2`. |
| `TC-ACT-06` | `test_test_drive_activity_auto_advances_non_terminal_lead` | Active `NEW` lead (`version=1`). | `POST .../activities` with `activity_type="TEST_DRIVE_SCHEDULED"`. | `201 Created`; `lead_snapshot` advances automatically to `status="TEST_DRIVE_SCHEDULED"`, updates `last_contacted_at`, `version=2`. |
| `TC-ACT-07` | `test_note_activity_does_not_change_status_or_last_contacted_at` | Active `NEW` lead. | 1) Log `NOTE` on `NEW` lead<br>2) Log `CALL` at `10:00Z`<br>3) Log `NOTE` at `16:00Z` | 1) `status` stays `NEW`, `last_contacted_at` stays `null`, `version=2`.<br>2) `status="CONTACTED"`, `last_contacted_at="10:00Z"`.<br>3) `last_contacted_at` remains `"10:00Z"`, `status` stays `"CONTACTED"`, `version=4`. |
| `TC-ACT-08` | `test_chronological_ordering_asc_desc_and_retroactive_logging` | Active lead. | Log 3 activities out of order (`12:00Z`, `15:00Z`, then retroactive `09:30Z`); query `GET /leads/{id}` (`asc`/`desc`) and `GET /leads/{id}/activities?activity_sort=desc&page_size=2`. | Retroactive `09:30Z` SMS does **not** regress `last_contacted_at` from `15:00Z`; `asc` returns `[09:30, 12:00, 15:00]`; `desc` returns `[15:00, 12:00, 09:30]`; paginated feed returns top 2 with `has_next=true`. |
| `TC-ACT-09` | `test_explicit_status_override_and_rollback_on_invalid_override` | Active `NEW` lead (`version=1`). | 1) `POST .../activities` (`QUOTE_SENT`, `new_lead_status="CONVERTED"`)<br>2) Inspect `GET /leads/{id}`<br>3) `POST .../activities` (`QUOTE_SENT`, `new_lead_status="NEGOTIATION"`) | 1) `409 Conflict` (`application/problem+json`).<br>2) Full transaction rollback confirmed (`activities=[]`, `version=1`).<br>3) `201 Created`, `status="NEGOTIATION"`, `version=2`. |
| `TC-ACT-10` | `test_terminal_lead_permits_post_sale_activity_without_status_regression` | Lead progressed to terminal `CONVERTED` (`version=3`). | `POST .../activities` with `activity_type="TEST_DRIVE_SCHEDULED"` (handover orientation drive). | `201 Created`; activity persisted while `lead_snapshot.status` remains `"CONVERTED"` (`version=4`). |
| `TC-ACT-11` | `test_activity_errors_404_and_422` | Active lead in default dealership. | 1) `POST` activity to random UUID<br>2) `POST` activity with secondary `X-Dealer-ID`<br>3) `POST` activity with invalid enum & whitespace-only `summary`/`performed_by` | 1 & 2) `404 Not Found` (`application/problem+json`).<br>3) `422 Unprocessable Entity` listing `body.activity_type`, `body.summary`, `body.performed_by`. |

---

### 3.4 Suite D — Health Probes & Persistence Guardrails (`tests/test_health.py`)

| Test ID | Pytest Function | Preconditions | Inputs / Action | Expected Result |
| :--- | :--- | :--- | :--- | :--- |
| `TC-HLTH-01` | `test_health_live_returns_200` | Running FastAPI app. | `GET /health/live` | `200 OK` with `{"status": "live"}` and `X-Correlation-ID` response header. |
| `TC-HLTH-02` | `test_health_ready_returns_200_when_db_connected` | Healthy SQLite session. | `GET /health/ready` | `200 OK` with `{"status": "ready", "database": "connected"}`. |
| `TC-HLTH-03` | `test_health_ready_returns_503_problem_json_on_db_failure` | `get_db_session` overridden to raise `RuntimeError` on `SELECT 1`. | `GET /health/ready` | `503 Service Unavailable` (`application/problem+json`) with `title="Service Unavailable"`, `instance="/health/ready"`, and `correlation_id`. |
| `TC-HLTH-04` | `test_sqlite_foreign_keys_pragma_enabled` | Active SQLite `DatabaseManager`. | Execute `PRAGMA foreign_keys;` on session connection. | Returns `1` (foreign key enforcement active, matching PostgreSQL behavior). |

---

### 3.5 Suite E — Observability, Headers & RFC 7807 Error Handling (`tests/test_observability_and_errors.py`)

| Test ID | Pytest Function | Preconditions | Inputs / Action | Expected Result |
| :--- | :--- | :--- | :--- | :--- |
| `TC-OBS-01` | `test_correlation_id_propagation_and_auto_generation` | Running FastAPI app. | 1) Send `X-Correlation-ID: corr-keyloop-12345` on `200` and `404` endpoints<br>2) Send request without `X-Correlation-ID` | 1) Exact caller ID echoed in response header and RFC 7807 `correlation_id` body field.<br>2) Valid UUIDv4 generated and returned in `X-Correlation-ID`. |
| `TC-OBS-02` | `test_bad_request_400_for_invalid_dealer_header_and_malformed_json` | Running FastAPI app. | 1) `GET /api/v1/leads` with `X-Dealer-ID: not-a-valid-uuid`<br>2) `POST /api/v1/leads` with `{broken json` | Both return `400 Bad Request` (`application/problem+json`) with `.../invalid-dealer-header` and `.../malformed-json` problem types. |
| `TC-OBS-03` | `test_unhandled_500_returns_sanitized_rfc7807` | Test route raising `RuntimeError("Sensitive internal DB password leaked here")`. | `GET /_test/crash` with `X-Correlation-ID: crash-corr-1`. | `500 Internal Server Error` (`application/problem+json`) containing `correlation_id="crash-corr-1"` and sanitized `detail` (zero stack trace or password leakage). |
| `TC-OBS-04` | `test_structured_json_logs_contain_envelope_and_exclude_all_pii` | `JsonFormatter` stream handler attached to root logger. | Create lead with sensitive `first_name`, `last_name`, `email`, `phone`, `enquiry_notes`, then log `CALL` activity with sensitive `notes`. | Emits valid single-line JSON logs for `lead.created`, `activity.logged`, and `http.request.completed` containing `timestamp`, `level`, `logger`, `event`, `correlation_id`, and non-null `dealership_id`; **zero PII strings appear anywhere in raw log output**. |

---

## 4. Test Execution Reference

Run from the repository root (`/Users/dothanhlong/Documents/Keyloop`):

```bash
# Execute all 50 automated test cases
.venv/bin/pytest

# List all 50 collected test cases without executing
.venv/bin/pytest --collect-only -q

# Execute individual suites
.venv/bin/pytest tests/test_business_logic.py
.venv/bin/pytest tests/test_leads_api.py
.venv/bin/pytest tests/test_activities_api.py
.venv/bin/pytest tests/test_health.py
.venv/bin/pytest tests/test_observability_and_errors.py
```
