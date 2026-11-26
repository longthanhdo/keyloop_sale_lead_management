# Sales Lead Management Tool — Backend Service (Demand Domain)

Backend service implementation for **Keyloop Engineering Manager Technical Assessment — Scenario C (Sales Lead Management Tool, Domain: Demand)**, built strictly to the [System Design Document (v1.0.0)](SYSTEM_DESIGN.md).

---

## Architecture Highlights

- **Layered Modular Monolith**: Clear separation across HTTP Middleware (`app/middleware`), Presentation (`app/api`, `app/schemas`), Domain Services (`app/services`), Data Access Repositories (`app/repositories`), and Persistence (`app/models`, `app/db`).
- **SQLite & PostgreSQL 16 Parity**: Dialect-portable SQLAlchemy 2.0 `Uuid` and `UTCDateTime` types, `PRAGMA foreign_keys = ON;` enforced on every SQLite connection, composite indexes aligned with inbox/detail access patterns, and PostgreSQL connection pooling (`pool_pre_ping`, `pool_recycle`).
- **Atomic Activity Logging**: Logging an activity (`POST /api/v1/leads/{lead_id}/activities`) inserts the immutable audit record and updates `last_contacted_at`, `status`, `updated_at`, and `version` inside a single ACID transaction with optimistic concurrency control.
- **Multi-Tenant & Soft-Delete Ready**: All queries scope by `dealership_id` (read from `X-Dealer-ID` header, defaulting to `11111111-1111-4111-8111-111111111111` for zero-config local evaluation) and exclude soft-deleted rows (`deleted_at IS NULL`).
- **RFC 7807 Errors & Zero-PII Structured Observability**: Every `400/404/409/422/500/503` response uses `application/problem+json` with `correlation_id`. Structured JSON logs propagate `X-Correlation-ID` and strip customer PII (`email`, `phone`, `first_name`, `last_name`, free-text `notes`).

---

## Project Structure

```text
.
├── SYSTEM_DESIGN.md                   # System Design Document (v1.0.0)
├── .env.example                       # Environment variables template
├── pyproject.toml                     # Python 3.12+ & Pytest configuration
├── requirements.txt                   # Runtime & testing dependencies
├── Dockerfile                         # Slim non-root Python 3.12 container
├── docker-compose.yml                 # SQLite default & PostgreSQL 16 profile
├── app/
│   ├── main.py                        # FastAPI app factory, lifespan, middleware & routers
│   ├── core/                          # Settings, enums, exceptions, JSON logger, RFC 7807
│   ├── db/                            # SQLAlchemy 2.0 engine, SQLite FK pragma, UTCDateTime
│   ├── middleware/                    # X-Correlation-ID, Access Log, X-Dealer-ID tenant
│   ├── models/                        # Lead & Activity ORM models + indexes/constraints
│   ├── schemas/                       # Pydantic v2 request/response DTOs
│   ├── repositories/                  # SQLAlchemy 2.0 queries, selectinload, optimistic lock
│   ├── services/                      # Lifecycle transitions & atomic UoW orchestration
│   └── api/                           # DI providers & /health + /api/v1 routers
├── scripts/
│   └── seed.py                        # Realistic automotive dealership seed data
└── tests/
    ├── conftest.py                      # Per-test isolated SQLite DB & TestClient fixtures
    ├── test_business_logic.py           # Pure domain & service-layer unit tests + N+1 SQL guard
    ├── test_health.py                   # Liveness & readiness (200 / 503) tests
    ├── test_leads_api.py                # Inbox filters/sort/pagination, CRUD, 404/409/422
    ├── test_activities_api.py           # Chronology asc/desc, auto-transitions, NOTE, retroactive
    └── test_observability_and_errors.py # Correlation ID, RFC 7807, zero-PII logs, tenancy
```

---

## Quick Start on macOS (Local Python 3.12+)

### 1. Create Virtual Environment & Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

*(Optional)* Copy `.env.example` to `.env` if you want to customize settings:

```bash
cp .env.example .env
```

### 2. Seed Realistic Dealership Data

```bash
python -m scripts.seed --reset
```

This seeds 9 realistic automotive leads (8 in the default dealership `11111111-1111-4111-8111-111111111111` across every lifecycle status, plus 1 in a secondary dealership `22222222-2222-4222-8222-222222222222`) and 12 chronological follow-up activities.

### 3. Run the API Server

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Interactive OpenAPI 3.1 / Swagger UI is available at:
- **Swagger UI**: http://127.0.0.1:8000/docs
- **ReDoc**: http://127.0.0.1:8000/redoc

### 4. Run Automated Tests (Pytest)

```bash
pytest
```

---

## Running with Docker & Docker Compose

### Option A: SQLite Mode (Fast Local Container)

```bash
docker compose up --build api
```

To seed data inside the running container:

```bash
docker compose exec api python -m scripts.seed --reset
```

### Option B: PostgreSQL 16 Mode (Production Parity)

```bash
docker compose --profile postgres up --build
```

The PostgreSQL-backed API listens on **http://127.0.0.1:8001**. To seed PostgreSQL:

```bash
docker compose --profile postgres exec api-postgres python -m scripts.seed --reset
```

---

## API Examples (`curl`)

### 1. Health Checks

```bash
curl -i http://127.0.0.1:8000/health/live
curl -i http://127.0.0.1:8000/health/ready
```

### 2. Lead Inbox (Filter, Search, Sort & Paginate)

```bash
curl -s "http://127.0.0.1:8000/api/v1/leads?status=NEW,CONTACTED&sort_by=created_at&sort_order=desc&page=1&page_size=10" | python3 -m json.tool
```

Search by customer name, email, or vehicle:

```bash
curl -s "http://127.0.0.1:8000/api/v1/leads?search=Audi" | python3 -m json.tool
```

### 3. Create a New Lead (`POST /api/v1/leads`)

```bash
curl -i -X POST "http://127.0.0.1:8000/api/v1/leads" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: demo-corr-001" \
  -d '{
    "first_name": "James",
    "last_name": "Carter",
    "email": "james.carter@example.co.uk",
    "phone": "+447700900111",
    "source": "DEALER_WEBSITE",
    "vehicle_of_interest": "2025 BMW i4 eDrive40",
    "enquiry_notes": "Looking for fleet salary sacrifice pricing."
  }'
```

### 4. Lead Details View with Chronological Activities (`asc` / `desc`)

```bash
# Default ascending chronological order (oldest -> newest)
curl -s "http://127.0.0.1:8000/api/v1/leads/8f14e45f-ea9a-4c6e-9b2a-1d3c4b5a6e7f?activity_sort=asc" | python3 -m json.tool

# Reverse chronological order (newest -> oldest)
curl -s "http://127.0.0.1:8000/api/v1/leads/8f14e45f-ea9a-4c6e-9b2a-1d3c4b5a6e7f?activity_sort=desc" | python3 -m json.tool
```

### 5. Log Activity & Atomically Update Lead State

Log a `CALL` against seeded `NEW` lead Amelia Clarke (`a2f3c4d5-1111-4222-8333-444444444401`) — automatically transitions `NEW -> CONTACTED` and sets `last_contacted_at`:

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/leads/a2f3c4d5-1111-4222-8333-444444444401/activities" \
  -H "Content-Type: application/json" \
  -d '{
    "activity_type": "CALL",
    "summary": "Initial discovery call — confirmed weekend availability",
    "notes": "Customer prefers Saturday morning slot.",
    "performed_by": "sarah.jenkins@keyloop-dealer.co.uk",
    "outcome": "CONNECTED",
    "occurred_at": "2026-11-23T11:30:00Z"
  }' | python3 -m json.tool
```

Log an internal `NOTE` (updates `updated_at` and `version`, does **not** alter `last_contacted_at` or `status`):

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/leads/8f14e45f-ea9a-4c6e-9b2a-1d3c4b5a6e7f/activities" \
  -H "Content-Type: application/json" \
  -d '{
    "activity_type": "NOTE",
    "summary": "Confirmed demonstrator vehicle charged to 95%",
    "performed_by": "sarah.jenkins@keyloop-dealer.co.uk"
  }' | python3 -m json.tool
```

### 6. Update Lead with Optimistic Locking (`PATCH /api/v1/leads/{lead_id}`)

```bash
curl -i -X PATCH "http://127.0.0.1:8000/api/v1/leads/8f14e45f-ea9a-4c6e-9b2a-1d3c4b5a6e7f" \
  -H "Content-Type: application/json" \
  -d '{
    "version": 3,
    "status": "NEGOTIATION",
    "assigned_to": "sarah.jenkins@keyloop-dealer.co.uk"
  }'
```

Re-sending the same stale `version` returns RFC 7807 `409 Conflict`.

### 7. Multi-Tenant Isolation (`X-Dealer-ID`)

Querying default dealership's lead using a different `X-Dealer-ID` returns RFC 7807 `404 Not Found`:

```bash
curl -i "http://127.0.0.1:8000/api/v1/leads/8f14e45f-ea9a-4c6e-9b2a-1d3c4b5a6e7f" \
  -H "X-Dealer-ID: 22222222-2222-4222-8222-222222222222"
```

---

## AI Collaboration Narrative

In alignment with Engineering Management best practices, Generative AI was used throughout this assessment as a **force-multiplying pair programmer and scaffolding accelerator**, operating under strict architectural governance, explicit domain constraints, and human-led verification. Every architectural boundary, data invariant, and operational guardrail was defined upfront and verified empirically before acceptance.

### 1. High-Level Strategy for Guiding the AI

Rather than issuing open-ended prompts (e.g., *"build a lead management API"*), the implementation followed a **Spec-Driven, Contract-First workflow** anchored to [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) (`v1.0.0`):

1. **Blueprint-First Constraint Setting**: Before generating any application code, the System Design Document locked down the target architecture (**Layered Modular Monolith**), Entity-Relationship schema, composite indexing strategy, Lead lifecycle state machine, and exact JSON/RFC 7807 wire contracts. The AI was instructed to treat `SYSTEM_DESIGN.md` as an immutable specification.
2. **Phased, Bottom-Up Layer Decomposition**: Work was sequenced strictly along dependency boundaries to prevent leaky abstractions:
   - *Phase 1 — Core & Cross-Cutting Infrastructure*: Configuration (`pydantic-settings`), domain enums/transition tables, domain exceptions, RFC 7807 handlers, and structured JSON logging.
   - *Phase 2 — Persistence & Data Contracts*: SQLAlchemy 2.0 `Mapped[]` models, dialect-portable custom types, composite indexes, and Pydantic v2 request/response DTOs.
   - *Phase 3 — Repositories, Domain Services & HTTP Middleware/Routers*: Encapsulating SQL queries (`selectinload`, conditional optimistic updates) away from business rules and HTTP transport.
   - *Phase 4 — Seed Tooling, Containerization & Verification Suite*: Deterministic automotive seed data, Docker/PostgreSQL 16 parity setup, and comprehensive Pytest suites.
3. **Explicit Guardrail Injection**: Non-negotiable production standards were specified directly in prompts—mandating `PRAGMA foreign_keys = ON;` on SQLite connections, single-transaction Unit of Work semantics for activity logging, `X-Correlation-ID` propagation via `contextvars`, multi-tenant scoping via `X-Dealer-ID`, and strict GDPR PII exclusion from stdout logs.

**Representative Prompting Pattern Used:**

```text
Role & Context:
  Act as a Senior Python Backend Engineer implementing Scenario C (Demand Domain)
  strictly against SYSTEM_DESIGN.md (v1.0.0) on Python 3.12+, FastAPI, Pydantic v2,
  and SQLAlchemy 2.0.

Architecture & Guardrails:
  - Layered Modular Monolith: isolate routers, schemas, services, repositories, ORM models, middleware.
  - DB Parity: compatible with SQLite & PostgreSQL 16; enforce PRAGMA foreign_keys = ON per SQLite connection;
    prevent N+1 queries on Lead Details via selectinload().
  - Atomicity & Concurrency: POST /leads/{id}/activities must insert the activity and update
    last_contacted_at, status, updated_at, and version inside a single DB transaction; enforce optimistic
    locking (version) on PATCH /leads/{id}; NOTE must not mutate last_contacted_at or force status changes.
  - Observability & Errors: RFC 7807 (application/problem+json) for 400/404/409/422/500/503; propagate
    X-Correlation-ID; emit structured JSON logs strictly excluding PII (email, phone, names, free-text notes).
```

### 2. Process for Verifying and Refining AI Output

All AI-generated code underwent line-by-line architectural review and live runtime inspection. Several subtle framework interactions and domain edge cases were identified, refined, or overridden during development:

- **Middleware Execution Order & `contextvars` Lifecycle Fix**:
  - *Finding*: During live smoke testing of structured stdout logs, `http.request.completed` access log entries initially emitted `"dealership_id": null` even when a valid tenant was resolved.
  - *Root Cause & Refinement*: Because Starlette middleware executes in LIFO order (`CorrelationIDMiddleware` -> `AccessLogMiddleware` -> `TenantContextMiddleware`), `TenantContextMiddleware` was resetting its `dealership_id_ctx` `ContextVar` in its `finally` block *before* control unwound back to `AccessLogMiddleware`. We refined `AccessLogMiddleware` ([app/middleware/access_log.py](app/middleware/access_log.py)) to read `request.state.dealership_id` directly on unwind and added an explicit regression assertion in [tests/test_observability_and_errors.py](tests/test_observability_and_errors.py) verifying non-null `dealership_id` across both domain and access log events.
- **SQLite ↔ PostgreSQL 16 Timestamp & Foreign-Key Parity**:
  - *Refinement*: Standard SQLAlchemy `DateTime(timezone=True)` returns naive datetimes on SQLite and can produce inconsistent lexicographical `ORDER BY` behavior if mixed offsets are stored. Rather than accepting dialect drift, we implemented a custom `UTCDateTime(TypeDecorator)` ([app/db/base.py](app/db/base.py)) that normalizes all persisted timestamps to UTC (naive ISO UTC in SQLite, `TIMESTAMPTZ` in PostgreSQL) and re-attaches `tzinfo=UTC` on load, paired with a Pydantic v2 `UTCDatetime` serializer outputting strict `Z`-suffixed ISO-8601 strings. SQLite's default-off foreign key enforcement was closed via a SQLAlchemy `connect` event hook (`PRAGMA foreign_keys = ON;`) and verified via dedicated test assertion.
- **Atomic Optimistic Concurrency & SQLAlchemy Identity Map Safety**:
  - *Refinement*: Naive read-modify-write ORM updates are vulnerable to lost updates when two sales executives edit the same lead simultaneously. We enforced an atomic SQL `UPDATE leads ... SET version = version + 1 WHERE id = :id AND version = :expected_version` check (`rowcount == 1`). Because `sessionmaker` uses `expire_on_commit=False`, we ensured explicit `session.refresh(lead)` calls post-commit in `LeadService` and `ActivityService` so serialized responses never serve stale in-memory ORM attributes.
- **Automotive Domain Edge Cases (Retroactive Logging & Terminal States)**:
  - *Refinement*: Sales executives frequently log phone calls retroactively after leaving the showroom floor. We refined `ActivityService._resolve_last_contacted_at` ([app/services/activity_service.py](app/services/activity_service.py)) to compute `max(current_last_contacted_at, occurred_at)` for outreach types so logging an earlier historical call never regresses `last_contacted_at` backwards, ensured internal `NOTE` entries leave `last_contacted_at` and `status` untouched, and protected terminal states (`CONVERTED`, `LOST`) from accidental status regression during post-sale handover logging.
- **Rejected Premature Infrastructure Complexity**:
  - *Override*: Consistent with the Stage 1 MVP scope in `SYSTEM_DESIGN.md`, suggestions to introduce Redis, Celery, or separate microservices were intentionally declined in favor of strong relational ACID guarantees within a clean modular monolith that preserves clear extraction seams for Stage 2/3 scale.

### 3. How Final Code Quality Was Ensured

Final readiness was validated through multiple independent quality gates:

1. **Automated Domain & API Contract Test Suite (`50 passed` in Pytest)**:
   - **Direct Business Logic & Service Unit Tests**: Exhaustive state-machine transition matrices (`validate_status_transition`), status non-regression rules on advanced/terminal leads, monotonic `last_contacted_at` resolution, partial `PATCH` field-set semantics (`model_fields_set`), and SQLAlchemy query-counter verification proving `get_lead_detail` executes strictly 2 `SELECT` queries regardless of activity volume ([tests/test_business_logic.py](tests/test_business_logic.py)).
   - **Per-Test Isolation**: Every test runs against a fresh in-memory SQLite database (`StaticPool` with foreign keys enabled) via composable FastAPI `TestClient` fixtures ([tests/conftest.py](tests/conftest.py)).
   - **Lifecycle & Rollback Coverage**: Parametrized tests verify automatic `NEW -> CONTACTED` transitions across all 5 outreach types (`CALL`, `EMAIL`, `SMS`, `QUOTE_SENT`, `MEETING`), `TEST_DRIVE_SCHEDULED` progression, `NOTE` invariance, `asc`/`desc` chronological ordering with retroactive `occurred_at`, and full transaction rollback when an invalid `new_lead_status` override (`409`) is rejected ([tests/test_activities_api.py](tests/test_activities_api.py)).
   - **Multi-Tenant, Concurrency & Validation Guardrails**: Dedicated tests verify cross-dealership `404` isolation (`X-Dealer-ID`), soft-delete exclusion (`deleted_at IS NULL`), `409` optimistic lock conflicts on stale `version`, `422` validation error arrays, `400` malformed JSON/header handling, `503` degraded readiness probes, and sanitized `500` responses ([tests/test_leads_api.py](tests/test_leads_api.py), [tests/test_health.py](tests/test_health.py)).
   - **Zero-PII Observability Audit**: Automated log-capture tests parse emitted stdout JSON lines to verify envelope completeness (`timestamp`, `level`, `logger`, `event`, `correlation_id`, `dealership_id`) and assert that customer `email`, `phone`, `first_name`, `last_name`, and free-text `notes` never appear in application logs ([tests/test_observability_and_errors.py](tests/test_observability_and_errors.py)).
2. **Query Performance & Schema Integrity**:
   - Audited ORM data access to confirm `GET /api/v1/leads/{lead_id}` uses `selectinload(Lead.activities)` (bounded to 2 SQL queries regardless of activity volume, eliminating N+1 queries) and that database `CHECK` constraints and composite indexes match Section 4 of the System Design Document.
3. **Operational & End-to-End Smoke Verification**:
   - Executed idempotent seeding (`python -m scripts.seed --reset` followed by repeat runs), performed live interactive testing through Swagger UI (`/docs`) creating and inspecting persisted leads directly in `keyloop_leads.db`, and packaged non-root Docker + Docker Compose configurations supporting both zero-dependency SQLite and production-parity PostgreSQL 16.
