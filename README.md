# AI Autonomous QA Platform

Autonomous URL → discovery → test design → script generation → Playwright execution → reporting pipeline.

**Stack (Week 1–2 scaffold):** Python 3.11+, FastAPI, SQLAlchemy + Alembic, Celery + Redis, LangGraph agent stubs, PostgreSQL 17.

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.11+ | `python3 --version` |
| pnpm | 9.x | Convenience scripts only |
| PostgreSQL | 17 | Native/local (Homebrew recommended) |
| Redis | 7+ | Native/local (Homebrew recommended) |

Optional for CI / Phase 2: Docker (`docker/docker-compose.full.yml`).

## Quick start

```bash
# 1. Clone and enter repo
cd "AI Autonomous QA Platform"

# 2. Python virtualenv + editable packages
pnpm setup:python

# 3. Environment
cp .env.example .env
# Edit DATABASE_URL if needed (default: postgresql://aqa:aqa@localhost:5432/autonomous_qa)

# 4. Start infrastructure (macOS Homebrew example)
brew services start postgresql@17
brew services start redis
redis-cli ping   # expect PONG

# 5. Create DB user/db (first time only)
# psql postgres -c "CREATE USER aqa WITH PASSWORD 'aqa';"
# psql postgres -c "CREATE DATABASE autonomous_qa OWNER aqa;"

# 6. Run migrations
pnpm db:migrate
```

## Development

Open **four terminals** (or use a process manager):

```bash
# Terminal 1 — API (port 3001)
pnpm dev:api

# Terminal 2 — Celery worker (all queues)
pnpm dev:worker:celery

# Or split workers:
pnpm dev:worker:discovery   # discover, design, generate-scripts
pnpm dev:worker:executor    # execute
pnpm dev:worker:report      # report, analyze
```

### Health and metrics

```bash
curl http://localhost:3001/health
curl http://localhost:3001/metrics
curl http://localhost:3001/api/v1/queues/stats   # dev only
```

## Verification

Run after setup (API optional for most; worker required for E2E):

```bash
pnpm verify:shared
pnpm verify:redis
pnpm verify:db
pnpm verify:agents
pnpm verify:worker-agents
pnpm verify:validation      # Day 10 — ValidationModule
pnpm verify:metrics         # Day 10 — GET /metrics
pnpm verify:celery
pnpm verify:smoke           # Day 10 — full smoke (no worker)
pnpm verify:e2e-celery      # enqueue → worker → result (worker must be running)
pnpm verify:week1-2         # Week 1–2 exit gate (smoke + E2E with temp worker)
```

## Project layout

```
apps/api/              FastAPI orchestration API
packages/aqa_shared/   Enums, Celery constants, SQLAlchemy models, ValidationModule
packages/agents/       Five LangGraph agent stubs
workers/celery_app/    Celery workers + agent_runner wiring
alembic/               Database migrations
docs/                  SPEC, scaffold guide, Phase 2 spec
scripts/               verify_* scripts
```

## Celery queues

| Queue | Task | Agent / handler |
|-------|------|-----------------|
| `discover` | `aqa.tasks.discover` | DiscoveryAgent |
| `design` | `aqa.tasks.design` | TestDesignAgent |
| `generate-scripts` | `aqa.tasks.generate_scripts` | ScriptGenerationAgent |
| `execute` | `aqa.tasks.execute` | Stub (Playwright in Phase 2) |
| `report` | `aqa.tasks.report` | Stub |
| `analyze` | `aqa.tasks.analyze` | IntelligenceAgent |

## ValidationModule (Day 10)

Deterministic validation gates in `packages/aqa_shared/aqa_shared/validation/`:

- `validate_test_case(data)` — JSON Schema (SPEC §13.1)
- `validate_script(code)` — stub (Week 5–6 adds `tsc`)
- `validate_locators(code)` — stub (Week 5–6 adds AST rules)
- `validate_execution_plan(plan)` — stub

## Documentation

- [SPEC.md](docs/SPEC.md) — full platform specification
- [WEEK-01-02-SCAFFOLD-GUIDE.md](docs/WEEK-01-02-SCAFFOLD-GUIDE.md) — Week 1–2 day-by-day plan (Days 1–10) ✅
- [WEEK-03-04-SCAFFOLD-GUIDE.md](docs/WEEK-03-04-SCAFFOLD-GUIDE.md) — Week 3–4 day-by-day plan (Days 11–20)
- [PHASE-2-SPEC.md](docs/PHASE-2-SPEC.md) — Phase 2 plugins and infrastructure
- [CELERY-TASK-REGISTRY.md](docs/CELERY-TASK-REGISTRY.md) — task → queue → agent mapping

## What's next (Week 3–4)

See [WEEK-03-04-SCAFFOLD-GUIDE.md](docs/WEEK-03-04-SCAFFOLD-GUIDE.md):

- Application APIs (`POST /api/v1/apps`, discover, appmap)
- DiscoveryWorker (Playwright crawl) + DiscoveryAgent flow structuring
- AppMap persistence + SSE pipeline progress

## License

Private — see repository owner.
