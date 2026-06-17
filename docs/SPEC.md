# Autonomous QA Platform — Product & Technical Specification

| Field | Value |
|-------|-------|
| **Version** | 2.3.0 |
| **Status** | Production Blueprint (Consolidated Agent Architecture) |
| **Last updated** | 2026-06-16 |
| **Source** | Executive Summary PDF + Implementation Plan v1 |
| **Workspace** | `AI Autonomous QA Platform` (monorepo root) |

---

## 1. Executive Summary

The Autonomous QA Platform is an AI-driven system that accepts a web application URL (plus minimal setup such as login credentials) and autonomously:

1. Explores and maps the application
2. Generates comprehensive functional test cases
3. Translates them into executable Playwright scripts
4. Runs tests in isolated environments
5. Produces rich reports and optional defect tickets

The platform unifies functional, API, security, performance, accessibility, and visual testing under one orchestrated pipeline — filling gaps left by existing tools (Mabl, Functionize, Katalon, etc.) that focus primarily on UI/API functional testing.

**Core pipeline (all phases):**

```
URL → Discovery → AppMap → Test Generation → Script Generation → Execution → Reporting
```

**MVP focus (Phase 1):** URL-driven discovery, AppMap storage, AI test/script generation, real Playwright execution, reporting, and CI integration.

**Future phases:** API, Security, Accessibility, Visual, Performance testing via plugin modes on the same 5 core agents (§31).

---

## 2. Goals

- Accept a **base URL + optional auth config** and run a full QA pipeline without manual script authoring
- Build an **AppMap** (pages, elements, flows) as the foundation for all test generation
- Generate **Playwright TypeScript** tests using semantic, self-healing-friendly locators
- Execute tests in **real browsers** (not simulated) with artifact capture (screenshots, traces, videos, logs)
- Provide a **dashboard** for AppMap visualization, pipeline progress, and run history
- Integrate with **CI/CD** (GitHub Actions) and optional **Jira** defect filing
- Support a **phased roadmap** extending to API, security, performance, a11y, visual testing, self-healing, and defect intelligence

---

## 3. MVP Scope

The MVP delivers end-to-end **UI functional testing** from a URL. Only the following capabilities are in scope:

| # | Capability | Description |
|---|------------|-------------|
| 1 | **Application Registration** | Register target apps with URL, auth config, crawl config |
| 2 | **URL Discovery** | Headless Playwright crawl from base URL and seed URLs |
| 3 | **AppMap Generation** | Persist pages, elements, and navigation graph |
| 4 | **Flow Discovery** | Infer user flows (login, navigation, form submit) |
| 5 | **Test Case Generation** | Rule-based + LLM scenarios from AppMap |
| 6 | **Playwright Script Generation** | Validated TypeScript test scripts |
| 7 | **Script Execution** | Real Playwright runs in Docker containers |
| 8 | **Reporting Dashboard** | Allure reports, run history, AppMap visualization, metrics |

**MVP also includes:** Celery job orchestration, SSE pipeline progress, GitHub Actions CI, optional Jira defect sync, Pino logging, Prometheus metrics.

---

## 4. Explicit Non-Goals (MVP)

The following are **not included in MVP**. They are documented for future phases and must not block MVP delivery.

| Non-Goal | Target Phase |
|----------|--------------|
| API Testing | Phase 2 |
| Security Testing (OWASP ZAP) | Phase 2 |
| Accessibility Testing (axe-core) | Phase 2 |
| Visual Testing (screenshot diff) | Phase 2 |
| Performance Testing (k6) | Phase 2 |
| Self-Healing Locators | Phase 3 |
| Defect Intelligence (AI root-cause) | Phase 3 |
| Multi-Tenancy | Phase 4 |
| SSO | Phase 4 |
| Kubernetes | Phase 4 |
| Vector Databases | Phase 4 |
| Neo4j / Graph DB | Phase 4 |

**Additional MVP exclusions:** Mobile native app testing, SAST/code analysis, production Kubernetes, full MFA/CAPTCHA automation (workarounds documented only).

---

## 5. Definition of Done

Each pipeline stage has explicit completion criteria. A stage is **Done** only when all criteria are met.

### 5.1 Discovery Done

- [ ] All discovered pages persisted to `pages` table
- [ ] All interactive elements persisted to `elements` table
- [ ] All inferred flows persisted to `flows` table
- [ ] Full-page screenshots captured and stored as `artifacts` (type: `screenshot` or `appmap`)
- [ ] AppMap export artifact stored (type: `appmap`)
- [ ] `pipeline_runs.current_stage` advanced; no unhandled crawl errors

### 5.2 Test Generation Done

- [ ] LLM/rule output validated against JSON Schema
- [ ] Invalid outputs discarded (not persisted)
- [ ] Valid test cases persisted to `test_cases` table
- [ ] Deduplication applied; priorities assigned

### 5.3 Script Generation Done

- [ ] Generated TypeScript passes `tsc --noEmit` compilation
- [ ] Playwright syntax validation passes (AST/lint rules)
- [ ] Locator policy compliance verified (see §12)
- [ ] Valid scripts persisted to `test_scripts` table with incremented `version`
- [ ] Script artifacts stored (type: `generated_script`)

### 5.4 Execution Done

- [ ] All selected scripts executed in isolated browser context
- [ ] Console logs captured and stored as artifacts
- [ ] Screenshots captured (on failure; optionally on pass)
- [ ] Playwright traces captured for every test
- [ ] Videos captured for every test
- [ ] Results persisted to `test_runs` and `results` tables
- [ ] Retry policy applied (timeout + network; see §18)

### 5.5 Reporting Done

- [ ] Allure report generated and stored (artifact type: `report`)
- [ ] Dashboard run history and metrics updated
- [ ] `applications.last_run_at` and `overall_health_score` recalculated
- [ ] `pipeline_runs.status` set to `completed` (or `failed` with `error_message`)

---

## 6. User Personas

| Persona | Need |
|---------|------|
| **QA Engineer** | Register apps, trigger discovery, review generated tests, approve runs, triage failures |
| **DevOps / Release Engineer** | Wire CI pipelines, schedule nightly runs, monitor flakiness |
| **Engineering Manager** | View coverage metrics, defect trends, automation ROI, health scores |

---

## 7. User Stories (MVP)

| ID | Story | Acceptance Criteria |
|----|-------|---------------------|
| US-01 | As a QA engineer, I register a web app by URL so the platform can test it | App saved with `name`, `base_url`, optional `auth_config`, `seed_urls` |
| US-02 | As a QA engineer, I start discovery so the system maps pages and elements | Discovery Done criteria met; AppMap visible in dashboard |
| US-03 | As a QA engineer, I generate tests from the AppMap without writing code | Test Generation + Script Generation Done criteria met |
| US-04 | As a QA engineer, I execute the generated suite and see pass/fail results | Execution Done criteria met; failures include artifacts |
| US-05 | As a QA engineer, I view an Allure report for a run | Reporting Done criteria met |
| US-06 | As a DevOps engineer, I trigger the pipeline from GitHub Actions | Workflow runs discover → generate → execute |
| US-07 | As a QA engineer, I optionally file failed tests as Jira defects | Jira issue created with artifact links (no credentials exposed) |

---

## 8. System Architecture

### 8.1 High-Level Components

```mermaid
flowchart TB
  subgraph client [Client Layer]
    Dashboard[Next.js Dashboard]
    CI[GitHub Actions]
  end

  subgraph orchestration [Orchestration Layer]
    API[FastAPI]
    Queue[Celery + Redis]
    PipelineRuns[PipelineRuns Master Table]
  end

  subgraph workers [Worker Layer — No LLM]
    DiscoveryWorker[DiscoveryWorker]
    PlaywrightExec[PlaywrightExecutor]
    ReportWorker[ReportingWorker]
  end

  subgraph coreAgents [5 Core AI Agents]
    DiscoveryAgent[DiscoveryAgent]
    TestDesignAgent[TestDesignAgent]
    ScriptGenAgent[ScriptGenerationAgent]
    IntelligenceAgent[IntelligenceAgent]
    HealingAgent[HealingAgent]
  end

  subgraph plugins [Testing Plugins]
    UIPlugin[UI Plugin]
    APIPlugin[API Plugin]
    SecPlugin[Security Plugin]
    A11yPlugin[Accessibility Plugin]
    VisPlugin[Visual Plugin]
    PerfPlugin[Performance Plugin]
  end

  subgraph modules [Deterministic Modules]
    ValidationGate[ValidationModule]
    Reporter[Reporting Pipeline]
  end

  subgraph data [Data Layer]
    PG[(PostgreSQL)]
    ArtifactStore[Artifact Storage]
  end

  subgraph observability [Observability]
    Pino[Pino Logging]
    Prom[Prometheus Metrics]
  end

  Dashboard --> API
  CI --> API
  API --> PipelineRuns
  API --> Queue
  Queue --> DiscoveryWorker
  Queue --> PlaywrightExec
  Queue --> ReportWorker
  DiscoveryWorker --> DiscoveryAgent
  DiscoveryAgent --> UIPlugin
  TestDesignAgent --> UIPlugin
  ScriptGenAgent --> UIPlugin
  HealingAgent --> ScriptGenAgent
  IntelligenceAgent --> Reporter
  PlaywrightExec --> UIPlugin
  ReportWorker --> Reporter
  ValidationGate --> TestDesignAgent
  ValidationGate --> ScriptGenAgent
  DiscoveryAgent --> PG
  TestDesignAgent --> PG
  ScriptGenAgent --> PG
  PlaywrightExec --> PG
  PlaywrightExec --> ArtifactStore
  Reporter --> PG
  API --> Pino
  API --> Prom
  plugins --> coreAgents
```

### 8.2 Plan-Act-Verify Loop

The orchestration layer follows an agentic **Plan → Act → Verify** pattern, implemented by **5 core AI agents** (not per-plugin agents):

1. **Plan (Discover + Design):** `DiscoveryAgent` → AppMap; `TestDesignAgent` → test scenarios
2. **Act (Generate + Execute):** `ScriptGenerationAgent` → scripts; **Workers** run tests
3. **Verify (Analyze + Heal):** `IntelligenceAgent` → analysis/defects; `HealingAgent` → repair; `ReportingWorker` → reports

**Architecture principle:** One domain capability = one agent. Plugins select agent **modes** and worker targets — they do not introduce new LLM agents.

### 8.3 Module Responsibilities

| Capability | Core Agent / Worker | MVP | Phase |
|------------|---------------------|-----|-------|
| **Discovery / AppMap** | `DiscoveryAgent` + `DiscoveryWorker` | Yes | 1 |
| **Test design (all types)** | `TestDesignAgent` (plugin mode) | UI only | 1→2 |
| **Script generation (all types)** | `ScriptGenerationAgent` (plugin mode) | Playwright | 1→2 |
| **Execution** | Plugin-specific **Workers** (no LLM) | PlaywrightExecutor | 1→2 |
| **Reporting** | `ReportingWorker` + dashboard | Yes | 1 |
| **Validation gates** | `ValidationModule` (deterministic code) | Yes | 1 |
| **Intelligence / defects / data** | `IntelligenceAgent` | Stub | 3 |
| **Self-healing / repair** | `HealingAgent` | Codegen repair | 1→3 |

**Phase 2 plugin coverage** (same 5 agents, new modes + workers):

| Plugin | Agent modes used | Worker |
|--------|------------------|--------|
| UI | `discover:ui`, `design:functional`, `script:playwright` | PlaywrightExecutor |
| API | `discover:api`, `design:api`, `script:api` | APIExecutor |
| Security | `discover:api`, `design:security` | ZAPRunner |
| Accessibility | `design:a11y`, `script:a11y` | AccessibilityRunner |
| Visual | `design:visual`, `script:visual` | VisualRunner (via PlaywrightExecutor) |
| Performance | `design:performance`, `script:k6` | K6Runner |

### 8.4 Plugin Architecture

Testing plugins are **configuration + worker bindings** over the 5 core agents. Plugins **must not** define plugin-specific LLM agents.

```typescript
interface TestingPlugin {
  readonly id: string;           // "ui" | "api" | "security" | "a11y" | "visual" | "performance"
  readonly phase: number;

  // Maps to agent modes — NOT separate agent classes
  discoverMode: DiscoverMode;
  designMode: DesignMode;
  scriptMode: ScriptMode;
  executorWorkerId: string;

  discover(ctx: DiscoverContext): Promise<DiscoverResult>;   // delegates to DiscoveryAgent
  generate(ctx: GenerateContext): Promise<GenerateResult>;   // delegates to TestDesignAgent + ScriptGenerationAgent
  execute(ctx: ExecuteContext): Promise<ExecuteResult>;     // delegates to Worker only
  report(ctx: ReportContext): Promise<ReportResult>;         // delegates to ReportingWorker + IntelligenceAgent
}
```

| Plugin | Phase | Worker | Agent modes |
|--------|-------|--------|-------------|
| **UI Plugin** | 1 | PlaywrightExecutor | `discover:ui`, `design:functional`, `script:playwright` |
| **API Plugin** | 2 | APIExecutor | `discover:api`, `design:api`, `script:api` |
| **Security Plugin** | 2 | ZAPRunner | `design:security` (+ API endpoints from DiscoveryAgent) |
| **Accessibility Plugin** | 2 | AccessibilityRunner | `design:a11y`, `script:a11y` |
| **Visual Plugin** | 2 | PlaywrightExecutor | `design:visual`, `script:visual` |
| **Performance Plugin** | 2 | K6Runner | `design:performance`, `script:k6` |

**Example — API Plugin pipeline (Phase 2):**

```
DiscoveryAgent (mode: api)
  → TestDesignAgent (mode: api)
  → ScriptGenerationAgent (mode: api)
  → APIExecutor
  → IntelligenceAgent (mode: analyze)
  → ReportingWorker
```

**Registration:** Plugins register with the orchestrator at startup. `POST /api/apps/:id/pipeline` accepts `plugins: ["ui"]` (MVP default). Each plugin writes to shared `pipeline_runs`, `test_runs`, `results`, and `artifacts` tables.

**Orchestration contract:** Plugins run sequentially unless `continue_on_error: true` (Phase 2+). Failures set `pipeline_runs.status = failed` with `error_message`.

---

## 9. Architecture Decision Records (ADR)

### ADR-001: Python + FastAPI for API / Orchestration

| | |
|---|---|
| **Decision** | Use Python 3.11+ with **FastAPI** for the orchestration API |
| **Reason** | Unified Python stack with Celery workers, SQLAlchemy/Alembic, and Playwright; single language for API, agents, and job execution |
| **Alternatives Considered** | Node.js + Express (original scaffold), NestJS |
| **Future Migration** | Optional API gateway or NestJS front-end proxy in Phase 4; FastAPI remains core orchestrator |

### ADR-002: PostgreSQL as Primary Database

| | |
|---|---|
| **Decision** | PostgreSQL 15+ for all structured data; JSONB for AppMap adjacency and config |
| **Reason** | ACID guarantees, mature tooling, JSONB avoids separate graph DB for MVP |
| **Alternatives Considered** | Neo4j (graph queries), MongoDB (flexible docs) |
| **Future Migration** | Optional Neo4j sync for AppMap graph analytics in Phase 4; PostgreSQL remains source of truth |

### ADR-003: Playwright for Crawler and Test Runner

| | |
|---|---|
| **Decision** | Playwright for discovery, script target framework, and execution |
| **Reason** | Multi-browser, headless-first, official Test Agents (planner/generator/healer), API testing mode for Phase 2 |
| **Alternatives Considered** | Selenium (heavier), Cypress (Chrome-only) |
| **Future Migration** | Script generator may emit Cypress/Selenium via alternate plugins; Playwright remains default |

### ADR-004: Celery + Redis for Job Queue

| | |
|---|---|
| **Decision** | Celery (Python) backed by Redis 7+ for async crawl, generate, execute jobs |
| **Reason** | Reliable retries, concurrency control, SSE-friendly progress events; mature Python worker ecosystem for Playwright-adjacent tasks |
| **Alternatives Considered** | BullMQ (Node-native; original blueprint ADR), RabbitMQ, AWS SQS |
| **Implementation** | FastAPI (Python) enqueues tasks via Celery `apply_async`; Python workers in `workers/celery_app/` consume queues; task names in `packages/aqa_shared` |
| **Future Migration** | SQS adapter for serverless workers in Phase 4; Redis retained for local/dev |

> **Note:** Executive Summary v1 referenced BullMQ. Implementation migrated to Celery during Week 1–2 scaffold (see `docs/WEEK-01-02-SCAFFOLD-GUIDE.md`).

### ADR-005: OpenAI GPT-4o as Primary LLM

| | |
|---|---|
| **Decision** | OpenAI GPT-4o for test case and script generation; Gemini as optional fallback |
| **Reason** | State-of-art code generation; strong structured JSON output with schema validation |
| **Alternatives Considered** | LLaMA 3 (self-hosted), Claude 3 |
| **Future Migration** | Provider abstraction layer (ported from prototype `llm.js`); local models in Phase 3 for cost control |

### ADR-006: LangGraph for AI Agent Orchestration

| | |
|---|---|
| **Decision** | LangGraph (Python) for Plan → Generate → Validate agent pipelines |
| **Reason** | Explicit state machine; retry nodes; validation gates before persistence; same runtime as API and workers |
| **Alternatives Considered** | LangGraph.js, raw prompt chains, LangChain agents without graph |
| **Future Migration** | Graph nodes map 1:1 to plugin `generate()` steps; extend graphs per plugin |

---

## 10. Technology Stack

| Layer | Technology | Notes |
|-------|------------|-------|
| Frontend | Next.js 14+, TypeScript, React | Dashboard, AppMap graph, reports, metrics |
| API | Python 3.11+, FastAPI, Uvicorn | Orchestration, REST, SSE, `/metrics` |
| Crawler / Runner | Playwright | Discovery + test execution |
| AI Orchestration | LangGraph (Python) | Plan → Generate → Validate agents |
| LLM | OpenAI GPT-4o (primary), Gemini (fallback) | Test/script generation |
| Database | PostgreSQL 15+ (17 supported for local dev) | Structured data, JSONB for AppMap adjacency |
| ORM / Migrations | SQLAlchemy 2.0 + Alembic | Schema models in `packages/aqa_shared`; migrations in `alembic/` |
| Queue | Celery + Redis 7+ | Async jobs |
| Execution | Docker (Playwright official image) | Isolated browser runs |
| Reporting | Allure + custom React views | HTML reports |
| Logging | Python `logging` (stdlib) | Structured logs; secret masking |
| Metrics | Prometheus (`prometheus-client`) | Platform and pipeline metrics |
| CI | GitHub Actions | Scheduled / manual pipeline |
| Secrets | Environment variables + encrypted `auth_config` | Phase 4: HashiCorp Vault |

---

## 11. Repository Structure

```
d:\AI Autonomous QA Platform\
├── docs/
│   └── SPEC.md
├── apps/
│   ├── web/                       # Next.js dashboard
│   └── api/                       # FastAPI orchestration API (Python)
├── packages/
│   ├── aqa_shared/                # Python: enums, Celery constants, SQLAlchemy models
│   ├── agents/                    # 5 core AI agents (LangGraph Python)
│   ├── plugins/
│   │   ├── ui/                    # MVP UI Plugin
│   │   ├── api/                   # Phase 2
│   │   ├── security/
│   │   ├── accessibility/
│   │   ├── visual/
│   │   └── performance/
│   └── integrations/              # Jira, GitHub
├── workers/                       # Celery task workers (Python, no LLM in worker body)
│   └── celery_app/                # Week 1–2: unified Celery app with stub tasks
│       └── aqa_celery/            # Week 3+ tasks call agents / Playwright executors
│           ├── tasks/             # discover, design, generate_scripts, execute, report, analyze
│           └── ...
│   # Target (Phase 1+): dedicated deterministic executors — no LLM in worker body
│   # discovery-worker/, playwright-executor/, api-executor/, zap-runner/,
│   # accessibility-runner/, k6-runner/, reporting-worker/
├── artifacts/                     # Runtime artifact storage (gitignored)
│   ├── screenshots/
│   ├── traces/
│   ├── videos/
│   ├── reports/
│   ├── appmaps/
│   └── generated-scripts/
├── docker/
│   ├── docker-compose.yml
│   └── playwright-runner/
├── .github/workflows/
├── alembic/                       # Alembic migrations + SQL baselines
│   ├── versions/
│   └── sql/
├── requirements.txt               # Python editable installs (api, workers, aqa_shared)
├── .venv/                         # Python virtualenv (local dev)
├── .env.example
└── README.md
```

Monorepo: **Python** backend (`requirements.txt`, root `.venv`); **pnpm** optional for Next.js frontend when added.

---

## 12. Locator Strategy Standards

All generated Playwright scripts **must** follow this mandatory locator priority order. The script generator validates compliance before persistence.

| Priority | Locator Method | Usage |
|----------|----------------|-------|
| 1 | `page.getByRole(role, { name })` | Buttons, links, headings, checkboxes |
| 2 | `page.getByLabel(text)` | Form inputs with associated labels |
| 3 | `page.getByPlaceholder(text)` | Inputs identified by placeholder |
| 4 | `page.getByText(text)` | Visible static text targets |
| 5 | `page.getByTestId(id)` | Elements with `data-testid` attributes |
| 6 | `page.locator('css=...')` | CSS selector when semantic locators unavailable |
| 7 | `page.locator('xpath=...')` | **Last resort only** — requires justification comment in generated code |

**Policy rules:**

- Never use bare XPath as the primary locator
- Store both `semantic_selector` and `xpath_fallback` in `elements` table; generator prefers semantic
- On validation failure for locator policy, retry via HealingAgent (§31)
- Self-healing (Phase 3) re-evaluates locators using the same priority order

---

## 13. AI Validation Requirements

**No invalid AI output may be persisted.** Every LLM-generated artifact passes through validation gates before database write.

### 13.1 Test Cases

| Check | Method |
|-------|--------|
| Structure | JSON Schema validation (`TestCaseSchema`) |
| Required fields | `name`, `steps[]`, `priority` |
| Step integrity | Each step has `action`, `target` (page or element ref) |

### 13.2 Scripts

| Check | Method |
|-------|--------|
| TypeScript | `tsc --noEmit` on generated file |
| Playwright syntax | AST lint: valid `test()`, `expect()`, locator methods |
| Locator policy | Static analysis for priority order (§12) |

### 13.3 Execution Plans

| Check | Method |
|-------|--------|
| Structure | JSON Schema validation (`ExecutionPlanSchema`) |
| Script references | All `script_id` values exist and are validated |
| Concurrency | `parallelism` within platform limits |

### 13.4 Retry on Validation Failure

```
Attempt 1 → validate → fail → retry with error context
Attempt 2 → validate → fail → retry with error context
Attempt 3 → validate → fail → reject; log to pipeline_runs.error_message
```

Maximum **2 retries** (3 total attempts). Failed generations are logged but **never persisted**.

> **See also:** §31 Agent Design, §32 OpenAI Cost Controls, §33 Versioning Strategy, §34 Database Index Strategy.

---

## 14. Data Model

### 14.1 Entity Relationship Overview

```
Applications ──┬── Pages ─── Elements
               ├── Flows
               ├── TestCases ─── TestScripts ─── TestRuns ─── Results
               ├── PipelineRuns ─── Artifacts
               └── (Phase 2: API_Endpoints, etc.)

TestRuns ─── Artifacts
TestRuns ─── Defects
Users (Phase 4)
```

### 14.2 Table Definitions (Phase 1)

#### `applications`

| Column | Type | Description |
|--------|------|-------------|
| `app_id` | UUID PK | Unique app identifier |
| `name` | VARCHAR(255) | Display name |
| `base_url` | TEXT | Starting URL for crawl |
| `seed_urls` | JSONB | Additional entry URLs: `["https://app.com/dashboard", ...]` |
| `auth_config` | JSONB (encrypted at rest) | Login selectors, credentials ref, cookies — **never returned in API responses** |
| `crawl_config` | JSONB | `max_depth`, `max_pages`, `allowed_domains`, exclusions — see §15 |
| `last_crawl_at` | TIMESTAMPTZ | Timestamp of last successful discovery |
| `last_run_at` | TIMESTAMPTZ | Timestamp of last test execution |
| `overall_health_score` | DECIMAL(5,4) | Computed score 0.0–1.0 — see §21 |
| `config_version` | INT | Incremented on config change — see §33 |
| `created_at` | TIMESTAMPTZ | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | Last update |

#### `pages`

| Column | Type | Description |
|--------|------|-------------|
| `page_id` | UUID PK | Unique page identifier |
| `app_id` | UUID FK | Parent application |
| `url` | TEXT | Normalized page URL |
| `title` | VARCHAR(512) | Document title |
| `screenshot_path` | TEXT | Reference to artifact path |
| `discovered_at` | TIMESTAMPTZ | Crawl timestamp |

#### `elements`

| Column | Type | Description |
|--------|------|-------------|
| `element_id` | UUID PK | Unique element identifier |
| `page_id` | UUID FK | Parent page |
| `tag_name` | VARCHAR(64) | HTML tag |
| `role` | VARCHAR(64) | ARIA role |
| `text_content` | TEXT | Visible text |
| `semantic_selector` | TEXT | Preferred Playwright locator (priority 1–5) |
| `xpath_fallback` | TEXT | Fallback XPath (priority 7) |
| `attributes` | JSONB | id, name, type, placeholder, data-testid |

#### `flows`

| Column | Type | Description |
|--------|------|-------------|
| `flow_id` | UUID PK | Unique flow identifier |
| `app_id` | UUID FK | Parent application |
| `name` | VARCHAR(255) | e.g. "Login", "Checkout" |
| `description` | TEXT | Human-readable summary |
| `sequence` | JSONB | Ordered steps: `{ action, target, value }[]` |
| `source` | ENUM | `crawler`, `llm`, `manual` |

#### `test_cases`

| Column | Type | Description |
|--------|------|-------------|
| `testcase_id` | UUID PK | Unique test case identifier |
| `app_id` | UUID FK | Parent application |
| `flow_id` | UUID FK (nullable) | Linked flow |
| `name` | VARCHAR(255) | Test name |
| `description` | TEXT | Scenario description |
| `steps` | JSONB | Abstract steps before codegen |
| `priority` | ENUM | `critical`, `high`, `medium`, `low` |
| `status` | ENUM | `draft`, `approved`, `archived` |
| `pipeline_run_id` | UUID FK (nullable) | Generation batch linkage — see §33 |

#### `test_scripts`

| Column | Type | Description |
|--------|------|-------------|
| `script_id` | UUID PK | Unique script identifier |
| `testcase_id` | UUID FK | Parent test case |
| `language` | VARCHAR(32) | `typescript` |
| `framework` | VARCHAR(32) | `playwright` |
| `code` | TEXT | Generated source code |
| `version` | INT | Increment on regeneration |
| `validated_at` | TIMESTAMPTZ | Last successful validation timestamp |

#### `test_runs`

| Column | Type | Description |
|--------|------|-------------|
| `run_id` | UUID PK | Unique run identifier |
| `app_id` | UUID FK | Application under test |
| `pipeline_run_id` | UUID FK (nullable) | Parent pipeline job |
| `status` | ENUM | `pending`, `running`, `passed`, `failed`, `error`, `flaky` |
| `started_at` | TIMESTAMPTZ | Run start |
| `ended_at` | TIMESTAMPTZ | Run end |
| `summary` | JSONB | Pass/fail counts, duration, retry count |
| `is_flaky` | BOOLEAN | True if passed after retry or intermittent history |

#### `results`

| Column | Type | Description |
|--------|------|-------------|
| `result_id` | UUID PK | Unique result identifier |
| `run_id` | UUID FK | Parent test run |
| `script_id` | UUID FK | Executed script |
| `assertion` | TEXT | Assertion description |
| `outcome` | ENUM | `passed`, `failed`, `skipped` |
| `error_msg` | TEXT | Failure message (credentials masked) |
| `artifact_ids` | JSONB | Array of related artifact UUIDs |

#### `pipeline_runs` (Master Orchestration Table)

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | Unique pipeline run identifier |
| `application_id` | UUID FK | Target application |
| `status` | ENUM | `pending`, `running`, `completed`, `failed`, `cancelled` |
| `current_stage` | ENUM | `discover`, `generate_tests`, `generate_scripts`, `execute`, `report`, `complete` |
| `config` | JSONB | Stage-specific options |
| `started_at` | TIMESTAMPTZ | Pipeline start |
| `ended_at` | TIMESTAMPTZ | Pipeline end |
| `llm_tokens_used` | INT | Total tokens consumed across stages |
| `cost_estimate` | DECIMAL(10,4) | Estimated LLM cost in USD |
| `error_message` | TEXT | Failure reason (credentials masked) |

All orchestration jobs **must** create a `pipeline_runs` record before enqueueing work. SSE events reference `pipeline_runs.id`.

#### `artifacts`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | Unique artifact identifier |
| `run_id` | UUID FK (nullable) | Related test run |
| `pipeline_run_id` | UUID FK (nullable) | Related pipeline run |
| `type` | ENUM | See artifact types below |
| `path` | TEXT | Relative path under `artifacts/` root |
| `size_bytes` | BIGINT | File size |
| `created_at` | TIMESTAMPTZ | Creation timestamp |

**Artifact types:**

| Type | Storage Path | Produced By |
|------|--------------|-------------|
| `screenshot` | `artifacts/screenshots/` | Crawler, Executor |
| `trace` | `artifacts/traces/` | Executor |
| `video` | `artifacts/videos/` | Executor |
| `report` | `artifacts/reports/` | Reporter (Allure) |
| `appmap` | `artifacts/appmaps/` | Crawler |
| `generated_script` | `artifacts/generated-scripts/` | Script Generator |

**Secure artifact access:** Artifacts served via authenticated API proxy (`GET /api/artifacts/:id`) — never direct filesystem URLs. MVP uses signed short-lived tokens for dashboard preview.

#### `defects` (optional MVP)

| Column | Type | Description |
|--------|------|-------------|
| `defect_id` | UUID PK | Unique defect identifier |
| `run_id` | UUID FK | Source test run |
| `result_id` | UUID FK (nullable) | Source result |
| `title` | VARCHAR(512) | Issue title |
| `description` | TEXT | Issue body |
| `status` | ENUM | `open`, `synced`, `closed` |
| `issue_key` | VARCHAR(64) | Jira/GitHub issue key |

#### `credential_access_audit` (MVP)

| Column | Type | Description |
|--------|------|-------------|
| `audit_id` | UUID PK | Unique audit entry |
| `app_id` | UUID FK | Application whose credentials were accessed |
| `pipeline_run_id` | UUID FK (nullable) | Triggering pipeline |
| `accessor` | VARCHAR(128) | Worker/service name |
| `action` | ENUM | `read`, `decrypt`, `inject` |
| `timestamp` | TIMESTAMPTZ | Access time |

### 14.3 Phase 2 Schema Extensions

Full table definitions, enums, indexes, and relationships: [PHASE-2-SPEC.md §8](./PHASE-2-SPEC.md#8-data-model).

Tables: `api_endpoints`, `api_tests`, `security_scans`, `performance_runs`, `a11y_results`, `visual_baselines`

### 14.4 Versioning Columns (Summary)

Full versioning policy is defined in §33. Key columns:

| Table | Version Field | Purpose |
|-------|---------------|---------|
| `test_scripts` | `version` (INT) | Incremented on each validated regeneration |
| `test_cases` | `status` + implicit generation batch via `pipeline_run_id` | Track draft vs approved |
| `applications` | `config_version` (INT) + `updated_at` | Config change tracking; increment on URL/crawl/auth changes (§33.2) |
| `artifacts` (appmap) | `created_at` + pipeline linkage | Point-in-time AppMap snapshots |

---

## 15. Discovery Constraints (Crawl Rules)

All discovery operations enforce the following constraints. Defaults apply when `crawl_config` omits a field.

### 15.1 Scope Limits

| Rule | Default | Config Key |
|------|---------|------------|
| Max crawl depth | `5` | `crawl_config.max_depth` |
| Max pages | `100` | `crawl_config.max_pages` |
| Allowed domains | Hostname of `base_url` | `crawl_config.allowed_domains[]` |
| Excluded URL patterns | `[]` | `crawl_config.excluded_urls[]` (glob/regex) |
| Timeout per page | `30s` | `crawl_config.page_timeout_ms` |

### 15.2 Safety Exclusions (Always Enforced)

The crawler **must not** interact with URLs or elements matching:

| Exclusion | Pattern / Heuristic |
|-----------|---------------------|
| Logout | URL contains `/logout`, `sign-out`, `signout`; buttons with text "Log out", "Sign out" |
| Delete account | URL/buttons matching `delete account`, `close account`, `deactivate` |
| Destructive forms | Forms with `method=DELETE` or action containing `/delete` unless explicitly allowlisted |

### 15.3 SPA Handling

- Listen for `popstate`, `pushState` intercepts, and DOM mutations indicating route changes
- Wait for `networkidle` or configurable `wait_for_selector` before extracting elements
- Track visited routes by normalized URL (including hash routes for hash-based SPAs)
- Deduplicate pages by canonical URL

### 15.4 Infinite Scroll Handling

- Max scroll iterations: `10` per page (configurable via `crawl_config.max_scroll_iterations`)
- Stop when no new elements appear after 2 consecutive scrolls
- Do not follow dynamically loaded external links outside `allowed_domains`

### 15.5 Seed URLs

- `applications.seed_urls` (JSONB array) provides additional crawl entry points beyond `base_url`
- Seed URLs merged into BFS queue at depth 0
- Each seed URL must match `allowed_domains`

### 15.6 Robots.txt

| Setting | Behavior |
|---------|----------|
| `respect_robots_txt: true` (default) | Skip disallowed paths; log skipped URLs |
| `respect_robots_txt: false` | Crawl all in-scope URLs (use only for owned test environments) |

### 15.7 Authentication Strategy

| Auth Type | MVP Support | Implementation |
|-----------|-------------|----------------|
| **Form login** | Yes | Fill selectors from `auth_config`; credentials from env secret ref |
| **Session cookie** | Yes | Inject cookies from `auth_config.cookies[]` before crawl |
| **Bearer token** | Phase 2 | Header injection |
| **OAuth flow** | No | Manual cookie injection workaround |

### 15.8 CAPTCHA Handling

- **Not automated in MVP**
- Detect CAPTCHA presence (reCAPTCHA/hCaptcha DOM markers) → halt crawl on affected page → set `pipeline_runs.error_message` with guidance
- Mitigation: provide pre-authenticated session cookies via `auth_config.cookies`

### 15.9 MFA Handling

- **Not automated in MVP**
- Detect MFA prompt → halt with actionable error
- Mitigation: test-environment credentials with MFA disabled; session cookie injection

---

## 16. API Specification

Base URL: `/api/v1`

**Conventions:**

- All async operations return `202 Accepted` with `pipeline_run_id`
- Credentials never appear in responses; `auth_config` returned as `{ "configured": true, "type": "form" }` only
- Error responses follow RFC 7807 Problem Details format

### 16.1 Standard Error Response

```json
{
  "type": "https://autonomous-qa.dev/errors/validation",
  "title": "Validation Error",
  "status": 400,
  "detail": "base_url must use HTTPS in production environments",
  "instance": "/api/v1/apps",
  "errors": [
    { "field": "base_url", "message": "must be a valid URL" }
  ]
}
```

---

### 16.2 `POST /api/v1/apps`

Register a new application.

**Request:**
```json
{
  "name": "Juice Shop",
  "base_url": "https://juice-shop.herokuapp.com",
  "seed_urls": [
    "https://juice-shop.herokuapp.com/#/login",
    "https://juice-shop.herokuapp.com/#/search"
  ],
  "auth_config": {
    "type": "form",
    "login_url": "/#/login",
    "email_selector": "input[name=email]",
    "password_selector": "input[name=password]",
    "submit_selector": "button[type=submit]",
    "credentials_secret_ref": "JUICE_SHOP_TEST_USER"
  },
  "crawl_config": {
    "max_depth": 5,
    "max_pages": 100,
    "allowed_domains": ["juice-shop.herokuapp.com"],
    "excluded_urls": ["**/logout**"],
    "respect_robots_txt": true
  }
}
```

**Response `201 Created`:**
```json
{
  "app_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "name": "Juice Shop",
  "base_url": "https://juice-shop.herokuapp.com",
  "seed_urls": ["https://juice-shop.herokuapp.com/#/login"],
  "auth_config": { "configured": true, "type": "form" },
  "crawl_config": { "max_depth": 5, "max_pages": 100 },
  "last_crawl_at": null,
  "last_run_at": null,
  "overall_health_score": null,
  "created_at": "2026-06-12T10:00:00Z"
}
```

**Error `400 Bad Request`:**
```json
{
  "type": "https://autonomous-qa.dev/errors/validation",
  "title": "Validation Error",
  "status": 400,
  "detail": "base_url resolves to a private IP address",
  "instance": "/api/v1/apps"
}
```

---

### 16.3 `POST /api/v1/apps/:appId/discover`

Start discovery (crawl) job.

**Request (optional body):**
```json
{
  "force": false,
  "crawl_config_overrides": { "max_pages": 50 }
}
```

**Response `202 Accepted`:**
```json
{
  "pipeline_run_id": "p1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "application_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "pending",
  "current_stage": "discover",
  "started_at": "2026-06-12T10:05:00Z"
}
```

**Error `409 Conflict`:**
```json
{
  "type": "https://autonomous-qa.dev/errors/conflict",
  "title": "Pipeline Already Running",
  "status": 409,
  "detail": "Application already has an active pipeline run",
  "instance": "/api/v1/apps/a1b2c3d4-e5f6-7890-abcd-ef1234567890/discover",
  "active_pipeline_run_id": "p0a1b2c3-..."
}
```

---

### 16.4 `POST /api/v1/apps/:appId/generate-tests`

Generate test cases and Playwright scripts from AppMap.

**Request:**
```json
{
  "priorities": ["critical", "high"],
  "max_tests": 50,
  "use_llm": true,
  "generate_scripts": true
}
```

**Response `202 Accepted`:**
```json
{
  "pipeline_run_id": "p2b3c4d5-e6f7-8901-bcde-f12345678901",
  "application_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "pending",
  "current_stage": "generate_tests",
  "started_at": "2026-06-12T10:15:00Z"
}
```

**Error `422 Unprocessable Entity`:**
```json
{
  "type": "https://autonomous-qa.dev/errors/precondition",
  "title": "AppMap Required",
  "status": 422,
  "detail": "No discovery data found. Run POST /apps/:id/discover first.",
  "instance": "/api/v1/apps/a1b2c3d4-e5f6-7890-abcd-ef1234567890/generate-tests"
}
```

---

### 16.5 `POST /api/v1/apps/:appId/execute`

Execute generated test suite.

**Request:**
```json
{
  "parallelism": 3,
  "script_ids": null,
  "capture_video": true,
  "capture_trace": true
}
```

**Response `202 Accepted`:**
```json
{
  "pipeline_run_id": "p3c4d5e6-f7a8-9012-cdef-123456789012",
  "application_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "pending",
  "current_stage": "execute",
  "started_at": "2026-06-12T10:30:00Z"
}
```

**Error `422 Unprocessable Entity`:**
```json
{
  "type": "https://autonomous-qa.dev/errors/precondition",
  "title": "No Scripts Available",
  "status": 422,
  "detail": "No validated test scripts found for this application.",
  "instance": "/api/v1/apps/a1b2c3d4-e5f6-7890-abcd-ef1234567890/execute"
}
```

---

### 16.6 `GET /api/v1/runs/:runId/report`

Retrieve Allure report for a test run.

**Response `200 OK`:**
```json
{
  "run_id": "r1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "failed",
  "report_url": "/api/v1/artifacts/art-report-uuid/view",
  "summary": {
    "total": 24,
    "passed": 20,
    "failed": 3,
    "skipped": 1,
    "duration_ms": 145000
  },
  "generated_at": "2026-06-12T10:45:00Z"
}
```

**Error `404 Not Found`:**
```json
{
  "type": "https://autonomous-qa.dev/errors/not-found",
  "title": "Run Not Found",
  "status": 404,
  "detail": "No test run exists with the given ID",
  "instance": "/api/v1/runs/00000000-0000-0000-0000-000000000000/report"
}
```

---

### 16.7 Additional Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/apps` | List applications |
| `GET` | `/apps/:appId` | App detail + health score |
| `GET` | `/apps/:appId/appmap` | AppMap graph JSON |
| `POST` | `/apps/:appId/pipeline` | Full discover → generate → execute |
| `GET` | `/pipeline-runs/:id` | Pipeline status |
| `GET` | `/pipeline-runs/:id/stream` | SSE live progress |
| `GET` | `/apps/:appId/runs` | List test runs |
| `GET` | `/runs/:runId` | Run detail + results |
| `GET` | `/artifacts/:id` | Secure artifact download |
| `POST` | `/runs/:runId/defects/sync-jira` | Create Jira issue |
| `GET` | `/health` | Health check |
| `GET` | `/metrics` | Prometheus metrics |

**SSE event types:** `stage_started`, `stage_progress`, `stage_completed`, `stage_failed`, `pipeline_completed`

---

## 17. Module Specifications

Modules map to **5 core agents + workers**. Package paths: `packages/agents/*`, `workers/*`.

### 17.1 DiscoveryAgent + DiscoveryWorker

**Agent input:** Application record, mode (`ui` | `api`), crawl config (§15)

**Worker process:** Headless Playwright crawl — login, link traversal, element extraction, screenshots

**Output:** AppMap in DB + artifacts; API endpoints for Phase 2 (`discover:api` mode)

### 17.2 TestDesignAgent

**Input:** AppMap, plugin mode, constraints

**Process:** Rule-based templates → LLM gap-fill → ValidationModule

**Output:** `test_cases`

### 17.3 ScriptGenerationAgent + HealingAgent

**Input:** Test cases, AppMap selectors, script mode

**Process:** LangGraph plan+generate → ValidationModule → HealingAgent (`codegen`) on failure

**Output:** `test_scripts` per §12 locator policy

### 17.4 PlaywrightExecutor (Worker)

**Input:** Validated scripts | **Process:** §18 artifact capture | **Output:** `test_runs`, `results`

**Container:** `mcr.microsoft.com/playwright:v1.x`

### 17.5 IntelligenceAgent + ReportingWorker

**MVP:** IntelligenceAgent (`coverage`, no LLM) + ReportingWorker (Allure)

**Phase 3:** IntelligenceAgent LLM modes; Jira sync via integrations

### 17.6 Phase 2 Workers

APIExecutor, ZAPRunner, AccessibilityRunner, K6Runner — deterministic; no LLM.

---

## 18. Execution Reliability

The execution engine **must** capture the following artifacts for every test run:

| Artifact | Required | Playwright Config |
|----------|----------|-------------------|
| Console logs | Yes | `page.on('console')` → log artifact |
| Screenshots | Yes (on failure); optional on pass | `screenshot: 'only-on-failure'` |
| Traces | Yes | `trace: 'on'` |
| Videos | Yes | `video: 'on'` |

### 18.1 Retry Policy

| Condition | Action |
|-----------|--------|
| Timeout (`TimeoutError`) | Retry once after 2s backoff |
| Network failure (`net::ERR_*`) | Retry once after 2s backoff |
| Assertion failure | No retry — record as failed |
| Locator not found | No auto-retry in MVP | `HealingAgent` repairs selector and re-runs (Phase 3) |

Maximum **1 retry per test** (2 total attempts). Retries logged in `test_runs.summary.retry_count`.

### 18.2 Flaky Test Tracking

A test is marked **flaky** (`test_runs.is_flaky = true`) when:

- It fails on first attempt and passes on retry, OR
- Historical analysis shows pass/fail alternation across last 5 runs without code changes (Phase 3 automation; MVP tracks retry-based flakiness only)

Flaky tests contribute to flakiness rate metrics (§20) but do not block pipeline completion.

---

## 19. Orchestration Workflow

### 19.1 MVP Pipeline (UI Plugin)

```mermaid
sequenceDiagram
  participant UI as Dashboard
  participant API as Orchestrator
  participant PR as PipelineRuns
  participant Q as Celery
  participant DA as DiscoveryAgent
  participant DW as DiscoveryWorker
  participant TDA as TestDesignAgent
  participant SGA as ScriptGenerationAgent
  participant HA as HealingAgent
  participant PE as PlaywrightExecutor
  participant RW as ReportingWorker
  participant DB as PostgreSQL

  UI->>API: POST /apps/:id/pipeline
  API->>PR: INSERT status=pending
  API->>Q: enqueue discover
  Q->>DA: discover mode ui
  DA->>DW: Playwright crawl instructions
  DW->>DB: save pages elements flows AppMap
  DA->>PR: UPDATE current_stage generate_tests
  API->>Q: enqueue generate
  Q->>TDA: design mode functional
  TDA->>DB: save test_cases
  Q->>SGA: script mode playwright
  SGA->>HA: on validation fail
  HA->>SGA: repaired script
  SGA->>DB: save test_scripts
  API->>Q: enqueue execute
  Q->>PE: run playwright tests
  PE->>DB: save test_runs results artifacts
  API->>Q: enqueue report
  Q->>RW: generate Allure
  RW->>DB: save report artifact
  RW->>PR: UPDATE status completed
  UI->>API: GET /runs/:id/report
```

### 19.2 Full Platform Pipeline (Multi-Plugin)

Each enabled plugin runs the same agent chain with different **modes** and **workers**. `IntelligenceAgent` runs once after all plugin executions complete.

```
FOR EACH plugin IN pipeline.plugins:
  DiscoveryAgent(mode) → TestDesignAgent(mode) → ScriptGenerationAgent(mode) → Worker(plugin)

IntelligenceAgent(analyze) → ReportingWorker → Dashboard
```

**Celery queues:** `discover`, `design`, `generate-scripts`, `execute`, `analyze`, `report`

---

## 20. Dashboard Metrics

The dashboard displays the following metrics per application and globally. Values refresh after each pipeline completion.

| Metric | Definition | MVP Target |
|--------|------------|------------|
| **Flow Coverage** | Flows with ≥1 test case / total discovered flows | ≥ 80% |
| **Test Coverage** | Pages with ≥1 test / total discovered pages | ≥ 70% |
| **Flakiness Rate** | Flaky runs / total runs (rolling 30 days) | < 5% |
| **Crawl Time** | `discover` stage duration (seconds) | Establish baseline |
| **Generation Time** | `generate_tests` + `generate_scripts` duration | Establish baseline |
| **Execution Time** | `execute` stage duration | Establish baseline |
| **Pass Rate** | Passed tests / total tests (latest run) | ≥ 90% |
| **Discovered Pages** | Count of pages in AppMap | Informational |
| **Automation Rate** | Generated tests / estimated manual effort (1 test = 15 min manual) | ≥ 10× speedup |
| **LLM Cost** | `pipeline_runs.cost_estimate` sum (rolling 30 days) | Monitor; alert > $50/mo dev (see §32) |

**Dashboard views:** Global overview, per-app detail, pipeline run drill-down, trend charts (Phase 2 history).

---

## 21. Application Health Score

Stored in `applications.overall_health_score` (0.0–1.0). Recalculated after each execution run.

**Formula:**

```
health_score = (0.4 × coverage) + (0.3 × pass_rate) + (0.3 × (1 - flakiness))
```

Where:

- `coverage` = Flow Coverage (§20) as decimal (0.0–1.0)
- `pass_rate` = Pass Rate (§20) as decimal (0.0–1.0)
- `flakiness` = Flakiness Rate (§20) as decimal (0.0–1.0), capped at 1.0

**Display thresholds:**

| Score | Label | Color |
|-------|-------|-------|
| ≥ 0.8 | Healthy | Green |
| 0.5 – 0.79 | At Risk | Yellow |
| < 0.5 | Critical | Red |

---

## 22. Observability

### 22.1 Logging (Pino)

- Structured JSON logs to stdout
- Log levels: `fatal`, `error`, `warn`, `info`, `debug`
- **Secret masking:** Pino redact paths: `auth_config`, `password`, `token`, `api_key`, `credentials`
- Never log decrypted credentials or full `auth_config`
- Include `pipeline_run_id`, `application_id`, `stage` in all worker logs

### 22.2 Metrics (Prometheus)

Expose `GET /metrics` (Prometheus text format) from the API service.

| Metric Name | Type | Description |
|-------------|------|-------------|
| `aqa_crawl_time_seconds` | Histogram | Discovery stage duration |
| `aqa_generation_time_seconds` | Histogram | Test + script generation duration |
| `aqa_execution_time_seconds` | Histogram | Execution stage duration |
| `aqa_queue_depth` | Gauge | Celery waiting jobs per queue |
| `aqa_failed_runs_total` | Counter | Cumulative failed pipeline runs |
| `aqa_browser_sessions_active` | Gauge | Active Playwright browser contexts |
| `aqa_llm_requests_total` | Counter | LLM API calls by core agent id and mode |
| `aqa_llm_cost_dollars` | Counter | Cumulative estimated LLM cost |

### 22.3 Alerting (Phase 2+)

- Prometheus alert rules for `failed_runs_total` spike, `queue_depth` > threshold
- MVP: dashboard-only monitoring

### 22.4 OpenAI Cost Controls (Summary)

Detailed controls are defined in §32. MVP enforces token budgets per pipeline run, prompt caching, and cost attribution via `pipeline_runs.llm_tokens_used` and `cost_estimate`.

---

## 23. Security Requirements

### 23.1 Credential Protection

| Requirement | Implementation |
|-------------|----------------|
| Encrypt `auth_config` at rest | AES-256-GCM; key from `ENCRYPTION_KEY` env var |
| Never log credentials | Pino redaction (§22.1) |
| Never expose credentials via APIs | Return `{ configured: true, type }` only; strip secrets from all responses |
| Store secrets in environment variables | Credentials referenced by `credentials_secret_ref`; resolved at worker runtime |
| Session-cookie authentication | Support `auth_config.cookies[]` injection |
| Credential access audit logging | Write to `credential_access_audit` on every decrypt/inject |

### 23.2 Artifact Security

- Serve artifacts via authenticated proxy (`GET /api/v1/artifacts/:id`)
- Signed URLs expire after 15 minutes
- Artifact paths never expose raw filesystem structure to clients

### 23.3 Network Security

- **SSRF mitigation:** Reject `base_url` and `seed_urls` resolving to private IP ranges (`10.x`, `172.16–31.x`, `192.168.x`, `127.x`, `169.254.x`) unless `crawl_config.allow_private_ips: true`
- Domain allowlist enforced during crawl (§15.1)

### 23.4 Platform Authentication (MVP)

- Single-user dev mode; no platform auth in MVP
- Phase 4: JWT + RBAC + SSO

---

## 24. Frontend Specification (MVP)

### 24.1 Pages

| Route | Purpose |
|-------|---------|
| `/` | Dashboard: metrics (§20), health scores, recent runs |
| `/apps` | List registered applications |
| `/apps/new` | Register app form |
| `/apps/[id]` | App detail: AppMap, tests, runs, health score |
| `/apps/[id]/discover` | Trigger/view discovery progress |
| `/apps/[id]/pipeline` | Full pipeline launcher + SSE progress |
| `/runs/[id]` | Run detail, results, artifact viewer, report link |
| `/settings` | Integration config (not raw credentials) |

### 24.2 Key UI Components

- **AppMapGraph:** Interactive node-edge graph (React Flow)
- **PipelineProgress:** Stage stepper with SSE updates tied to `pipeline_runs.current_stage`
- **MetricsPanel:** Flow coverage, pass rate, flakiness, LLM cost
- **HealthScoreBadge:** Visual indicator per §21
- **TestCaseList:** Generated tests with approve/archive actions
- **RunResultsTable:** Pass/fail with artifact links
- **ArtifactViewer:** Screenshot, trace, video preview via secure proxy

---

## 25. CI/CD Integration

### 25.1 GitHub Actions Workflow

**Trigger:** `workflow_dispatch` (manual) + nightly cron

**Steps:**
1. Checkout platform repo
2. Start Docker Compose full stack: `docker compose -f docker/docker-compose.full.yml up -d`
3. Call `POST /api/v1/apps/:id/pipeline` with target URL from secrets
4. Poll `GET /api/v1/pipeline-runs/:id` until `status != running`
5. Upload Allure artifact
6. Fail workflow if pass rate < 90% or health score < 0.5

### 25.2 Docker Compose Services (MVP / CI)

Defined in `docker/docker-compose.full.yml` (Phase 2 / CI — not used for Phase 1 local dev where Postgres and Redis run natively):

| Service | Image / Build | Ports |
|---------|---------------|-------|
| `postgres` | postgres:15 | 5432 |
| `redis` | redis:7 | 6379 |
| `api` | build `apps/api` | 3001 |
| `worker-celery` | build `workers/celery_app` | — |
| `worker-crawl` | build `workers/discovery-worker` | — |
| `worker-execute` | build `workers/playwright-executor` | — |
| `worker-report` | build `workers/reporting-worker` | — |
| `web` | build `apps/web` | 3000 |

### 25.3 Local Development Setup

For day-to-day development, **PostgreSQL and Redis run natively** on the host (e.g. Homebrew PostgreSQL 17 + local Redis 7). Docker Compose is reserved for **CI and Phase 2 full stack** — see `docker/docker-compose.full.yml` and [PHASE-2-SPEC.md §13](./PHASE-2-SPEC.md#13-infrastructure--docker).

| Component | Local dev (current) | CI / Phase 2 full stack |
|-----------|---------------------|-------------------------|
| **PostgreSQL** | Native PG 17 on `localhost:5432` | Docker `postgres:15` (`docker-compose.full.yml`) |
| **Redis** | Native Redis 7+ on `localhost:6379` | Docker `redis:7-alpine` (`docker-compose.full.yml`) |
| **API** | `pnpm dev:api` (Uvicorn) → port `3001` | Docker `api` service |
| **Celery workers** | `pnpm dev:worker:celery` | Docker `worker-celery` |

**Local PostgreSQL bootstrap:**

```sql
CREATE ROLE aqa WITH LOGIN PASSWORD 'aqa' CREATEDB;
CREATE DATABASE autonomous_qa OWNER aqa;
```

**Local Redis bootstrap (Homebrew example):**

```bash
brew install redis
brew services start redis
redis-cli ping   # expect PONG
```

**Daily commands:**

```bash
brew services start postgresql@17          # if using native Postgres
brew services start redis                  # local Redis (not Docker)
pnpm setup:python                          # first time: create .venv + install deps
pnpm db:stamp                              # existing DB migrated from Prisma
# OR pnpm db:migrate                       # fresh DB: apply Alembic migrations
pnpm verify:db
pnpm dev:api
```

**pgAdmin:** Connect with `postgresql://aqa:aqa@localhost:5432/autonomous_qa`. On Homebrew PostgreSQL, the superuser is typically your macOS username — use the `aqa` role for this project, not `postgres`.

**Port conflict:** Only one process may bind `5432`. Stop Docker Postgres or native Postgres before switching modes.

---

## 26. Phased Roadmap

### Phase 1 — Core Automation (Weeks 1–12, MVP)

**Agent stack:** 5 core agents (4 active + `IntelligenceAgent` stub) + 3 workers.

| Agent / Worker | MVP Status |
|----------------|------------|
| `DiscoveryAgent` | Active |
| `TestDesignAgent` | Active (UI modes only) |
| `ScriptGenerationAgent` | Active (Playwright mode) |
| `HealingAgent` | Active (codegen repair) |
| `IntelligenceAgent` | Stub — no LLM calls; coverage computed by code |
| `DiscoveryWorker` | Active |
| `PlaywrightExecutor` | Active |
| `ReportingWorker` | Active |

| Week | Deliverable |
|------|-------------|
| 1–2 | Monorepo scaffold, 5 agent shells, 3 workers, DB schema, Docker Compose |
| 3–4 | `DiscoveryAgent` + `DiscoveryWorker`, AppMap persistence, SSE progress |
| 5–6 | `TestDesignAgent` + `ScriptGenerationAgent` + `ValidationModule` + `HealingAgent` |
| 7–8 | `PlaywrightExecutor` with full artifact capture and retry policy (§18) |
| 9–10 | `ReportingWorker`, dashboard metrics (§20), health score (§21), GitHub Actions |
| 11–12 | Benchmark validation (Juice Shop), security hardening (§23), README/runbook |

**Phase 1 success criteria:**
- 80%+ flow coverage on benchmark apps
- Flakiness < 5%
- Full pipeline without manual script editing
- All Definition of Done criteria (§5) met

### Phase 2 — Extended Testing (Months 4–6)

Enable 5 additional plugins by adding **agent modes** and **workers** — no new LLM agents.

**Detailed specification:** See [PHASE-2-SPEC.md](./PHASE-2-SPEC.md) for full plugin specs, schema definitions, API endpoints, validation rules, infrastructure, and delivery plan.

| Deliverable | Agents used | Workers added |
|-------------|-------------|---------------|
| API Plugin | `discover:api`, `design:api`, `script:api` | APIExecutor |
| Security Plugin | `design:security` | ZAPRunner |
| Accessibility Plugin | `design:a11y`, `script:a11y` | AccessibilityRunner |
| Visual Plugin | `design:visual`, `script:visual` | PlaywrightExecutor (visual mode) |
| Performance Plugin | `design:performance`, `script:k6` | K6Runner |

Enhanced reporting history. **Full platform worker count: 6** (+ APIExecutor, ZAPRunner, AccessibilityRunner, K6Runner; DiscoveryWorker + PlaywrightExecutor + ReportingWorker from MVP).

### Phase 3 — Intelligent Agents (Months 7–12)

Activate **`IntelligenceAgent`** (full LLM): root-cause analysis, defect intelligence, test data generation, requirements import (Jira/Gherkin modes). Activate **`HealingAgent`** runtime locator healing (post-execution). No new agent classes.

### Phase 4 — Scale & Enterprise (Months 13–18)

Kubernetes, multi-tenancy, RBAC, SSO, Neo4j/vector DB, audit trails, alpha release. Agent architecture unchanged.

---

## 27. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Incomplete SPA crawl | Missing flows | Seed URLs (§15.5), iterative re-crawl, manual flow import |
| LLM hallucination | Invalid tests/code | AI validation gates (§13); 2 retries; no invalid persistence |
| MFA/CAPTCHA | Blocked login | Cookie injection (§15.8–15.9); test credentials |
| Flaky tests | False failures | Retry policy (§18), semantic locators (§12), flakiness tracking |
| LLM cost | Budget overrun | Token tracking in `pipeline_runs`; Prometheus `llm_cost` metric |
| SSRF via user URL | Security breach | Private IP blocking (§23.3), domain allowlist |
| Credential leakage | Security breach | Encryption, redaction, audit logging (§23.1) |

---

## 28. Prototype Reuse

From `d:\software_testing_Project\software testing\`:

| Asset | Reuse |
|-------|-------|
| `orchestrator.js` | SSE broadcast + staged pipeline pattern |
| `llm.js` | LLM provider abstraction (add OpenAI + validation gates) |
| `jira.js` | Defect sync on failed runs |
| Agent layout | Module structure inspiration |
| Dashboard UX | Tab layout, live pipeline view patterns |

**Do not reuse:** requirements-only entry point, simulated execution, JSON file DB.

---

## 29. Environment Variables

```env
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/autonomous_qa

# Redis / Celery
REDIS_URL=redis://localhost:6379
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Encryption
ENCRYPTION_KEY=                          # 32-byte hex key for auth_config encryption

# LLM
OPENAI_API_KEY=
GEMINI_API_KEY=
LLM_BUDGET_PER_PIPELINE=2.00
LLM_BUDGET_PER_APP_DAILY=10.00

# Target app credentials (referenced by credentials_secret_ref)
JUICE_SHOP_TEST_USER={"email":"...","password":"..."}

# Jira (optional)
JIRA_BASE_URL=
JIRA_EMAIL=
JIRA_API_TOKEN=
JIRA_PROJECT_KEY=

# Platform
API_PORT=3001
WEB_PORT=3000
ARTIFACT_STORAGE_PATH=./artifacts
NODE_ENV=development
LOG_LEVEL=info
```

---

## 30. References

- Executive Summary PDF: `c:\Users\Dell\Downloads\Executive Summary.pdf`
- Playwright Test Agents: planner / generator / healer pipeline
- LangGraph: agent orchestration
- OWASP ZAP, k6, axe-core, Allure (Phase 2+ integrations)
- Forrester "Autonomous Testing Platforms" category
- Related prototype: `d:\software_testing_Project\software testing\`

---

## 31. Agent Design

This section defines the **consolidated agent architecture**. The platform uses **5 core AI agents** plus **deterministic workers**. Plugins configure agent **modes** — they do not add new LLM agent classes.

**Architecture principle:** One domain capability = one agent — NOT one responsibility = one agent.

**Goal state:**

| Milestone | AI Agents | Workers |
|-----------|-----------|---------|
| **Phase 1 MVP** | 5 core (4 active + IntelligenceAgent stub) | 3 |
| **Full platform** | 5 core (all active) | 6 |

### 31.1 Consolidated Agent Model

| # | Core Agent | Domain capability | Replaces (deprecated agents) |
|---|------------|-------------------|------------------------------|
| 1 | **DiscoveryAgent** | URL crawl, page/element/flow/API discovery, AppMap generation | Crawler Agent, FlowAnalyzerAgent, API Discovery Agent |
| 2 | **TestDesignAgent** | All test scenario design across plugins | TestPlannerAgent, APITestPlannerAgent, SecurityScanPlannerAgent, A11yTestPlannerAgent, LoadScenarioPlannerAgent, RequirementsParserAgent |
| 3 | **ScriptGenerationAgent** | All executable script generation | ScriptPlannerAgent, ScriptGeneratorAgent, APIScriptGeneratorAgent, VisualTestGeneratorAgent, K6ScriptGeneratorAgent |
| 4 | **IntelligenceAgent** | Analysis, defects, data, optimization | RootCauseAgent, DefectIntelligenceAgent, TestDataGeneratorAgent |
| 5 | **HealingAgent** | Locator healing, script repair, retry strategy | HealerAgent, LocatorHealerAgent |

**Deterministic (not agents):**

| Module / Worker | Role |
|-----------------|------|
| **ValidationModule** | JSON Schema, TypeScript compile, Playwright syntax, locator policy (§13) — replaces ValidationAgent |
| **DiscoveryWorker** | Playwright headless crawl (no LLM) |
| **PlaywrightExecutor** | UI + visual test execution |
| **APIExecutor** | HTTP/API test execution |
| **ZAPRunner** | OWASP ZAP scans |
| **AccessibilityRunner** | axe-core audits |
| **K6Runner** | Load/stress tests |
| **ReportingWorker** | Allure generation, artifact assembly (no LLM) |

### 31.2 Agent Mode Matrix

Each core agent accepts a `mode` parameter set by the active plugin:

#### DiscoveryAgent modes

| Mode | Plugin | Output |
|------|--------|--------|
| `ui` | UI | Pages, elements, flows, screenshots |
| `api` | API, Security | Endpoints, methods, schemas (from network + OpenAPI) |

#### TestDesignAgent modes

| Mode | Plugin | Output |
|------|--------|--------|
| `functional` | UI | Smoke, regression, CRUD, boundary tests |
| `api` | API | HTTP test scenarios, schema assertions |
| `security` | Security | DAST scan scenarios, OWASP Top 10 coverage |
| `a11y` | Accessibility | WCAG check scenarios per page |
| `visual` | Visual | Baseline comparison scenarios |
| `performance` | Performance | Load/stress scenario definitions |
| `requirements` | Phase 3 | Jira/Gherkin → test cases |

#### ScriptGenerationAgent modes

| Mode | Plugin | Output |
|------|--------|--------|
| `playwright` | UI | Playwright TypeScript |
| `api` | API | Playwright `request` or HTTP client scripts |
| `a11y` | Accessibility | axe-core injection scripts |
| `visual` | Visual | Playwright snapshot scripts |
| `k6` | Performance | k6 JavaScript |

#### IntelligenceAgent modes

| Mode | Phase | Output |
|------|-------|--------|
| `coverage` | MVP (code-only stub) | Coverage metrics, no LLM |
| `analyze` | 3 | Root-cause classification |
| `defect` | 3 | Jira-ready defect summaries |
| `testdata` | 3 | Synthetic test data |
| `optimize` | 3 | Test suite optimization recommendations |

#### HealingAgent modes

| Mode | Phase | Output |
|------|-------|--------|
| `codegen` | MVP | Repaired script after validation failure |
| `locator` | 3 | Updated selector after DOM change |
| `retry` | 3 | Retry strategy recommendation |

### 31.3 MVP Agent Stack

**5 core AI agents + 3 workers** (IntelligenceAgent runs in `coverage` mode without LLM):

```
DiscoveryAgent (mode: ui)
  → DiscoveryWorker
  → TestDesignAgent (mode: functional)
  → ScriptGenerationAgent (mode: playwright)
      ↔ HealingAgent (mode: codegen) on validation failure
  → PlaywrightExecutor
  → IntelligenceAgent (mode: coverage, deterministic)
  → ReportingWorker
```

| Component | LLM | MVP |
|-----------|-----|-----|
| DiscoveryAgent | Yes (flow structuring) | Active |
| TestDesignAgent | Yes | Active |
| ScriptGenerationAgent | Yes | Active |
| HealingAgent | Yes | Active |
| IntelligenceAgent | No in MVP | Stub (`coverage` mode) |
| DiscoveryWorker | No | Active |
| PlaywrightExecutor | No | Active |
| ReportingWorker | No | Active |
| ValidationModule | No | Active |

### 31.4 Full Platform Agent Stack

**5 core AI agents + 6 workers + 6 plugins** (no new LLM agents in Phase 2):

| Worker | Phase | Plugin |
|--------|-------|--------|
| DiscoveryWorker | 1 | All (crawl) |
| PlaywrightExecutor | 1 | UI, Visual |
| APIExecutor | 2 | API |
| ZAPRunner | 2 | Security |
| AccessibilityRunner | 2 | Accessibility |
| K6Runner | 2 | Performance |
| ReportingWorker | 1 | All (shared) |

ReportingWorker is shared across plugins and is not an LLM agent. **Six workers** in the user's target count refers to DiscoveryWorker + five plugin executors; ReportingWorker is shared reporting infrastructure (7 deterministic processes total).

### 31.5 Agent Architecture Pattern

Each core AI agent is a **LangGraph (Python) state machine** with mode-specific prompt templates:

```mermaid
stateDiagram-v2
  [*] --> ReceiveMode: plugin context plus mode
  ReceiveMode --> Plan: build prompt from mode template
  Plan --> Act: LLM call
  Act --> Validate: ValidationModule
  Validate --> Persist: pass
  Validate --> Heal: HealingAgent codegen mode
  Heal --> Act: retry up to 2 times
  Validate --> Fail: max retries
  Persist --> [*]
  Fail --> [*]
```

**Shared agent interface:**

```typescript
type AgentMode = string;

interface AgentContext {
  pipelineRunId: string;
  applicationId: string;
  pluginId: string;
  mode: AgentMode;
  appMap?: AppMapSnapshot;
  priorErrors?: string[];
  tokenBudgetRemaining: number;
}

interface CoreAgent<TInput, TOutput> {
  readonly id: 'discovery' | 'test-design' | 'script-generation' | 'intelligence' | 'healing';
  run(input: TInput, ctx: AgentContext): Promise<AgentResult<TOutput>>;
}
```

### 31.6 Per-Agent Specifications

#### DiscoveryAgent

- **Input:** `base_url`, `seed_urls`, `auth_config`, `crawl_config`, mode (`ui` | `api`)
- **LLM role:** Structure crawl results into flows; prioritize pages; infer API endpoints from network log
- **Worker delegation:** Issues crawl instructions to `DiscoveryWorker` (Playwright, no LLM)
- **Output:** AppMap persisted to DB + `appmap` artifact

#### TestDesignAgent

- **Input:** AppMap snapshot, mode, `max_tests`, priorities
- **LLM role:** Generate structured test cases per mode (JSON only)
- **Rule-based fallback:** Deterministic templates run first; LLM fills coverage gaps (§32.3)
- **Output:** `test_cases` validated by `ValidationModule`

#### ScriptGenerationAgent

- **Input:** `test_case`, AppMap selectors, mode (`playwright` | `api` | `a11y` | `visual` | `k6`)
- **LLM role:** Plan steps + emit executable script in one graph (replaces separate planner/generator agents)
- **Validation:** `ValidationModule` — tsc, Playwright syntax, locator policy (§12)
- **On failure:** Delegates to `HealingAgent` (mode: `codegen`), max 2 retries
- **Output:** `test_scripts` + `generated_script` artifact

#### IntelligenceAgent

- **MVP (`coverage` mode):** Compute flow/page coverage from DB — **no LLM**
- **Phase 3 modes:** Root-cause, defect summaries, test data, requirements parsing, optimization
- **Input:** Run results, artifacts, historical data
- **Output:** Classifications, defect drafts, synthetic data, coverage recommendations

#### HealingAgent

- **MVP (`codegen` mode):** Repair failed script generation using validation error context
- **Phase 3 (`locator` mode):** DOM snapshot → new semantic selector → patch script
- **Phase 3 (`retry` mode):** Recommend retry vs fail for flaky tests
- **Output:** Repaired script or selector; re-submitted to ValidationModule

### 31.7 Context Management & Token Budget

Single budget pool per pipeline run shared across all 5 agents (§32):

| Context slice | Max tokens | Notes |
|---------------|------------|-------|
| AppMap (Discovery + Design) | 6,000 | Shared snapshot; cached via AppMap hash |
| Test cases (Script gen) | 2,000 | Per batch of 5 cases |
| Failure context (Healing) | 500 | Last error only |
| **Max per agent call** | **8,000 input** | Hard cap |

**Consolidation benefit:** ~60% fewer LLM round-trips vs. specialized agent model (design + script in 2 calls vs. planner + generator + analyzer chain per plugin).

Agents **must** check `tokenBudgetRemaining` on `AgentContext` before calling OpenAI (see §32).

### 31.8 Agent Communication

Agents do **not** call each other directly except `ScriptGenerationAgent` → `HealingAgent` on validation failure.

```
Orchestrator → Celery → Agent (with mode) → ValidationModule
                              ↓ fail
                         HealingAgent → Agent retry
                              ↓
                         Worker (deterministic execute)
                              ↓
                         IntelligenceAgent → ReportingWorker
```

All token usage aggregated on `pipeline_runs.llm_tokens_used` and `cost_estimate`. State persisted in PostgreSQL; raw LLM responses in redacted logs only.

### 31.9 Agent Failure Modes

| Failure | Handler | Pipeline impact |
|---------|---------|-----------------|
| Validation fail (< 3 attempts) | HealingAgent (`codegen`) | Continue |
| Validation fail (exhausted) | Skip item; log | Continue other tests |
| Token budget exceeded | Rule-based fallback | Warning on pipeline run |
| OpenAI 429/5xx | Backoff + Gemini fallback (§32.6) | Fail stage if exhausted |
| Worker fail (executor) | No LLM retry; log artifacts | Plugin stage fails |

### 31.10 Deprecated Agent Mapping

| Deprecated agent | Successor |
|------------------|-----------|
| FlowAnalyzerAgent | DiscoveryAgent + IntelligenceAgent (`coverage`) |
| TestPlannerAgent | TestDesignAgent |
| ScriptPlannerAgent | ScriptGenerationAgent (internal plan step) |
| ScriptGeneratorAgent | ScriptGenerationAgent |
| ValidationAgent | ValidationModule (code) |
| HealerAgent | HealingAgent (`codegen`) |
| APITestPlannerAgent | TestDesignAgent (`api`) |
| APIScriptGeneratorAgent | ScriptGenerationAgent (`api`) |
| SecurityScanPlannerAgent | TestDesignAgent (`security`) |
| A11yTestPlannerAgent | TestDesignAgent (`a11y`) |
| LoadScenarioPlannerAgent | TestDesignAgent (`performance`) |
| VisualTestGeneratorAgent | ScriptGenerationAgent (`visual`) |
| K6ScriptGeneratorAgent | ScriptGenerationAgent (`k6`) |
| RootCauseAgent | IntelligenceAgent (`analyze`) |
| DefectIntelligenceAgent | IntelligenceAgent (`defect`) |
| TestDataGeneratorAgent | IntelligenceAgent (`testdata`) |
| RequirementsParserAgent | TestDesignAgent (`requirements`) |
| LocatorHealerAgent | HealingAgent (`locator`) |

### 31.11 Consolidated Architecture Benefits

| Benefit | Impact |
|---------|--------|
| **Reduced token usage** | ~60% fewer LLM calls per pipeline; shared AppMap context across agents |
| **Reduced orchestration complexity** | 5 LangGraph graphs vs. 22+ agent classes; one Celery job per stage |
| **Easier debugging** | One log namespace per capability; `mode` + `pluginId` on every call |
| **Lower implementation effort** | 5 agents + 7 workers vs. 22+ agents + scattered workers |
| **Faster MVP delivery** | Phase 2 adds modes + workers only — no new agent classes |
| **Better maintainability** | Prompt templates per mode in `packages/shared/src/prompts/` |
| **Preserved capabilities** | All 6 testing plugins supported without plugin-specific LLM agents |
| **Plugin extensibility** | New test type = new mode + worker, not new agent class |

---

## 32. OpenAI Cost Controls

LLM usage is a primary operational cost. The platform enforces controls at pipeline, stage, and request levels.

### 32.1 Cost Attribution

Every LLM call **must** record:

| Field | Storage | Description |
|-------|---------|-------------|
| `prompt_tokens` | Log + aggregate | Input tokens |
| `completion_tokens` | Log + aggregate | Output tokens |
| `model` | Log | e.g. `gpt-4o` |
| `cost_estimate` | `pipeline_runs.cost_estimate` | Calculated from model pricing table |
| `stage` | Log | Agent id + mode: `discovery:ui`, `test-design:functional`, etc. |

**Pricing table:** Maintained in `packages/shared/src/llm/pricing.ts` (updated manually when OpenAI changes rates).

```
cost = (prompt_tokens × input_rate) + (completion_tokens × output_rate)
```

### 32.2 Budget Limits (MVP)

| Limit | Default | Config Key | Behavior When Exceeded |
|-------|---------|------------|------------------------|
| Per pipeline run | $2.00 USD | `LLM_BUDGET_PER_PIPELINE` | Stop LLM calls; fall back to rule-based generation |
| Per application (daily) | $10.00 USD | `LLM_BUDGET_PER_APP_DAILY` | Reject new pipeline runs with `402`-style error |
| Per agent call (input) | 8,000 tokens | Hard-coded | Truncate context (§31.5) |
| Per agent call (output) | 4,000 tokens | `max_tokens` param | Truncate + validation retry |
| Max tests via LLM | 50 | Request body `max_tests` | Cap generation count |

### 32.3 Cost Optimization Strategies

| Strategy | Implementation | Phase |
|----------|----------------|-------|
| **AppMap prompt caching** | Hash AppMap JSON; reuse test plan if AppMap unchanged since last crawl | MVP |
| **Rule-based first** | Generate deterministic tests before LLM; LLM fills gaps only | MVP |
| **Consolidated agent calls** | Max 3 LLM calls per test case (design + script + heal) vs. 6+ in v2.1 model | MVP |
| **Batch script generation** | ScriptGenerationAgent processes 5 test cases per call | MVP |
| **Skip LLM on re-run** | If AppMap hash unchanged and scripts exist, skip `generate_*` stages | MVP |
| **Model tiering** | Use `gpt-4o-mini` for test planning; `gpt-4o` for script codegen only | Phase 2 |
| **Local model fallback** | LLaMA 3 for non-codegen tasks | Phase 3 |

### 32.4 AppMap Cache Key

```
appmap_hash = SHA256(normalized_pages + normalized_flows + element_count)
```

Stored on `pipeline_runs.config.appmap_hash`. If `discover` stage produces the same hash as the previous successful run, downstream stages may skip LLM generation when `force: false`.

### 32.5 Monitoring & Alerts

| Signal | Source | MVP Action |
|--------|--------|------------|
| `aqa_llm_cost_dollars` | Prometheus (§22.2) | Dashboard display |
| `aqa_llm_requests_total` | Prometheus | Dashboard display |
| Daily spend > budget | API middleware | Reject pipeline; log warning |
| Anomalous token spike | Log analysis | Pino `warn` if single call > 12K tokens |

**Dashboard (§20):** Display rolling 30-day LLM cost per app and globally.

### 32.6 Gemini Fallback

When `GEMINI_API_KEY` is set and OpenAI returns 429/5xx after retries:

1. Switch to Gemini for current agent call only
2. Log provider switch event
3. Do **not** double-count budget (use Gemini pricing table separately)
4. Mark `pipeline_runs.config.llm_provider_fallback = true`

---

## 33. Versioning Strategy

Versioning ensures traceability across discovery, generation, and execution. Every artifact is reproducible from its version metadata.

### 33.1 Versioning Principles

1. **Immutable history:** Regenerating scripts creates a new version; old versions are never overwritten
2. **Pipeline linkage:** Every generated artifact links to the `pipeline_run_id` that produced it
3. **Execution binding:** Test runs execute a specific script `version`, not "latest"
4. **AppMap snapshots:** Each discovery run produces a point-in-time AppMap artifact

### 33.2 Entity Versioning Rules

#### Applications

| Change | Version Impact |
|--------|----------------|
| `base_url`, `seed_urls`, `crawl_config` change | Increment internal `config_version` (JSONB metadata); trigger re-discovery recommendation |
| `auth_config` change | Same; invalidate cached session |
| Health score update | No config version change |

Column `applications.config_version` (INT, default 1) is defined in SQLAlchemy models (`packages/aqa_shared`) and incremented on URL/crawl/auth changes.

#### AppMap (Pages, Elements, Flows)

| Event | Behavior |
|-------|----------|
| New discovery run | Upsert pages/elements by canonical URL + selector hash; soft-delete stale pages (`discovered_at` older than latest crawl) |
| AppMap artifact | Immutable JSON export per `pipeline_run_id` stored at `artifacts/appmaps/{pipeline_run_id}.json` |
| Comparison | Dashboard shows diff between last two AppMap artifacts (Phase 2) |

#### Test Cases

| Field | Version Behavior |
|-------|------------------|
| `status` | `draft` → `approved` → `archived` (lifecycle, not numeric version) |
| Regeneration | Old test case archived; new record created with same `name` + new `testcase_id` OR update in place if `force_regenerate: false` and steps unchanged |
| Linkage | Add `pipeline_run_id` FK on `test_cases` for generation batch tracking |

#### Test Scripts

| Rule | Detail |
|------|--------|
| Numeric version | `test_scripts.version` starts at 1; increment on each validated regeneration |
| Unique constraint | `(testcase_id, version)` unique |
| Active script | Latest validated version used for execution unless `script_ids` specified in execute request |
| Artifact mirror | Each version stored at `artifacts/generated-scripts/{script_id}_v{version}.ts` |

#### Test Runs

| Rule | Detail |
|------|--------|
| Execution record | `test_runs` stores `script_id` + script `version` in `summary` JSONB |
| Re-run | Same script version re-executed unless regeneration occurred between runs |
| Immutability | Run results never modified after `ended_at` is set |

### 33.3 API Versioning

| Layer | Strategy |
|-------|----------|
| REST API | URL prefix `/api/v1/`; breaking changes require `/api/v2/` |
| JSON schemas | `TestCaseSchema` version in `$id` (e.g. `.../schemas/testcase/v1`) |
| Agent prompts | Prompt template per agent + mode: `test-design.functional.v1.txt` (§31.2) |

### 33.4 Migration & Rollback

| Scenario | Action |
|----------|--------|
| Bad script generation | Execute previous `version - 1` via `script_ids` + version pin |
| Bad discovery | Re-run discover with `force: true`; previous AppMap artifact retained |
| Schema migration | Alembic migrations with backward-compatible columns; no destructive drops in MVP |

---

## 34. Database Index Strategy

Indexes are required for dashboard queries, pipeline orchestration, and worker lookups at MVP scale (≤100 apps, ≤10K pages, ≤100K elements).

### 34.1 Index Design Principles

1. Index all foreign keys used in JOINs and cascades
2. Composite indexes for common filter + sort patterns
3. Partial indexes for hot status queries (`status = 'running'`)
4. Avoid over-indexing JSONB unless query pattern is proven (Phase 2)

### 34.2 Required Indexes (MVP)

#### `applications`

```sql
CREATE INDEX idx_applications_name ON applications (name);
CREATE INDEX idx_applications_last_run_at ON applications (last_run_at DESC NULLS LAST);
CREATE INDEX idx_applications_health_score ON applications (overall_health_score DESC NULLS LAST);
```

#### `pages`

```sql
CREATE INDEX idx_pages_app_id ON pages (app_id);
CREATE UNIQUE INDEX idx_pages_app_url ON pages (app_id, url);
CREATE INDEX idx_pages_discovered_at ON pages (app_id, discovered_at DESC);
```

#### `elements`

```sql
CREATE INDEX idx_elements_page_id ON elements (page_id);
CREATE INDEX idx_elements_app_page ON elements (page_id) INCLUDE (semantic_selector);
-- Worker lookup: all elements for an app via join
CREATE INDEX idx_elements_page_app ON pages (app_id) WHERE app_id IS NOT NULL; -- covered by idx_pages_app_id
```

#### `flows`

```sql
CREATE INDEX idx_flows_app_id ON flows (app_id);
CREATE INDEX idx_flows_source ON flows (app_id, source);
```

#### `test_cases`

```sql
CREATE INDEX idx_test_cases_app_id ON test_cases (app_id);
CREATE INDEX idx_test_cases_status ON test_cases (app_id, status);
CREATE INDEX idx_test_cases_priority ON test_cases (app_id, priority);
CREATE INDEX idx_test_cases_pipeline ON test_cases (pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;
```

#### `test_scripts`

```sql
CREATE INDEX idx_test_scripts_testcase ON test_scripts (testcase_id);
CREATE UNIQUE INDEX idx_test_scripts_version ON test_scripts (testcase_id, version);
CREATE INDEX idx_test_scripts_validated ON test_scripts (testcase_id, validated_at DESC);
```

#### `test_runs`

```sql
CREATE INDEX idx_test_runs_app_id ON test_runs (app_id, started_at DESC);
CREATE INDEX idx_test_runs_pipeline ON test_runs (pipeline_run_id);
CREATE INDEX idx_test_runs_status ON test_runs (app_id, status);
CREATE INDEX idx_test_runs_flaky ON test_runs (app_id, is_flaky) WHERE is_flaky = true;
```

#### `results`

```sql
CREATE INDEX idx_results_run_id ON results (run_id);
CREATE INDEX idx_results_script ON results (script_id);
CREATE INDEX idx_results_outcome ON results (run_id, outcome);
```

#### `pipeline_runs` (Master orchestration — highest query volume)

```sql
CREATE INDEX idx_pipeline_runs_app ON pipeline_runs (application_id, started_at DESC);
CREATE INDEX idx_pipeline_runs_status ON pipeline_runs (status);
CREATE INDEX idx_pipeline_runs_active ON pipeline_runs (application_id, status)
  WHERE status IN ('pending', 'running');
CREATE INDEX idx_pipeline_runs_stage ON pipeline_runs (current_stage, status);
```

**Critical query:** "Does this app have an active pipeline?" → `idx_pipeline_runs_active` (partial index).

#### `artifacts`

```sql
CREATE INDEX idx_artifacts_run ON artifacts (run_id) WHERE run_id IS NOT NULL;
CREATE INDEX idx_artifacts_pipeline ON artifacts (pipeline_run_id) WHERE pipeline_run_id IS NOT NULL;
CREATE INDEX idx_artifacts_type ON artifacts (type, created_at DESC);
```

#### `defects`

```sql
CREATE INDEX idx_defects_run ON defects (run_id);
CREATE INDEX idx_defects_status ON defects (status);
```

#### `credential_access_audit`

```sql
CREATE INDEX idx_credential_audit_app ON credential_access_audit (app_id, timestamp DESC);
CREATE INDEX idx_credential_audit_pipeline ON credential_access_audit (pipeline_run_id);
```

### 34.3 Query → Index Mapping

| Query Pattern | Index Used |
|---------------|------------|
| List apps by health score (dashboard) | `idx_applications_health_score` |
| AppMap pages for app | `idx_pages_app_id` |
| Dedupe page on crawl | `idx_pages_app_url` (unique) |
| Active pipeline check (409 conflict) | `idx_pipeline_runs_active` |
| Run history for app | `idx_test_runs_app_id` |
| Failed results drill-down | `idx_results_outcome` |
| Artifacts for run report | `idx_artifacts_run` |
| Latest validated script | `idx_test_scripts_validated` |

### 34.4 Maintenance

| Task | Frequency |
|------|-----------|
| `ANALYZE` after bulk crawl | After each discovery stage |
| Index bloat review | Monthly (Phase 2) |
| Add JSONB GIN index on `crawl_config` | Phase 2 only if filtered queries needed |

### 34.5 Scaling Notes (Phase 4)

- Partition `test_runs` and `results` by `started_at` (monthly) when rows > 10M
- Read replicas for dashboard analytics queries
- Connection pooling via PgBouncer

---

## 35. Glossary

| Term | Definition |
|------|------------|
| **AppMap** | Graph of discovered pages, UI elements, and user flows |
| **Pipeline Run** | Master orchestration record in `pipeline_runs` spanning one or more stages |
| **Semantic Selector** | Playwright locator based on role, label, or visible text (§12) |
| **Self-Healing** | Automatic selector repair when DOM changes (Phase 3) |
| **Defect Intelligence** | AI root-cause analysis and failure classification (Phase 3) |
| **TestingPlugin** | Pluggable interface for UI, API, security, and other test engines (§8.4) |
| **Health Score** | Composite metric: coverage + pass rate + flakiness (§21) |
| **CoreAgent** | One of 5 consolidated AI agents with mode-based behavior (§31) |
| **ValidationModule** | Deterministic validation gate — not an LLM agent (§13) |
| **Agent Mode** | Plugin-specific behavior profile passed to a core agent (§31.2) |
| **AppMap Hash** | SHA256 fingerprint for cache invalidation and cost control (§32.4) |

---

## Appendix A: Implementation Checklist

- [x] Monorepo scaffold (Python venv, Alembic, FastAPI)
- [x] PostgreSQL schema + Alembic migrations (including `pipeline_runs`, `artifacts`, `credential_access_audit`)
- [x] Database indexes per §34 migration (`20260615114336_init`)
- [x] `aqa_shared` Python package (agent types, pipeline enums, Celery task names, SQLAlchemy models)
- [x] Python Celery app + 6 tasks wired to agents (`workers/celery_app/`)
- [x] FastAPI shell + `GET /health` (DB + Redis checks)
- [x] Python logging (stdlib)
- [x] Artifact storage folder structure (`artifacts/`)
- [x] FastAPI Celery enqueue (`apps/api/aqa_api/services/celery_enqueue.py`) — business routes (§16) remain Phase 1+
- [x] SSE pipeline progress (`GET /pipeline-runs/:id/stream`)
- [x] `GET /metrics` (Prometheus) — Day 10 scaffold
- [ ] Playwright discovery with crawl rules (§15) via DiscoveryAgent + DiscoveryWorker
- [ ] TestDesignAgent + ScriptGenerationAgent + ValidationModule + HealingAgent
- [ ] PlaywrightExecutor with traces, videos, retry policy
- [ ] Next.js dashboard with metrics and health score
- [ ] ReportingWorker (Allure) + IntelligenceAgent stub
- [ ] GitHub Actions CI
- [ ] Jira integration
- [ ] UI Plugin with agent modes (§8.4)
- [ ] Benchmark validation (Juice Shop)
- [ ] Definition of Done verification (§5)
- [x] Five core agent stubs (`packages/agents/aqa_agents/`) — Discovery, TestDesign, ScriptGeneration, Intelligence, Healing
- [ ] OpenAI cost controls per §32 (budgets, AppMap cache, token tracking)
- [ ] Versioning rules per §33 (script versions, AppMap artifacts, pipeline linkage)
- [x] README / runbook — Day 10 scaffold (`README.md`)

---

## Appendix B: Week 1–2 Scaffold Progress

Reference: `docs/WEEK-01-02-SCAFFOLD-GUIDE.md`

| Day | Scope | Status |
|-----|--------|--------|
| Day 1 | Monorepo bootstrap, git, `.env`, artifacts | **Complete** |
| Day 2 | `aqa_shared` types, queues | **Complete** |
| — | Celery migration (Python workers + shared task names) | **Complete** |
| Day 3 | SQLAlchemy models — 11 tables, 9 enums | **Complete** |
| Day 4 | Indexes + Alembic baseline migration | **Complete** |
| Day 5 | Local infra (native Postgres + native Redis) | **Complete** |
| Day 6 | FastAPI + `GET /health` | **Complete** |
| Day 7 | Celery task enqueue from API | **Complete** |
| Day 8 | Five core agent stubs (LangGraph Python) | **Complete** |
| Day 9 | Celery worker → agent integration | **Complete** |
| Day 10 | ValidationModule skeleton + `/metrics` + integration gate | **Complete** |

**Verified commands (as of 2026-06-16):** `pnpm verify:week1-2` (exit gate), `pnpm verify:smoke`, `pnpm verify:e2e-celery`, `pnpm verify:shared`, `pnpm verify:redis`, `pnpm verify:db`, `pnpm verify:agents`, `pnpm verify:worker-agents`, `pnpm verify:validation`, `pnpm verify:metrics`, `pnpm verify:celery`, `curl http://localhost:3001/health`, `curl http://localhost:3001/metrics`.

**Local infrastructure:** PostgreSQL 17 + Redis 7 (both native/local). Docker full stack in Phase 2 — see §25.3 and `docker/docker-compose.full.yml`.

---

## Appendix C: Week 3–4 Scaffold Progress

Reference: [WEEK-03-04-SCAFFOLD-GUIDE.md](./WEEK-03-04-SCAFFOLD-GUIDE.md)

| Day | Scope | Status |
|-----|--------|--------|
| Day 11 | Application API (`POST/GET /apps`) | **Complete** |
| Day 12 | SSRF URL validation + `auth_config` encryption | **Complete** |
| Day 13 | `pipeline_runs` + `POST .../discover` | **Complete** |
| Day 14 | SSE live progress stream | **Complete** |
| Day 15 | DiscoveryWorker scaffold + Playwright | **Complete** |
| Day 16 | Crawl engine (BFS, scope limits) | **Complete** |
| Day 17 | Safety exclusions + robots.txt + SPA | **Complete** |
| Day 18 | Auth (form login, cookies) + credential audit | **Complete** |
| Day 19 | Element extraction + DB persistence | **Complete** |
| Day 20 | DiscoveryAgent flows + AppMap API + smoke gate | **Complete** |

**Prerequisite:** Week 1–2 complete — `pnpm verify:smoke` passes.

---

## Appendix D: Week 5–6 Scaffold Progress

Reference: [WEEK-05-06-SCAFFOLD-GUIDE.md](./WEEK-05-06-SCAFFOLD-GUIDE.md)

| Day | Scope | Status |
|-----|--------|--------|
| Day 21 | `POST .../generate-tests` + pipeline orchestration | **Not started** |
| Day 22 | TestDesignAgent rule-based templates | **Not started** |
| Day 23 | TestDesignAgent LLM gap-fill + TestCaseSchema validation | **Not started** |
| Day 24 | Persist `test_cases` + `GET .../test-cases` | **Not started** |
| Day 25 | ScriptGenerationAgent plan step + Celery design wire | **Not started** |
| Day 26 | Playwright TypeScript emit | **Not started** |
| Day 27 | ValidationModule real (`tsc`, locator policy) | **Not started** |
| Day 28 | HealingAgent codegen loop | **Not started** |
| Day 29 | Persist `test_scripts` + artifacts + Celery wire | **Not started** |
| Day 30 | `verify:smoke-generation` + sprint exit gate | **Not started** |

**Prerequisite:** Week 3–4 complete — `pnpm verify:smoke-discovery` passes.
