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
├── SYSTEM_DESIGN.md                     # System Design Document (v1.0.0)
├── TEST_SPEC.md                         # Formal Test Specification & Traceability Matrix (125 cases)
├── .env.example                         # Environment variables template
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
    ├── test_observability_and_errors.py # Correlation ID, RFC 7807, zero-PII logs, tenancy
    └── test_edge_cases.py               # Full transition matrix, isolation, soft delete, dates, inbox inputs
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

See [TEST_SPEC.md](TEST_SPEC.md) for the formal Test Specification & Requirement Traceability Matrix covering all 125 test cases (`TC-BL-01` through `TC-EDGE-21`). Expected result: 124 passed, 1 xfailed. The xfail test is a known gap listed in Section 8.5 of the design document.

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

AI was used throughout this assessment. The full account, including what I changed, how I verified the output and what is still open, is in [Section 8 of SYSTEM_DESIGN.md](SYSTEM_DESIGN.md#8-genai-usage). In summary:

### 1. How I guided the AI

| Tool | Used for |
|---|---|
| **Gemini** (chat) | Domain research, structuring the design document, a first draft of assumptions, data model and API contracts, and delivery planning. |
| **Google Antigravity** | Implementing the service from `SYSTEM_DESIGN.md`: FastAPI layers, the pytest suite, seed data, Docker setup, and a first draft of this README. |
| **Claude** | Cross-model review of the finished design and code. |

The work was spec-first. I reworked Gemini's first blueprint before any code was written: dual activity timestamps (`occurred_at` and `created_at`), `dealership_id` on every table, a fuller lead lifecycle, and optimistic locking. Antigravity proposed FastAPI instead of Gemini's Next.js suggestion, and I accepted it for a backend-only submission. The finished `SYSTEM_DESIGN.md` was then the specification Antigravity built against.

### 2. How the output was verified and refined

- **Automated tests:** Antigravity generated 50 pytest cases covering lifecycle rules, API contracts, tenant isolation, optimistic locking, and zero-PII logging ([TEST_SPEC.md](TEST_SPEC.md)). I later added 74 edge-case tests with Claude ([tests/test_edge_cases.py](tests/test_edge_cases.py)), 3 of them marked xfail as known gaps in `occurred_at` handling. Two of those gaps were then fixed (a time without a time zone, and a time in the future, now return `422`), with one more test for the clock allowance. The third is left open as a product decision. I re-ran the full suite myself: 124 pass, 1 xfail.
- **Manual testing:** I tested the main flows in Swagger UI: creating a lead, retrieving a lead with its activities, and logging follow-up activities.
- **Middleware ordering:** Starlette middleware unwinds in reverse order, so the tenant middleware would clear its context variable before the access log is written. The access log reads the dealership from `request.state` instead, and a regression test in [tests/test_observability_and_errors.py](tests/test_observability_and_errors.py) checks it.
- **Cross-model review:** a review with Claude found that the design document had drifted from the code (the status diagram showed fewer transitions than the code allows, and Alembic was described but not used), and that an earlier version of this README overstated the process. Both documents were corrected.

### 3. Known limits

- When one agent writes both the code and the tests, the tests can share the code's blind spots. My manual testing covered the main paths, not every edge case.
- Performance targets have not been load-tested, and the PostgreSQL profile has had less testing than SQLite.
- Open items for production (token-based identity, `Idempotency-Key`, `occurred_at` before lead creation, retry on concurrent activity logging) are listed in Section 8 of the design document.
