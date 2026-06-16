# Week 1–2 Scaffold Guide — Day-by-Day Implementation Playbook

| Field | Value |
|-------|-------|
| **Phase** | Phase 1, Weeks 1–2 |
| **Goal** | Runnable monorepo skeleton: DB, queue, API health check, agent/worker stubs |
| **Reference spec** | [SPEC.md](./SPEC.md) v2.3.0 |
| **Implementation plan** | Platform Implementation Plan (Cursor plan) |
| **Status** | **Complete** — Week 1–2 scaffold (Days 1–10) |
| **Duration** | 10 working days (2 weeks) |

---

## 1. What this sprint delivers

> **Stack (2026-06-16):** Backend is **Python 3.11+** — **FastAPI** orchestration API, **SQLAlchemy + Alembic** for PostgreSQL, **Celery** workers. Local dev uses **native PostgreSQL + native Redis** (not Docker). Full Docker stack is Phase 2 / CI — see `docker/docker-compose.full.yml`.

By end of Day 10 you should have:

- A **Python monorepo layout** with `apps/api/` (FastAPI), `packages/aqa_shared/`, `workers/`, `alembic/`, `docker/`
- **PostgreSQL schema** (SQLAlchemy + Alembic) for all Phase 1 tables + indexes (SPEC §14, §34)
- **Native Redis 7+** on localhost for Celery (no Docker Redis in Phase 1 local dev)
- **FastAPI** with `GET /health`, `GET /metrics`, Python logging
- **Celery** queue definitions wired to Redis
- **5 core agent stubs** (LangGraph Python shells, mock responses)
- **3 worker stubs** (job consumers, log-only handlers)
- **ValidationModule skeleton** (interfaces + placeholder validators)
- **Exit verification:** native Postgres + native Redis running + API returns `{ "status": "ok" }` + migrations apply

**Explicitly NOT in this sprint:** Real crawling, LLM calls, Playwright execution, dashboard UI (Week 9–10), business APIs beyond health/metrics.

---

## 2. Tooling reference (install before Day 1)

### 2.1 Required tools

| Tool | Minimum version | Purpose | Install (Windows) | Official docs |
|------|-----------------|---------|-------------------|---------------|
| **Python** | 3.11+ | FastAPI API, Celery workers, agents, Alembic | [python.org](https://www.python.org/) or `brew install python@3.11` | https://docs.python.org/3/ |
| **pnpm** | 9.x | Convenience scripts (`dev:api`, `verify:*`) | `npm install -g pnpm` | https://pnpm.io/installation |
| **Git** | 2.x | Version control | [git-scm.com](https://git-scm.com/) | https://git-scm.com/doc |
| **Redis** | 7+ | Celery broker/backend (native local install) | `brew install redis` | https://redis.io/docs/ |
| **Docker Desktop** | 4.x | Phase 2 / CI full stack only (optional in Phase 1) | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) | https://docs.docker.com/desktop/ |
| **Python** | 3.11+ | Celery workers | [python.org](https://www.python.org/) or `brew install python@3.11` | https://docs.python.org/3/ |
| **VS Code / Cursor** | Latest | IDE | — | — |

### 2.2 Verify installations (run on Day 1)

```powershell
python3 --version  # expect 3.11+
redis-cli ping     # expect PONG (local Redis must be running)
pnpm -v            # optional script runner
git --version
docker -v          # optional until Phase 2 CI
docker compose version
```

### 2.3 Core Python packages (installed via `requirements.txt` during sprint)

| Package | Used in | Purpose |
|---------|---------|---------|
| `fastapi` | `apps/api` | HTTP API (SPEC §16) |
| `uvicorn` | `apps/api` | ASGI server |
| `sqlalchemy` | `packages/aqa_shared` | ORM models |
| `alembic` | Root | DB migrations |
| `psycopg2-binary` | Root | PostgreSQL driver |
| `pydantic` / `pydantic-settings` | `apps/api`, `aqa_shared` | Settings + payloads |
| `redis` | `apps/api` | Redis health check + queue stats |
| `langgraph` | `packages/agents` | Agent graph stubs (Day 8+) |
| `celery[redis]` | `workers/celery_app`, `apps/api` | Task queue (SPEC §19) |
| `python-dotenv` | All Python apps | Environment variables |
| `langgraph` | Agent packages (Day 8+) | Agent graphs |

### 2.4 Infrastructure services

**Phase 1 local dev (native — no Docker):**

| Service | How to run | Port | Purpose |
|---------|------------|------|---------|
| **PostgreSQL** | `brew services start postgresql@17` | 5432 | Primary database |
| **Redis** | `brew services start redis` (or your local install) | 6379 | Celery broker/backend |

**Phase 2 / CI (Docker — `docker/docker-compose.full.yml`):**

| Service | Image | Port |
|---------|-------|------|
| **postgres** | `postgres:15-alpine` | 5432 |
| **redis** | `redis:7-alpine` | 6379 |

### 2.5 Environment variables (`.env.example`)

```env
# Database
DATABASE_URL=postgresql://aqa:aqa@localhost:5432/autonomous_qa

# Redis / Celery (local Redis — not Docker in Phase 1)
REDIS_URL=redis://localhost:6379
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# API
API_PORT=3001
NODE_ENV=development
LOG_LEVEL=info

# Artifacts (local)
ARTIFACT_STORAGE_PATH=./artifacts

# LLM (not used in Week 1–2 stubs)
OPENAI_API_KEY=
GEMINI_API_KEY=
LLM_BUDGET_PER_PIPELINE=2.00
LLM_BUDGET_PER_APP_DAILY=10.00

# Encryption (Week 3+; define now)
ENCRYPTION_KEY=
```

---

## 3. Target folder structure (end of Day 10)

```
AI Autonomous QA Platform/
├── docs/
│   ├── SPEC.md
│   ├── WEEK-01-02-SCAFFOLD-GUIDE.md
│   ├── WEEK-03-04-SCAFFOLD-GUIDE.md
│   └── CELERY-TASK-REGISTRY.md
├── apps/
│   └── api/
│       ├── pyproject.toml
│       └── aqa_api/
│           ├── main.py
│           ├── config.py
│           ├── routers/
│           │   ├── health.py
│           │   ├── metrics.py
│           │   └── queues.py
│           └── services/
│               └── celery_enqueue.py
├── packages/
│   ├── aqa_shared/
│   │   └── aqa_shared/
│   │       ├── db/                    # SQLAlchemy models + session
│   │       ├── types/                 # AgentContext, AgentResult
│   │       ├── celery/                # task names, payload types
│   │       ├── queue/                 # queue name constants
│   │       └── validation/            # ValidationModule (Day 10)
│   ├── agents/
│   │   └── aqa_agents/                # 5 core agent stubs (LangGraph)
│   └── plugins/
│       └── ui/                        # Empty shell; wired in Week 9
├── workers/
│   └── celery_app/
│       └── aqa_celery/
│           ├── app.py
│           ├── config.py
│           ├── agent_runner.py        # Day 9 — tasks → agents
│           └── tasks/__init__.py
├── alembic/                           # DB migrations (replaces Prisma)
│   ├── env.py
│   ├── versions/
│   └── sql/
├── docker/
│   ├── docker-compose.yml             # Phase 1 stub (no services)
│   └── docker-compose.full.yml        # Phase 2 / CI full stack
├── scripts/
│   ├── verify_*.py
│   └── verify_week1_2.py              # Week 1–2 exit gate
├── artifacts/                         # gitignored
│   ├── screenshots/
│   ├── traces/
│   ├── videos/
│   ├── reports/
│   ├── appmaps/
│   └── generated-scripts/
├── .github/                           # Placeholder until Week 9 CI
├── .venv/                             # Python virtualenv (gitignored)
├── requirements.txt
├── alembic.ini
├── pnpm-workspace.yaml
├── package.json
├── .env.example
├── .gitignore
└── README.md
```

---

## 4. Day-by-day plan

### Day 1 — Environment, git, monorepo bootstrap

**Objective:** Empty repo becomes a pnpm workspace with root config.

| Step | Action | Tools |
|------|--------|-------|
| 1 | Verify Node, pnpm, Docker, Git (§2.2) | CLI |
| 2 | `git init` in project root | Git |
| 3 | Create `.gitignore`: `node_modules`, `.env`, `artifacts/`, `dist/`, `.next/` | Editor |
| 4 | Create root `package.json` with `"private": true`, scripts: `dev:api`, `db:migrate`, `verify:*` | pnpm |
| 5 | Create `pnpm-workspace.yaml` listing `apps/*`, `packages/**`, `workers/*` | pnpm |
| 6 | Create `requirements.txt` + `pnpm setup:python` for editable Python packages | pip |
| 7 | Copy `.env.example` → `.env` (local only, never commit) | dotenv |
| 8 | Create empty `artifacts/` subfolders (§3) | Filesystem |

**Commands (reference — run when implementing):**

```powershell
cd "d:\AI Autonomous QA Platform"
git init
pnpm init
# create pnpm-workspace.yaml and tsconfig.base.json manually
mkdir artifacts\screenshots, artifacts\traces, artifacts\videos, artifacts\reports, artifacts\appmaps, artifacts\generated-scripts
```

**End-of-day check:**
- [x] `pnpm-workspace.yaml` exists
- [x] `.gitignore` excludes `.env` and `artifacts/`
- [x] `artifacts/` subfolders exist
- [x] `packages/plugins/ui/` placeholder exists
- [x] `.github/` placeholder exists

---

### Day 2 — Shared package (`aqa_shared`)

**Objective:** Python `aqa_shared` package with core types and queue name constants.

| Step | Action | Tools |
|------|--------|-------|
| 1 | Create `packages/aqa_shared/pyproject.toml` | pip / setuptools |
| 2 | Define `AgentContext`, `AgentResult`, `CoreAgent` (Pydantic / Protocol) | Python |
| 3 | Define pipeline enums: `PipelineStatus`, `PipelineStage`, queue names | Python |
| 4 | Export Celery task constants + queue routing map | Python |
| 5 | Add `scripts/verify_shared.py` + `pnpm verify:shared` | Python |
| 6 | Wire editable installs via root `requirements.txt` | pip |

**Key types to define:**

```python
# packages/aqa_shared/aqa_shared/types/agent.py
CoreAgentId = Literal["discovery", "test-design", "script-generation", "intelligence", "healing"]

class AgentContext(BaseModel):
    pipeline_run_id: str  # alias pipelineRunId
    application_id: str   # alias applicationId
    plugin_id: str        # alias pluginId
    mode: str
    token_budget_remaining: int  # alias tokenBudgetRemaining
    app_map: Any | None = None   # alias appMap
    prior_errors: list[str] | None = None  # alias priorErrors
```

**End-of-day check:**
- [x] `pnpm setup:python` succeeds
- [x] `aqa_shared` importable (`pnpm verify:shared`)

---

### Day 3 — SQLAlchemy models (tables)

**Objective:** Full Phase 1 data model in `packages/aqa_shared/aqa_shared/db/models.py` (SPEC §14.2).

| Step | Action | Tools |
|------|--------|-------|
| 1 | Create `packages/aqa_shared` with SQLAlchemy 2.0 models | SQLAlchemy |
| 2 | Define all 11 tables + 9 enums | Python |
| 3 | Create `aqa_shared/db/session.py` — engine + session factory | SQLAlchemy |
| 4 | Add relations + `ondelete` cascades | SQLAlchemy |

**Tables checklist (must all exist):**

- [x] `applications` (incl. `seed_urls`, `config_version`, health fields)
- [x] `pages`, `elements`, `flows`
- [x] `test_cases` (incl. `pipeline_run_id`)
- [x] `test_scripts` (incl. `version`, unique `[testcase_id, version]`)
- [x] `test_runs`, `results`
- [x] `pipeline_runs` (master orchestration: `llm_tokens_used`, `cost_estimate`)
- [x] `artifacts`
- [x] `credential_access_audit`

**End-of-day check:**
- [x] Models import without error
- [x] `pnpm verify:shared` passes

---

### Day 4 — Database indexes + Alembic baseline migration

**Objective:** Apply SPEC §34 indexes; database creatable from scratch via Alembic.

| Step | Action | Tools |
|------|--------|-------|
| 1 | Initialize Alembic: `alembic.ini`, `alembic/env.py` | Alembic |
| 2 | Create `alembic/versions/20260615114336_init.py` from Prisma baseline SQL | Alembic + SQL |
| 3 | Include partial indexes in `alembic/sql/20260615114336_init.sql` | SQL |
| 4 | Fresh DB: `pnpm db:migrate` → `alembic upgrade head` | Alembic |
| 5 | Existing Prisma DB: `pnpm db:stamp` → `alembic stamp head` | Alembic |

**Critical indexes (SPEC §34 — must exist after migration):**

| Table | Index | Notes |
|-------|-------|-------|
| `pipeline_runs` | `(application_id, status) WHERE status IN ('pending','running')` | Active pipeline check |
| `pages` | `UNIQUE (app_id, url)` | Crawl dedupe |
| `test_scripts` | `UNIQUE (testcase_id, version)` | Versioning |
| `test_runs` | `(app_id, started_at DESC)` | Dashboard history |

**Partial index example (raw SQL in migration):**

```sql
CREATE INDEX idx_pipeline_runs_active ON pipeline_runs (application_id, status)
  WHERE status IN ('pending', 'running');
```

**End-of-day check:**
- [x] `alembic current` shows `20260615114336`
- [x] Can connect via `DATABASE_URL` from `.env`
- [x] `pnpm verify:db` passes

---

### Day 5 — Local infrastructure (native Postgres + native Redis)

**Objective:** PostgreSQL and Redis run on the host — no Docker required for Phase 1 daily dev.

| Step | Action | Tools |
|------|--------|-------|
| 1 | Ensure PostgreSQL 17 is running (`brew services start postgresql@17`) | Homebrew |
| 2 | Ensure **local Redis** is running (`brew services start redis` or your existing install) | Homebrew / local |
| 3 | Verify `redis-cli ping` → `PONG` and `DATABASE_URL` in `.env` | CLI |
| 4 | Keep `docker/docker-compose.yml` as Phase 1 stub (no services) | Docker |
| 5 | Full stack for CI documented in `docker/docker-compose.full.yml` (Phase 2) | Docker Compose |

**docker-compose.yml (Phase 1 — stub only):**

```yaml
# Local dev: native PostgreSQL + native Redis. No Docker services.
services: {}
```

**docker-compose.full.yml (Phase 2 / CI — Postgres + Redis in Docker):**

```yaml
services:
  postgres:
    image: postgres:15-alpine
    # ...
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
```

**End-of-day check:**
- [x] `redis-cli ping` → `PONG`
- [x] PostgreSQL accepts connections on `5432`
- [x] SQLAlchemy connects and Alembic stamped/applied

---

### Day 6 — FastAPI shell

**Objective:** Running HTTP server with health check and structured logging.

| Step | Action | Tools |
|------|--------|-------|
| 1 | Create `apps/api` Python package `aqa-api` | pip / setuptools |
| 2 | Dependencies: `fastapi`, `uvicorn`, `pydantic-settings`, `redis`, `aqa-shared` | pip |
| 3 | `aqa_api/config.py` — validate `DATABASE_URL`, `REDIS_URL`, `API_PORT` | pydantic-settings |
| 4 | `GET /health` — check DB (`SELECT 1`) + Redis (`PING`) | FastAPI, SQLAlchemy, redis |
| 5 | Root script: `pnpm dev:api` → `uvicorn aqa_api.main:app --reload --port 3001` | uvicorn |

**Health response shape:**

```json
{
  "status": "ok",
  "db": "ok",
  "redis": "ok",
  "version": "0.1.0"
}
```

**End-of-day check:**
- [x] `pnpm dev:api` starts without errors
- [x] `curl http://localhost:3001/health` returns 200
- [x] Structured logging via stdlib `logging`

---

### Day 7 — Celery task enqueue (API)

**Objective:** FastAPI can enqueue Celery tasks via Python Celery `apply_async`; workers ready on Day 9.

| Step | Action | Tools |
|------|--------|-------|
| 1 | `aqa_api/services/celery_enqueue.py` — enqueue helpers using `aqa_celery.tasks` | Celery (Python) |
| 2 | Export helpers: `enqueue_discovery_task(payload)`, etc. | Python |
| 3 | Configure retries: `max_retries: 3`, exponential backoff (mirrors worker config) | Celery |
| 4 | Add optional `GET /api/v1/queues/stats` (dev only) — Redis `LLEN` per queue | FastAPI, redis |
| 5 | Document task → agent/worker mapping (see §5 below) | Markdown |

**Task registry (SPEC §19):**

| Queue | Celery task | Producer | Consumer (Day 9) | Future agent/worker |
|-------|-------------|----------|------------------|---------------------|
| `discover` | `aqa.tasks.discover` | API | celery worker `-Q discover,design,generate-scripts` | DiscoveryAgent |
| `design` | `aqa.tasks.design` | API | celery worker (discovery queues) | TestDesignAgent |
| `generate-scripts` | `aqa.tasks.generate_scripts` | API | celery worker (discovery queues) | ScriptGenerationAgent |
| `execute` | `aqa.tasks.execute` | API | celery worker `-Q execute` | PlaywrightExecutor |
| `report` | `aqa.tasks.report` | API | celery worker `-Q report,analyze` | ReportingWorker |
| `analyze` | `aqa.tasks.analyze` | API | celery worker (report queues) | IntelligenceAgent |

**End-of-day check:**
- [x] API connects to Redis/Celery broker without error on startup
- [x] `pnpm verify:celery` returns async result id
- [x] `/health` still passes with Celery client initialized

---

### Day 8 — Five core agent stubs

**Objective:** Each agent package exports a `run()` that returns mock data; LangGraph-ready layout (Python).

| Step | Action | Tools |
|------|--------|-------|
| 1 | Create `packages/agents/` (`aqa-agents` Python package) | pip / setuptools |
| 2 | Depends on `aqa-shared`, `langgraph` (graph stub per agent) | Python |
| 3 | **DiscoveryAgent** — `run(ctx)` returns mock `{ pages: [], flows: [] }` | Python |
| 4 | **TestDesignAgent** — returns mock `{ testCases: [] }` | Python |
| 5 | **ScriptGenerationAgent** — returns mock `{ code: "// stub" }` | Python |
| 6 | **IntelligenceAgent** — returns mock `{ coverage: 0 }` (no LLM) | Python |
| 7 | **HealingAgent** — returns input unchanged (pass-through stub) | Python |
| 8 | Each agent logs `{ agentId, mode, pipelineRunId }` via stdlib logging | Python |
| 9 | Export all from `aqa_agents` barrel (`from aqa_agents import ...`) | Python |

**Agent stub contract (every agent must implement):**

```python
class AgentResult(BaseModel):
    output: Any
    tokens_used: int = 0       # alias tokensUsed
    cost_estimate: float = 0.0 # alias costEstimate
    validation_passed: bool = True  # alias validationPassed
```

**End-of-day check:**
- [x] Each agent callable from `pnpm verify:agents`
- [x] All 5 agents import without error
- [x] No OpenAI API key required yet

---

### Day 9 — Celery worker → agent integration

**Objective:** Celery tasks invoke Day 8 agent stubs; execute/report remain non-agent stubs.

| Step | Action | Tools |
|------|--------|-------|
| 1 | Add `aqa-agents` dependency to `workers/celery_app` | pip |
| 2 | `aqa_celery/agent_runner.py` — payload → `AgentContext`, invoke agent | Python |
| 3 | Wire `discover`, `design`, `generate_scripts`, `analyze` tasks to agents | Celery |
| 4 | Keep `execute`, `report` as log-only stubs (Playwright/reporting later) | Celery |
| 5 | Return `{ ok, pipelineRunId, agentId, output, tokensUsed, ... }` | Python |
| 6 | Worker scripts unchanged: `dev:worker:discovery`, `executor`, `report` | pnpm |
| 7 | Verify: `pnpm verify:worker-agents` | Python |

**Worker rules (SPEC §31):**
- Workers **must not** call OpenAI or any LLM
- Workers **may** update `pipeline_runs` via SQLAlchemy (optional — not in Day 9 stub)

**End-of-day check:**
- [x] `pnpm verify:worker-agents` passes (direct task.run)
- [x] Enqueue via API → worker consumes → SUCCESS with agent output (`pnpm verify:e2e-celery`)
- [x] `execute` / `report` still return `{ ok: true, stub: true }`

---

### Day 10 — ValidationModule skeleton + metrics + integration gate

**Objective:** Validation scaffolding in place; full stack smoke test; README.

| Step | Action | Tools |
|------|--------|-------|
| 1 | `packages/aqa_shared/aqa_shared/validation/schemas/test-case.schema.json` — JSON Schema per SPEC §13.1 | jsonschema |
| 2 | `validate_test_case(data)` — JSON Schema validate; return `ValidationResult` | jsonschema |
| 3 | `validate_script(code)` — placeholder: always `{ valid: true }`; Week 5–6 adds `tsc` | Python |
| 4 | `validate_locators(code)` — placeholder: always `{ valid: true }`; Week 5–6 adds AST rules | Python |
| 5 | Export `ValidationModule` class with all four functions | Python |
| 6 | `GET /metrics` — prometheus-client default metrics + `aqa_queue_depth` gauge | prometheus-client |
| 7 | `pnpm verify:week1-2` — smoke + E2E Celery (§7) | Script |
| 8 | Write `README.md`: prerequisites, migrate, dev commands | Markdown |

**ValidationModule skeleton API:**

```python
class ValidationModule:
    validate_test_case(data) -> ValidationResult      # JSON Schema
    validate_script(code) -> ValidationResult         # stub
    validate_locators(code) -> ValidationResult     # stub
    validate_execution_plan(plan) -> ValidationResult  # stub
```

**End-of-day check (sprint exit criteria):**
- [x] All Day 1–9 checks still pass
- [x] `/health` → 200, `/metrics` → Prometheus text
- [x] Agents + workers + ValidationModule import cleanly
- [x] README documents local setup
- [x] Ready for Week 3–4 (DiscoveryAgent + DiscoveryWorker)

---

## 5. Queue → agent → worker mapping (reference)

```mermaid
flowchart LR
  API[FastAPI]
  Q[Celery + Redis]
  DA[DiscoveryAgent stub]
  TDA[TestDesignAgent stub]
  SGA[ScriptGenerationAgent stub]
  IA[IntelligenceAgent stub]
  DW[Celery Worker: discovery queues]
  PE[Celery Worker: execute stub]
  RW[Celery Worker: report/analyze]

  API --> Q
  Q --> DW
  DW --> DA
  DW --> TDA
  DW --> SGA
  Q --> PE
  Q --> RW
  RW --> IA
```

Day 9 wires Celery tasks → agent stubs. `execute` / `report` remain log-only stubs until Week 7+.

---

## 6. SQLAlchemy model quick reference

| Model | Primary key | Key FKs |
|-------|-------------|---------|
| Application | `app_id` | — |
| Page | `page_id` | `app_id` |
| Element | `element_id` | `page_id` |
| Flow | `flow_id` | `app_id` |
| TestCase | `testcase_id` | `app_id`, `pipeline_run_id` |
| TestScript | `script_id` | `testcase_id` |
| TestRun | `run_id` | `app_id`, `pipeline_run_id` |
| Result | `result_id` | `run_id`, `script_id` |
| PipelineRun | `id` | `application_id` |
| Artifact | `id` | `run_id`, `pipeline_run_id` |
| CredentialAccessAudit | `audit_id` | `app_id`, `pipeline_run_id` |

Full column definitions: SPEC §14.2. Index definitions: SPEC §34.

---

## 7. Integration smoke test (Day 10)

Run in order after all services are up:

```powershell
# Terminal 1 — ensure native infra is running
brew services start postgresql@17
brew services start redis
redis-cli ping   # PONG

# Terminal 2 — migrations
pnpm db:migrate

# Terminal 3 — API
pnpm dev:api

# Terminal 4 — workers (separate terminals or use concurrently)
pnpm dev:worker:discovery
pnpm dev:worker:executor
pnpm dev:worker:report

# Verify health
curl http://localhost:3001/health

# Verify metrics
curl http://localhost:3001/metrics

# Automated Week 1–2 exit gate (smoke + E2E with temporary worker)
pnpm verify:week1-2

# Or run separately:
pnpm verify:smoke
pnpm dev:worker:celery   # separate terminal
pnpm verify:e2e-celery
```

**Expected results:**

| Check | Expected |
|-------|----------|
| `redis-cli ping` | `PONG` (local Redis, not Docker) |
| PostgreSQL | Accepts connections on `5432` |
| `/health` | `{ "status": "ok", "db": "ok", "redis": "ok" }` |
| `/metrics` | Contains `python_info` and `aqa_queue_depth` metrics |
| Worker logs | Job received and completed |
| DB schema | 11 tables via `pnpm verify:db` / Alembic |

---

## 8. Root `package.json` scripts (target)

| Script | Command | When |
|--------|---------|------|
| `setup:python` | `python3 -m venv .venv && pip install -r requirements.txt` | Day 1+ |
| `dev:api` | `uvicorn aqa_api.main:app --reload --port 3001` | Day 6+ |
| `dev:worker:celery` | `celery -A aqa_celery.app worker -Q discover,design,generate-scripts,execute,report,analyze` | All queues (dev) |
| `dev:worker:discovery` | `celery ... worker -Q discover,design,generate-scripts` | Day 9+ |
| `dev:worker:executor` | `celery ... worker -Q execute` | Day 9+ |
| `dev:worker:report` | `celery ... worker -Q report,analyze` | Day 9+ |
| `db:migrate` | `alembic upgrade head` | Day 4+ |
| `db:stamp` | `alembic stamp head` | Existing DB |
| `db:revision` | `alembic revision --autogenerate` | After model change |
| `verify:shared` | `scripts/verify_shared.py` | Day 2+ |
| `verify:db` | `scripts/verify_db.py` | Day 4+ |
| `verify:redis` | `scripts/verify_redis.py` | Day 5+ |
| `verify:agents` | `scripts/verify_agents.py` | Day 8+ |
| `verify:worker-agents` | `scripts/verify_worker_agents.py` | Day 9+ |
| `verify:celery` | `scripts/verify_celery_enqueue.py` | Day 7+ |
| `verify:validation` | `scripts/verify_validation.py` | Day 10 |
| `verify:metrics` | `scripts/verify_metrics.py` | Day 10 |
| `verify:smoke` | `scripts/verify_smoke.py` | Day 10 |
| `verify:e2e-celery` | `scripts/verify_e2e_celery.py` | Day 9+ (worker required) |
| `verify:week1-2` | `scripts/verify_week1_2.py` | **Week 1–2 exit gate** |

---

## 9. Risks and mitigations (Week 1–2)

| Risk | Mitigation |
|------|------------|
| Docker port conflicts (5432/6379) | Change compose ports; update `.env` |
| Prisma partial indexes not supported in schema DSL | Use raw SQL in migration file |
| Windows path issues with Playwright (later) | Use WSL2 or Docker for workers (Week 7+) |
| pnpm workspace hoisting confusion | Explicit `dependencies` in each package.json |
| Scope creep into Week 3 work | Do not implement crawl, LLM, or UI in this sprint |

---

## 10. Handoff to Week 3–4

When this sprint is complete, the next sprint implements:

1. **DiscoveryWorker** — real Playwright crawl (SPEC §15)
2. **DiscoveryAgent** — LLM flow structuring (mode `ui`)
3. **Application APIs** — `POST /api/v1/apps`, discover, appmap, SSE

Agents and workers already have package boundaries; Week 3 replaces stub `run()` bodies and worker handlers.

**See:** [WEEK-03-04-SCAFFOLD-GUIDE.md](./WEEK-03-04-SCAFFOLD-GUIDE.md) for the day-by-day plan (Days 11–20).

---

## 11. Document changelog

| Date | Change |
|------|--------|
| 2026-06-12 | Initial day-wise scaffold guide created |
| 2026-06-16 | Updated §3 to Python layout; added `verify:week1-2`; marked Days 1–10 complete |
