# System Design Document: Sales Lead Management Tool (Demand Domain)

| Metadata | Details |
| :--- | :--- |
| **Document Title** | Sales Lead Management Tool — Backend System Design |
| **Target Context** | Keyloop Engineering Manager Technical Assessment — Scenario C (Domain: Demand) |
| **Version** | 1.0.0 |
| **Status** | Architecture Proposal & Implementation Blueprint |
| **Core Stack** | Python 3.12+, FastAPI, SQLAlchemy 2.0, Pydantic v2, SQLite (Dev/Test) / PostgreSQL 16 (Prod), Pytest |

---

## Executive Summary

In automotive retail, **speed-to-lead** and disciplined follow-up execution directly govern dealership conversion rates and customer satisfaction. This document specifies the backend architecture for **Scenario C: The Sales Lead Management Tool** within the **Demand** domain. The system provides dealership sales executives with a reliable, low-latency REST API to triage incoming website leads (**Lead Inbox**), inspect a complete customer engagement history (**Lead Details View**), and record follow-up interactions (**Activity Logging**) with strict transactional consistency.

To balance rapid delivery for the assessment MVP with enterprise readiness for Keyloop's multi-dealership automotive ecosystem, the system adopts a **Layered Modular Monolith** architecture with strict domain boundaries, RFC 7807 standardized error contracts, structured observability, and a clear horizontal scaling roadmap.

---

## 1. Architecture Overview

### 1.1 Architectural Style: Layered Modular Monolith

Rather than introducing premature microservice complexity, the backend is designed as a **Layered Modular Monolith** following Dependency Inversion principles:

- **Clear Separation of Concerns**: HTTP transport (Routers/Schemas), business orchestration (Services), and persistence mechanics (Repositories/ORM) are isolated into distinct layers.
- **Strong ACID Consistency**: Recording an activity and updating the parent lead's `last_contacted_at` timestamp and lifecycle status execute atomically within a single database transaction.
- **Future Extractability**: Because business logic is decoupled from both FastAPI and raw SQL, domain modules (e.g., `leads`, `activities`, future `notifications`) can be extracted into independent services or event-driven consumers without rewriting core domain rules.

### 1.2 System Architecture Diagram

```mermaid
flowchart TB
    subgraph Clients["Clients & API Consumers"]
        WebUI["Dealership Web UI (Sales Executive)"]
        Website["Dealer Website / Lead Aggregator"]
        Swagger["Swagger UI / OpenAPI 3.1 Docs"]
    end

    subgraph Edge["API Gateway & FastAPI Middleware Layer"]
        ASGI["Uvicorn ASGI Server"]
        MW_Corr["Correlation ID Middleware (X-Correlation-ID)"]
        MW_Log["Structured Access Logging Middleware"]
        MW_Tenant["Tenant & Auth Context (X-Dealer-ID / JWT)"]
        MW_Err["Global Exception Handler (RFC 7807)"]
    end

    subgraph Presentation["Presentation Layer (Routers & Contracts)"]
        LeadRouter["Lead Router (/api/v1/leads)"]
        ActivityRouter["Activity Router (/api/v1/leads/{id}/activities)"]
        HealthRouter["Health Router (/health/live, /health/ready)"]
        Pydantic["Pydantic v2 Schemas (Validation & Serialization)"]
    end

    subgraph Domain["Service Layer (Business Logic & UoW)"]
        LeadService["LeadService (Inbox Query, Transitions, Details)"]
        ActivityService["ActivityService (Log Activity & Sync Lead State)"]
    end

    subgraph DataAccess["Repository Layer (SQLAlchemy 2.0)"]
        LeadRepo["LeadRepository"]
        ActivityRepo["ActivityRepository"]
        UoW["SQLAlchemy Session / Transaction Manager"]
    end

    subgraph Persistence["Persistence Layer"]
        DB[("SQLite (Dev/Test) / PostgreSQL 16 (Prod)")]
        Alembic["Alembic Schema Migrations"]
    end

    subgraph Observability["Cross-Cutting Observability"]
        JSONLogs["Structured JSON Logs (stdout -> ELK / Datadog)"]
        Metrics["OpenTelemetry Traces & RED Metrics"]
    end

    WebUI --> ASGI
    Website --> ASGI
    Swagger --> ASGI

    ASGI --> MW_Corr --> MW_Log --> MW_Tenant --> MW_Err

    MW_Err --> LeadRouter
    MW_Err --> ActivityRouter
    MW_Err --> HealthRouter

    LeadRouter <--> Pydantic
    ActivityRouter <--> Pydantic

    LeadRouter --> LeadService
    ActivityRouter --> ActivityService
    HealthRouter --> UoW

    LeadService --> LeadRepo
    ActivityService --> ActivityRepo
    ActivityService --> LeadRepo

    LeadRepo --> UoW
    ActivityRepo --> UoW
    UoW --> DB
    Alembic -.-> DB

    MW_Log -.-> JSONLogs
    LeadService -.-> JSONLogs
    ActivityService -.-> JSONLogs
    Edge -.-> Metrics
    UoW -.-> Metrics
```

---

## 2. Key Assumptions & Design Decisions

Where the assessment brief intentionally leaves requirements open, the following pragmatic, automotive-domain-aligned assumptions have been established:

### 2.1 Lead Lifecycle & Status Progression
- **Defined Statuses**: `NEW`, `CONTACTED`, `QUALIFIED`, `TEST_DRIVE_SCHEDULED`, `NEGOTIATION`, `CONVERTED`, `LOST`.
- **Automatic Progression on Activity Logging**:
  - When a substantive customer interaction (`CALL`, `EMAIL`, `SMS`, `QUOTE_SENT`, `MEETING`) is logged against a `NEW` lead, the service automatically transitions the lead status from `NEW` to `CONTACTED`.
  - When a `TEST_DRIVE_SCHEDULED` activity is logged against a non-terminal lead, the status automatically advances to `TEST_DRIVE_SCHEDULED` (unless the caller provides an explicit `new_lead_status` override).
  - Logging an internal `NOTE` updates `updated_at` but does **not** automatically change the lead status or `last_contacted_at`.
- **Terminal States**: `CONVERTED` and `LOST` leads still permit retrospective activity logging (e.g., post-sale handover notes) without regressing their status unless explicitly reopened via `PATCH /api/v1/leads/{lead_id}`.

```mermaid
stateDiagram-v2
    [*] --> NEW : Website Enquiry Received
    NEW --> CONTACTED : First Outreach Activity Logged
    CONTACTED --> QUALIFIED : Needs & Budget Confirmed
    QUALIFIED --> TEST_DRIVE_SCHEDULED : Test Drive Booked
    TEST_DRIVE_SCHEDULED --> NEGOTIATION : Quote / Finance Discussed
    QUALIFIED --> NEGOTIATION : Direct Quote Requested
    NEGOTIATION --> CONVERTED : Deal Closed (Won)
    NEW --> LOST : Unreachable / Duplicate
    CONTACTED --> LOST : No Longer Interested
    QUALIFIED --> LOST : Lost to Competitor
    TEST_DRIVE_SCHEDULED --> LOST : Declined After Test Drive
    NEGOTIATION --> LOST : Price / Finance Declined
    LOST --> CONTACTED : Re-engaged by Customer
```

### 2.2 Activity Taxonomy & Audit Immutability
- **Supported Activity Types**: `CALL`, `EMAIL`, `SMS`, `TEST_DRIVE_SCHEDULED`, `QUOTE_SENT`, `MEETING`, `NOTE`, `STATUS_CHANGE`.
- **Append-Only Audit Log**: Follow-up activities are treated as **immutable historical records** once persisted (no `PUT`/`DELETE` endpoints for activities in MVP). This preserves compliance and auditability for dealership managers reviewing sales execution.

### 2.3 Chronological Ordering Semantics
- **Dual Timestamps**: Each activity tracks `occurred_at` (when the interaction actually happened; defaults to UTC `now()` if omitted, allowing sales executives to log calls retroactively) and `created_at` (immutable server ingestion timestamp).
- **Default Ordering**: The Lead Details View returns activities in **ascending chronological order** (`occurred_at ASC, created_at ASC, id ASC`) to tell the complete story from first enquiry to latest follow-up. An optional query parameter (`activity_sort=desc`) allows UI consumers to flip to reverse-chronological order if preferred.

### 2.4 Multi-Dealership Context & Authentication (MVP vs. Production)
- **Tenant Readiness Without Friction**: Every lead record includes a `dealership_id` column (defaulting to a seeded dealership UUID in MVP, or read from an optional `X-Dealer-ID` header). This keeps local evaluation zero-config while ensuring all queries and indexes are multi-tenant ready from Day 1.
- **Actor Attribution**: In the MVP, `performed_by` (e.g., `"sarah.jenkins@dealer.co.uk"`) is accepted in the activity creation payload and validated as non-empty. In production, this identity is strictly extracted from a verified OIDC/JWT `sub` claim issued by Keyloop's Identity Provider (IdP) to prevent spoofing.

### 2.5 Pagination, Soft Deletion & Timezones
- **Pagination**: Offset pagination (`page`, `page_size` defaulting to `20`, max `100`) is used for the Lead Inbox to support standard page controls and total record counts. Migration to cursor/keyset pagination is addressed in Section 7.4.
- **Identifiers & Timezones**: All primary keys are **UUIDv4** (preventing sequential ID enumeration across dealerships). All timestamps are stored and serialized in **UTC ISO-8601** (`Z` suffix); timezone localization is delegated to the presentation client.
- **GDPR / Soft Deletion**: `leads` includes a nullable `deleted_at` column to support soft deletion and future GDPR right-to-erasure anonymization workflows without breaking referential integrity.

---

## 3. Component Responsibilities & Data Flows

### 3.1 Component Responsibility Matrix

| Component | Layer | Primary Responsibilities | Explicit Non-Responsibilities |
| :--- | :--- | :--- | :--- |
| **Middleware Stack** | Edge / HTTP | Generate/propagate `X-Correlation-ID`, emit structured access logs, extract tenant context, translate unhandled exceptions to RFC 7807. | Business rules, database queries. |
| **FastAPI Routers** | Presentation | Define versioned REST routes, parse query/path parameters, bind Pydantic schemas, invoke services via DI, map responses to HTTP status codes. | Transaction management, direct ORM queries. |
| **Pydantic v2 Schemas** | Presentation | Strict input validation (email format, enums, string bounds, pagination limits) and response DTO serialization. | Persistence logic, database session handling. |
| **Service Layer** | Domain | Enforce business invariants (status transitions, `last_contacted_at` computation), orchestrate multi-repository operations within a single transaction, emit domain audit logs. | HTTP status codes, raw SQL dialect details. |
| **Repository Layer** | Data Access | Encapsulate SQLAlchemy 2.0 queries, dynamic filtering/sorting, eager loading (`selectinload`), and database persistence primitives. | Business workflow rules, HTTP error formatting. |
| **ORM Models & UoW** | Persistence | Define relational schema, constraints, indexes, and transaction lifecycle (`commit` / `rollback`). | Request validation, API response shaping. |

### 3.2 Core Data Flows

#### Flow A: Lead Inbox Query (`GET /api/v1/leads`)
1. Client requests `/api/v1/leads` with optional filters (`status`, `source`, `assigned_to`, `search`), sorting (`sort_by`, `sort_order`), and pagination (`page`, `page_size`).
2. `LeadRouter` validates query parameters via Pydantic dependency models (rejecting unknown sort fields or `page_size > 100` with `422 Unprocessable Entity`).
3. `LeadService` scopes the query to the active `dealership_id` and excludes soft-deleted rows (`deleted_at IS NULL`).
4. `LeadRepository` executes:
   - A filtered `COUNT(*)` query for pagination metadata.
   - A filtered, deterministically sorted `SELECT` query with `LIMIT`/`OFFSET` leveraging composite indexes (without eagerly loading child `activities` to keep inbox payloads lightweight).
5. `LeadRouter` returns `200 OK` with `items` and `pagination` metadata.

#### Flow B: Lead Details View (`GET /api/v1/leads/{lead_id}`)
1. Client requests `/api/v1/leads/{lead_id}?activity_sort=asc`.
2. `LeadRouter` validates `lead_id` as a valid UUID.
3. `LeadService` calls `LeadRepository.get_by_id_with_activities(lead_id, dealership_id, activity_sort)`.
4. `LeadRepository` loads the lead and its associated activities using SQLAlchemy's `selectinload()` (2 bounded queries total, strictly avoiding the **N+1 query problem**) ordered by `(occurred_at, created_at, id)`.
5. If no matching lead exists (or belongs to another dealership), `LeadService` raises `LeadNotFoundError`, which the global handler converts into an RFC 7807 `404 Not Found` response.
6. Otherwise, `LeadRouter` serializes the `LeadDetailResponse` (lead profile + chronological `activities` array) and returns `200 OK`.

#### Flow C: Activity Logging & Atomic Lead Synchronization (`POST /api/v1/leads/{lead_id}/activities`)

```mermaid
sequenceDiagram
    autonumber
    participant Client as Sales Executive UI
    participant MW as FastAPI Middleware
    participant Router as ActivityRouter
    participant Service as ActivityService
    participant Repo as Lead & Activity Repos
    participant DB as SQLite / PostgreSQL

    Client->>MW: POST /api/v1/leads/{lead_id}/activities<br/>(JSON + X-Correlation-ID)
    MW->>Router: Forward validated HTTP request
    Router->>Router: Validate payload via ActivityCreate schema
    Router->>Service: log_activity(dealership_id, lead_id, payload)
    Service->>DB: BEGIN TRANSACTION
    Service->>Repo: Fetch Lead by (lead_id, dealership_id)
    Repo->>DB: SELECT * FROM leads<br/>WHERE id = ? AND dealership_id = ? AND deleted_at IS NULL
    alt Lead Not Found
        DB-->>Repo: Empty result
        Service->>DB: ROLLBACK
        Service-->>MW: Raise LeadNotFoundError
        MW-->>Client: 404 Not Found (RFC 7807 Problem Details)
    else Lead Exists
        DB-->>Repo: Lead entity
        Service->>Service: Validate status transition &<br/>compute new last_contacted_at
        Service->>Repo: Insert Activity record
        Repo->>DB: INSERT INTO activities (...) VALUES (...)
        Service->>Repo: Update Lead (status, last_contacted_at,<br/>updated_at, version + 1)
        Repo->>DB: UPDATE leads SET ...<br/>WHERE id = ? AND version = ?
        Service->>DB: COMMIT TRANSACTION
        Service->>MW: Emit structured log (event="activity.logged")
        Service-->>Router: Return Activity + Updated Lead Summary
        Router-->>Client: 201 Created (ActivityCreatedResponse)
    end
```

---

## 4. Database Schema & Indexing Strategy

### 4.1 Entity-Relationship Diagram

```mermaid
erDiagram
    LEADS ||--o{ ACTIVITIES : "tracks follow-ups"

    LEADS {
        uuid id PK "UUIDv4 Primary Key"
        uuid dealership_id "Tenant / Dealership Identifier"
        varchar first_name "Customer first name (max 100)"
        varchar last_name "Customer last name (max 100)"
        varchar email "Customer email (max 255)"
        varchar phone "Customer phone E.164 (max 30, nullable)"
        varchar source "Enum: DEALER_WEBSITE, AUTO_TRADER, etc."
        varchar status "Enum: NEW, CONTACTED, QUALIFIED, etc."
        varchar vehicle_of_interest "e.g., 2025 BMW 320i M Sport (nullable)"
        text enquiry_notes "Initial web form message (nullable)"
        varchar assigned_to "Sales executive ID/email (nullable)"
        timestamp last_contacted_at "Latest customer outreach UTC (nullable)"
        integer version "Optimistic locking counter (default 1)"
        timestamp created_at "Record creation UTC"
        timestamp updated_at "Last modification UTC"
        timestamp deleted_at "Soft-delete timestamp UTC (nullable)"
    }

    ACTIVITIES {
        uuid id PK "UUIDv4 Primary Key"
        uuid lead_id FK "References leads(id) ON DELETE CASCADE"
        varchar activity_type "Enum: CALL, EMAIL, TEST_DRIVE_SCHEDULED, etc."
        varchar summary "Short headline (max 255)"
        text notes "Detailed call/meeting notes (nullable)"
        varchar performed_by "Sales executive who logged activity (max 150)"
        varchar outcome "Optional outcome tag e.g. CONNECTED, VOICEMAIL"
        timestamp occurred_at "When interaction occurred UTC"
        timestamp created_at "Server audit ingestion timestamp UTC"
    }
```

### 4.2 Table Design & Constraints

1. **`leads` Table**:
   - **Primary Key**: `id` (UUID stored via a dialect-portable SQLAlchemy `Uuid` type — native `UUID` in PostgreSQL, `CHAR(32)/CHAR(36)` in SQLite).
   - **Data Integrity**: `NOT NULL` enforced on `dealership_id`, `first_name`, `last_name`, `email`, `source`, `status`, `version`, `created_at`, and `updated_at`. Application-level Enum validation is paired with database `CHECK` constraints for defense-in-depth.
   - **Denormalized Read Optimization**: Storing `last_contacted_at` directly on `leads` avoids expensive correlated `MAX(activities.occurred_at)` subqueries when sorting or filtering the Lead Inbox by follow-up recency.
   - **Optimistic Concurrency**: The `version` integer column is incremented on every update to prevent lost updates if two sales executives modify the same lead concurrently.

2. **`activities` Table**:
   - **Foreign Key**: `lead_id` references `leads(id)` with `ON DELETE CASCADE`.
   - **SQLite Parity Guardrail**: Because SQLite disables foreign key enforcement by default, the SQLAlchemy engine registers a `connect` event hook executing `PRAGMA foreign_keys = ON;` on every SQLite connection, ensuring test and local behavior matches PostgreSQL.
   - **Audit Clarity**: Separating `occurred_at` from `created_at` supports both accurate customer timelines (when an activity is logged 15 minutes after a phone call) and strict audit trails.

### 4.3 Indexing Strategy

Indexes are designed strictly around the application's primary read/write access patterns to balance query speed against write overhead:

| Index Name | Table | Columns | Query Pattern Optimized |
| :--- | :--- | :--- | :--- |
| `pk_leads` | `leads` | `(id)` | Primary key lookups (`GET /leads/{id}`, FK joins). |
| `idx_leads_tenant_status_created` | `leads` | `(dealership_id, status, created_at DESC)` | **Lead Inbox default view**: filter by dealership & status, sorted newest-first without filesort. |
| `idx_leads_tenant_source_created` | `leads` | `(dealership_id, source, created_at DESC)` | **Lead Inbox source filtering**: e.g., show all `DEALER_WEBSITE` leads newest-first. |
| `idx_leads_tenant_last_contacted` | `leads` | `(dealership_id, last_contacted_at ASC)` | **SLA / Follow-up triage**: quickly surface leads untouched for the longest duration (`NULLS FIRST` in Postgres). |
| `idx_leads_tenant_email` | `leads` | `(dealership_id, email)` | Duplicate lead detection and returning-customer lookup. |
| `idx_activities_lead_chronological` | `activities` | `(lead_id, occurred_at ASC, created_at ASC)` | **Lead Details View**: retrieves all activities for a lead already in deterministic chronological order via an index range scan. |

> **PostgreSQL Production Enhancements**: In production, inbox indexes should be defined as **partial indexes** (`WHERE deleted_at IS NULL`) to reduce index bloat, and a GIN trigram index (`pg_trgm`) on `(first_name, last_name, email, vehicle_of_interest)` can accelerate substring `search` queries without requiring an external search engine initially.

---

## 5. RESTful API Contract

### 5.1 API Design Conventions
- **Base Path**: `/api/v1` (URI path versioning for explicit backward compatibility).
- **Content Types**: `application/json` for success payloads; `application/problem+json` (RFC 7807) for all error responses.
- **Standard Headers**:
  - `X-Correlation-ID` (optional request header, always echoed in response).
  - `X-Dealer-ID` (optional UUID header for multi-dealership scoping; defaults to the configured dealership in MVP).
  - `Idempotency-Key` (optional UUID header on `POST` endpoints to prevent duplicate submissions on network retries).

### 5.2 Endpoint Inventory

| Method | Endpoint | Purpose | Success Code |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/leads` | **Lead Inbox**: Paginated, filterable, sortable list of leads. | `200 OK` |
| `POST` | `/api/v1/leads` | **Lead Ingestion**: Create a new sales lead (web form intake / seeding). | `201 Created` |
| `GET` | `/api/v1/leads/{lead_id}` | **Lead Details View**: Full lead profile + chronological activity log. | `200 OK` |
| `PATCH` | `/api/v1/leads/{lead_id}` | **Lead Update**: Partially update lead status, assignee, or contact details. | `200 OK` |
| `POST` | `/api/v1/leads/{lead_id}/activities` | **Activity Logging**: Log a follow-up activity & atomically update lead state. | `201 Created` |
| `GET` | `/api/v1/leads/{lead_id}/activities` | **Activity Feed**: Paginated activities sub-resource (for leads with extensive history). | `200 OK` |
| `GET` | `/health/live` | **Liveness Probe**: Confirms application process is responsive. | `200 OK` |
| `GET` | `/health/ready` | **Readiness Probe**: Confirms active database connectivity. | `200 OK` |

---

### 5.3 Detailed Endpoint Specifications

#### 1. Lead Inbox — `GET /api/v1/leads`

**Query Parameters**:
- `status` *(optional, repeatable or comma-separated)*: Filter by lead status (e.g., `NEW`, `CONTACTED`).
- `source` *(optional)*: Filter by lead source (e.g., `DEALER_WEBSITE`, `AUTO_TRADER`).
- `assigned_to` *(optional)*: Filter by assigned sales executive.
- `search` *(optional)*: Case-insensitive partial match against customer name, email, or `vehicle_of_interest`.
- `sort_by` *(optional, default `created_at`)*: Allowed values: `created_at`, `updated_at`, `last_contacted_at`.
- `sort_order` *(optional, default `desc`)*: Allowed values: `asc`, `desc`.
- `page` *(optional, default `1`, min `1`)*: Page number.
- `page_size` *(optional, default `20`, min `1`, max `100`)*: Items per page.

**Sample Response (`200 OK`)**:
```json
{
  "items": [
    {
      "id": "8f14e45f-ea9a-4c6e-9b2a-1d3c4b5a6e7f",
      "dealership_id": "11111111-1111-4111-8111-111111111111",
      "first_name": "Oliver",
      "last_name": "Bennett",
      "email": "oliver.bennett@example.co.uk",
      "phone": "+447700900123",
      "source": "DEALER_WEBSITE",
      "status": "CONTACTED",
      "vehicle_of_interest": "2025 Audi Q4 e-tron 45 S Line",
      "assigned_to": "sarah.jenkins@keyloop-dealer.co.uk",
      "last_contacted_at": "2026-11-23T10:15:00Z",
      "created_at": "2026-11-23T09:00:00Z",
      "updated_at": "2026-11-23T10:15:02Z"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_items": 47,
    "total_pages": 3,
    "has_next": true,
    "has_previous": false
  }
}
```

---

#### 2. Lead Details View — `GET /api/v1/leads/{lead_id}`

**Query Parameters**:
- `activity_sort` *(optional, default `asc`)*: `asc` (chronological, oldest-to-newest) or `desc` (newest-to-oldest).

**Sample Response (`200 OK`)**:
```json
{
  "id": "8f14e45f-ea9a-4c6e-9b2a-1d3c4b5a6e7f",
  "dealership_id": "11111111-1111-4111-8111-111111111111",
  "first_name": "Oliver",
  "last_name": "Bennett",
  "email": "oliver.bennett@example.co.uk",
  "phone": "+447700900123",
  "source": "DEALER_WEBSITE",
  "status": "TEST_DRIVE_SCHEDULED",
  "vehicle_of_interest": "2025 Audi Q4 e-tron 45 S Line",
  "enquiry_notes": "Interested in PCP finance options and part-exchange for a 2021 Golf.",
  "assigned_to": "sarah.jenkins@keyloop-dealer.co.uk",
  "last_contacted_at": "2026-11-23T14:00:00Z",
  "version": 3,
  "created_at": "2026-11-23T09:00:00Z",
  "updated_at": "2026-11-23T14:00:05Z",
  "activities": [
    {
      "id": "a1b2c3d4-0001-4000-8000-000000000001",
      "lead_id": "8f14e45f-ea9a-4c6e-9b2a-1d3c4b5a6e7f",
      "activity_type": "CALL",
      "summary": "Called customer — discussed Q4 e-tron availability",
      "notes": "Confirmed blue metallic is in stock. Customer requested PCP illustration.",
      "performed_by": "sarah.jenkins@keyloop-dealer.co.uk",
      "outcome": "CONNECTED",
      "occurred_at": "2026-11-23T10:15:00Z",
      "created_at": "2026-11-23T10:15:02Z"
    },
    {
      "id": "a1b2c3d4-0002-4000-8000-000000000002",
      "lead_id": "8f14e45f-ea9a-4c6e-9b2a-1d3c4b5a6e7f",
      "activity_type": "TEST_DRIVE_SCHEDULED",
      "summary": "Scheduled test drive for Saturday at 11:00 AM",
      "notes": "Booked demonstrator vehicle Reg: KL25 EVX. Sent calendar invite.",
      "performed_by": "sarah.jenkins@keyloop-dealer.co.uk",
      "outcome": "BOOKED",
      "occurred_at": "2026-11-23T14:00:00Z",
      "created_at": "2026-11-23T14:00:05Z"
    }
  ]
}
```

---

#### 3. Activity Logging — `POST /api/v1/leads/{lead_id}/activities`

**Sample Request Payload**:
```json
{
  "activity_type": "QUOTE_SENT",
  "summary": "Sent 48-month PCP finance quote via email",
  "notes": "Includes £4,000 deposit contribution and part-exchange valuation of £14,500.",
  "performed_by": "sarah.jenkins@keyloop-dealer.co.uk",
  "outcome": "SENT",
  "occurred_at": "2026-11-23T15:30:00Z",
  "new_lead_status": "NEGOTIATION"
}
```

*(Note: `occurred_at`, `notes`, `outcome`, and `new_lead_status` are optional. If `occurred_at` is omitted, the server assigns current UTC time. If `new_lead_status` is omitted, automatic transition rules from Section 2.1 apply.)*

**Sample Response (`201 Created`)**:
```json
{
  "activity": {
    "id": "a1b2c3d4-0003-4000-8000-000000000003",
    "lead_id": "8f14e45f-ea9a-4c6e-9b2a-1d3c4b5a6e7f",
    "activity_type": "QUOTE_SENT",
    "summary": "Sent 48-month PCP finance quote via email",
    "notes": "Includes £4,000 deposit contribution and part-exchange valuation of £14,500.",
    "performed_by": "sarah.jenkins@keyloop-dealer.co.uk",
    "outcome": "SENT",
    "occurred_at": "2026-11-23T15:30:00Z",
    "created_at": "2026-11-23T15:30:04Z"
  },
  "lead_snapshot": {
    "id": "8f14e45f-ea9a-4c6e-9b2a-1d3c4b5a6e7f",
    "status": "NEGOTIATION",
    "last_contacted_at": "2026-11-23T15:30:00Z",
    "updated_at": "2026-11-23T15:30:04Z",
    "version": 4
  }
}
```

---

#### 4. Lead Creation — `POST /api/v1/leads`

**Sample Request Payload**:
```json
{
  "first_name": "Amelia",
  "last_name": "Clarke",
  "email": "amelia.clarke@example.co.uk",
  "phone": "+447700900456",
  "source": "DEALER_WEBSITE",
  "vehicle_of_interest": "2025 Volvo EX30 Twin Motor",
  "enquiry_notes": "Looking to book a weekend test drive."
}
```

**Sample Response (`201 Created`, Header `Location: /api/v1/leads/{id}`)**:
Returns the created Lead resource with `status: "NEW"` and `last_contacted_at: null`.

---

#### 5. Standardized Error Response (RFC 7807 Problem Details)

**Sample `404 Not Found` (`Content-Type: application/problem+json`)**:
```json
{
  "type": "https://api.keyloop.example/problems/lead-not-found",
  "title": "Lead Not Found",
  "status": 404,
  "detail": "Lead with id '8f14e45f-ea9a-4c6e-9b2a-000000000000' was not found for the active dealership.",
  "instance": "/api/v1/leads/8f14e45f-ea9a-4c6e-9b2a-000000000000/activities",
  "correlation_id": "c7a8d9e0-1234-4567-89ab-cdef01234567"
}
```

**Sample `422 Unprocessable Entity` (`Content-Type: application/problem+json`)**:
```json
{
  "type": "https://api.keyloop.example/problems/validation-error",
  "title": "Request Validation Failed",
  "status": 422,
  "detail": "One or more request fields failed validation.",
  "instance": "/api/v1/leads/8f14e45f-ea9a-4c6e-9b2a-1d3c4b5a6e7f/activities",
  "correlation_id": "d8b9e0f1-2345-4678-9abc-def012345678",
  "errors": [
    {
      "field": "body.activity_type",
      "message": "Input should be 'CALL', 'EMAIL', 'SMS', 'TEST_DRIVE_SCHEDULED', 'QUOTE_SENT', 'MEETING', 'NOTE' or 'STATUS_CHANGE'"
    }
  ]
}
```

### 5.4 HTTP Status Code Matrix

| Status Code | Meaning | When Used |
| :--- | :--- | :--- |
| `200 OK` | Success | `GET` requests, `PATCH` updates, healthy probes. |
| `201 Created` | Resource Created | Successful `POST /leads` and `POST /leads/{id}/activities`. |
| `400 Bad Request` | Malformed Request | Malformed JSON syntax or invalid UUID/header format. |
| `404 Not Found` | Resource Missing | Target `lead_id` does not exist, is soft-deleted, or belongs to another dealership. |
| `409 Conflict` | State / Concurrency Conflict | Optimistic lock `version` mismatch or invalid business state transition. |
| `422 Unprocessable Entity` | Semantic Validation Error | Invalid enum value, invalid email, out-of-range pagination parameter. |
| `500 Internal Server Error` | Unexpected Fault | Unhandled exception (sanitized response; full stack trace logged internally with `correlation_id`). |
| `503 Service Unavailable` | Dependency Unhealthy | `/health/ready` fails database connectivity check. |

---

## 6. Tech Stack Justification

From an Engineering Management perspective, technology selection optimizes for **team productivity, long-term maintainability, contract safety, and smooth progression from local prototype to enterprise production**.

| Technology | Role | Why Chosen | Alternatives Considered & Trade-offs |
| :--- | :--- | :--- | :--- |
| **FastAPI (Python 3.12+)** | Web / API Framework | Native **Pydantic v2** validation (Rust-backed speed), first-class **OpenAPI 3.1 / Swagger UI** auto-generation (eliminates spec drift between frontend and backend teams), intuitive Dependency Injection (`Depends`) for clean testing and tenant scoping, and high ASGI concurrency. | **Django / DRF**: Heavier boilerplate for a focused microservice/API. **Flask**: Requires assembling multiple third-party plugins for validation, OpenAPI, and DI. |
| **SQLAlchemy 2.0 + Alembic** | ORM, Query Builder & Migrations | Type-safe `Mapped[]` declarative syntax aligns with static type checkers (`mypy`/`pyright`); explicit Unit of Work transaction control; granular eager loading (`selectinload`) prevents N+1 regressions; seamless dialect portability between SQLite and PostgreSQL. | **Raw SQL / Psycopg**: Higher maintenance cost for dynamic Lead Inbox filters and schema portability. **SQLModel**: Thinner ecosystem maturity for complex query tuning compared to direct SQLAlchemy 2.0 + Pydantic v2 separation. |
| **SQLite (Dev/Test) -> PostgreSQL 16 (Prod)** | Relational Database | **SQLite** provides zero-dependency local setup for reviewers and sub-second automated test suites. **PostgreSQL 16** provides production MVCC concurrency, strict transactional integrity, Row-Level Security (RLS) for multi-tenancy, partial indexes, and `pg_trgm` text search. | **NoSQL (MongoDB/DynamoDB)**: Lead-to-activity data is inherently relational with ad-hoc multi-field filtering/sorting and strict transactional requirements; relational SQL is the natural fit. *(CI pipeline should run integration tests against a real PostgreSQL container to catch dialect edge cases early.)* |
| **Pytest + HTTPX** | Automated Testing Framework | Composable fixture hierarchy enables clean per-test database isolation; `pytest.mark.parametrize` cleanly covers filtering/transition matrices; native integration with FastAPI's `TestClient` / `AsyncClient` supports fast API contract testing alongside unit tests. | **unittest**: More verbose boilerplate and weaker fixture composition than Pytest. |

---

## 7. Observability, Scalability & Reliability Strategy

### 7.1 Observability (Logs, Traces & Metrics)

1. **Structured JSON Logging**:
   - Emit single-line JSON logs to `stdout` (using `structlog` or Python's `logging` with a JSON formatter), ready for ingestion by Datadog, AWS CloudWatch, or OpenSearch/ELK.
   - **Standard Log Envelope**: `timestamp`, `level`, `logger`, `event`, `correlation_id`, `dealership_id`, `http_method`, `path`, `status_code`, `duration_ms`.
   - **GDPR & PII Protection**: Customer PII (`email`, `phone`, `first_name`, `last_name`, free-text `notes`) is **explicitly excluded** from application logs. Log only opaque entity IDs (`lead_id`, `activity_id`) and non-PII metadata (`status`, `activity_type`, `source`).
2. **End-to-End Correlation ID Propagation**:
   - Inbound middleware reads `X-Correlation-ID` (or generates a UUIDv4 if absent), binds it to Python `contextvars` so every downstream log statement automatically carries it, injects it into RFC 7807 error payloads, and returns it in the HTTP response header.
3. **Distributed Tracing & Metrics (Production Readiness)**:
   - Instrument FastAPI and SQLAlchemy with **OpenTelemetry** (`opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-sqlalchemy`) to capture trace spans across HTTP requests and SQL queries.
   - Track **RED Metrics** (Request Rate, Error Rate, Latency Duration p50/p95/p99) and database connection pool saturation.
   - **Target SLOs**: `99.9%` API availability; `p95 < 150ms` for Lead Inbox and Lead Details queries; `p95 < 250ms` for Activity Logging writes.

### 7.2 Health Checks & Graceful Lifecycle
- **Liveness (`/health/live`)**: Returns `200 OK` immediately if the event loop/worker process is responsive. Performs zero external I/O so transient DB blips do not cause cascading container restarts.
- **Readiness (`/health/ready`)**: Executes a lightweight `SELECT 1` query against the database with a strict timeout (e.g., 2 seconds). Returns `200 OK` when healthy or `503 Service Unavailable` when degraded, allowing Kubernetes / load balancers to drain traffic safely.
- **Graceful Shutdown**: Handle `SIGTERM` via Uvicorn lifespan hooks to drain in-flight HTTP requests and cleanly dispose of SQLAlchemy connection pools before process termination.

### 7.3 Error Handling & Reliability Guardrails
- **RFC 7807 Centralized Exception Mapping**: All domain exceptions (`LeadNotFoundError`, `InvalidStatusTransitionError`, `OptimisticLockError`), FastAPI validation errors, and unexpected `500` faults are intercepted by registered exception handlers and serialized into `application/problem+json`. Stack traces are never exposed to clients in production.
- **Database Resilience**: Configure SQLAlchemy connection pooling (`pool_size`, `max_overflow`, `pool_pre_ping = True`, `pool_recycle = 1800`) to automatically recover from stale or dropped PostgreSQL connections.
- **Idempotency for Write Endpoints**: In production, support an `Idempotency-Key` header backed by an idempotency store (Redis or dedicated DB table with 24h TTL) on `POST /leads` and `POST /leads/{id}/activities` so mobile/unstable dealership Wi-Fi retries never create duplicate leads or duplicate call logs.

### 7.4 Scalability Roadmap: From Single Dealership to Keyloop Multi-Dealership Scale

| Growth Stage | Scale Profile | Architectural Evolution |
| :--- | :--- | :--- |
| **Stage 1: MVP (Current Scope)** | 1–10 dealerships, < 50k leads | Single stateless FastAPI container, SQLite (dev) / PostgreSQL (prod), offset pagination, synchronous ACID writes. |
| **Stage 2: Dealership Group Scale** | 100s–1,000s of dealerships, millions of leads | - **Horizontal API Scaling**: Stateless FastAPI replicas behind an L7 Load Balancer (autoscaling on CPU/request latency).<br>- **Multi-Tenant Isolation**: Enforce PostgreSQL **Row-Level Security (RLS)** keyed on `dealership_id` as defense-in-depth alongside application-level filtering.<br>- **Read/Write Separation**: Route Lead Inbox & reporting queries to PostgreSQL Read Replicas; keep Activity writes on Primary.<br>- **Cursor/Keyset Pagination**: Replace `OFFSET` with keyset pagination (`(created_at, id)`) to maintain constant `O(log N)` query latency on deep pages. |
| **Stage 3: Enterprise Automotive Ecosystem** | 10,000+ rooftops, pan-European OEM integrations | - **Transactional Outbox + Event Bus**: Persist domain events (`LeadCreated`, `ActivityLogged`, `LeadStatusChanged`) in an `outbox_events` table within the same DB transaction; relay asynchronously to Kafka / AWS EventBridge for downstream CRM sync, automated SMS/email follow-ups, SLA breach alerts, and BI analytics.<br>- **Table Partitioning**: Range-partition `activities` by `occurred_at` (quarterly/yearly) or hash-partition by `dealership_id` to keep working index sets in RAM.<br>- **Distributed Caching**: Add Redis for dealership configuration, sales executive rosters, and near-real-time Inbox badge counts. |

---

## 8. GenAI Usage in the Design Phase

From an Engineering Management perspective, Generative AI was used intentionally as an **architecture sounding board and drafting accelerator**—never as an autonomous decision-maker. Every architectural trade-off, domain invariant, and production guardrail in this blueprint was explicitly reviewed, constrained, and validated against automotive retail workflows and Keyloop's multi-dealership operating context.

### 8.1 Architecture Brainstorming & Trade-Off Analysis
GenAI was leveraged early in the design phase to rapidly surface comparison matrices, edge cases, and failure modes across key architectural choices:
- **Layered Modular Monolith vs. Microservices**: Evaluated deployment simplicity and single-transaction ACID guarantees (`activities` insert + `leads` state update) against independent scaling and team autonomy, validating that strict internal module boundaries provide future extractability without upfront distributed-systems tax.
- **Offset vs. Cursor/Keyset Pagination**: Contrasted standard page-number navigation and `total_items` visibility for the MVP Lead Inbox against deep-page `OFFSET` scan degradation, establishing an explicit Stage 2 transition trigger to `(created_at, id)` keyset pagination.
- **SQLite / PostgreSQL Portability**: Stress-tested SQLAlchemy 2.0 dialect parity early—identifying native `UUID` vs. `CHAR` serialization, SQLite's default-off foreign key enforcement (`PRAGMA foreign_keys = ON;`), `NULLS FIRST` sorting semantics, and PostgreSQL-only upgrades (partial indexes, `pg_trgm`, Row-Level Security).

### 8.2 Engineering Leadership Decisions, Overrides & Guardrails
Several initial AI-generated recommendations were deliberately **modified or rejected** to keep the architecture pragmatic, auditable, and compliant:
- **Rejected Premature Service Decomposition & Infra Bloat**: Declined suggestions to split `leads` and `activities` into separate services or introduce Redis, Kafka, and async task queues in Stage 1. For an MVP serving dealership sales executives, a single stateless FastAPI service with strong relational consistency minimizes operational risk while preserving a clean evolution path (Section 7.4).
- **Enforced Dual Timestamps (`occurred_at` vs. `created_at`)**: Overrode single-timestamp activity proposals to separate *when an interaction occurred* (`occurred_at`) from *when the server recorded it* (`created_at`). Dealership sales executives frequently log phone calls or showroom visits retroactively; separating these fields preserves accurate customer timelines without sacrificing immutable audit trails.
- **Mandated Zero-PII Application Logging**: Rejected generic request/response body logging patterns in favor of strict PII exclusion—forbidding `email`, `phone`, `first_name`, `last_name`, and free-text `notes` from stdout logs and restricting log envelopes to opaque UUIDs (`lead_id`, `activity_id`), `correlation_id`, and non-PII metadata for GDPR compliance.
- **Right-Sized MVP Auth vs. Multi-Tenant Readiness**: Replaced boilerplate full-IdP integration in the MVP scope with zero-config local defaults (`performed_by` payload + optional `X-Dealer-ID` header), while embedding `dealership_id` across every table, query, and composite index so production OIDC/JWT and PostgreSQL RLS plug in without schema rewrites.

### 8.3 Cross-Artifact Consistency Verification
Before finalizing this document as an engineering blueprint, all AI-assisted drafts underwent manual end-to-end verification across four dimensions:
1. **Diagram ↔ Schema ↔ API Contract Parity**: Cross-checked every column, enum value, optimistic locking counter (`version`), and HTTP header (`X-Correlation-ID`, `X-Dealer-ID`, `Idempotency-Key`) across the Mermaid architecture/sequence/ER diagrams (Sections 1.2, 2.1, 3.2, 4.1), table constraints and indexes (Section 4.2–4.3), and JSON request/response examples (Section 5.3).
2. **MVP-to-Production Traceability**: Audited every MVP simplification (SQLite, offset pagination, synchronous writes, relaxed auth) to confirm it maps cleanly to a concrete, non-breaking production upgrade in Section 7.4 with no throwaway architecture.
3. **Behavioral & Edge-Case Review**: Verified state-transition invariants (e.g., `NOTE` not mutating `last_contacted_at`, terminal states `CONVERTED`/`LOST` allowing post-sale notes without status regression) and RFC 7807 error contracts (`404`, `409`, `422`, `503`).
4. **Formatting & Diagram QA**: Inspected rendered Mermaid diagrams, code/SQL configuration syntax (`PRAGMA foreign_keys = ON;`, `pool_recycle = 1800`), and Markdown structure to ensure the specification is clean, unambiguous, and immediately actionable for implementation.

