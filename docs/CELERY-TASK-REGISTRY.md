# Celery Task Registry

Producer (FastAPI) → Redis broker → Python Celery workers.

Task names are defined in `packages/aqa_shared/aqa_shared/celery/task_names.py` and re-exported from `workers/celery_app/aqa_celery/task_names.py`.

| Queue | Celery task | API helper | Consumer worker | Agent / worker |
|-------|-------------|------------|-----------------|----------------|
| `discover` | `aqa.tasks.discover` | `enqueue_discovery_task` | `pnpm dev:worker:discovery` | **DiscoveryAgent** |
| `design` | `aqa.tasks.design` | `enqueue_design_task` | `pnpm dev:worker:discovery` | **TestDesignAgent** |
| `generate-scripts` | `aqa.tasks.generate_scripts` | `enqueue_generate_scripts_task` | `pnpm dev:worker:discovery` | **ScriptGenerationAgent** |
| `execute` | `aqa.tasks.execute` | `enqueue_execute_task` | `pnpm dev:worker:executor` | PlaywrightExecutor (stub) |
| `report` | `aqa.tasks.report` | `enqueue_report_task` | `pnpm dev:worker:report` | ReportingWorker (stub) |
| `analyze` | `aqa.tasks.analyze` | `enqueue_analyze_task` | `pnpm dev:worker:report` | **IntelligenceAgent** |

**Worker integration:** `workers/celery_app/aqa_celery/agent_runner.py` maps tasks → agents. Verify with `pnpm verify:worker-agents`.

**Retry policy:** Workers enforce `max_retries: 3` with exponential backoff (`workers/celery_app/aqa_celery/config.py`). API logs the same policy via `CELERY_ENQUEUE_RETRY` in `apps/api/aqa_api/services/celery_enqueue.py`.

**Dev queue stats:** `GET /api/v1/queues/stats` (development only).

**Metrics:** `GET /metrics` — Prometheus default process metrics + `aqa_queue_depth` gauge (Day 10).

**Validation:** `packages/aqa_shared/aqa_shared/validation/` — `ValidationModule` JSON Schema gate + stubs (Day 10).
