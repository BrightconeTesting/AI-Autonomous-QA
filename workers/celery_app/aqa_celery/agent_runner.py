"""Bridge Celery task payloads to Day 8 agent stubs."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from aqa_agents import (
    DiscoveryAgent,
    DiscoveryInput,
    IntelligenceAgent,
    IntelligenceInput,
    ScriptGenerationAgent,
    ScriptGenerationInput,
    TestDesignAgent,
    TestDesignInput,
)
from aqa_discovery.auth import AuthError
from aqa_discovery.types import CrawlHaltError, PageSnapshot
from aqa_discovery.worker import crawl_application
from aqa_shared.metrics import (
    aqa_cic_interactions_total,
    aqa_cic_safety_skips_total,
    aqa_cic_states_total,
    aqa_crawl_time_seconds,
)
from aqa_shared.sse import PipelineEventType, publish_pipeline_event
from aqa_shared.types.agent import AgentContext, AgentResult

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_BUDGET = 8000
DISCOVERY_STAGE = "discover"


def payload_to_context(payload: dict[str, Any]) -> AgentContext:
    return AgentContext(
        pipelineRunId=payload["pipelineRunId"],
        applicationId=payload["applicationId"],
        pluginId=payload.get("pluginId") or "ui",
        mode=payload.get("mode") or "ui",
        tokenBudgetRemaining=int(payload.get("tokenBudgetRemaining", DEFAULT_TOKEN_BUDGET)),
    )


def _serialize_output(output: Any) -> Any:
    if hasattr(output, "model_dump"):
        return output.model_dump()
    return output


def agent_result_to_task_result(
    agent_id: str,
    pipeline_run_id: str,
    result: AgentResult,
) -> dict[str, Any]:
    return {
        "ok": True,
        "pipelineRunId": pipeline_run_id,
        "agentId": agent_id,
        "output": _serialize_output(result.output),
        "tokensUsed": result.tokens_used,
        "costEstimate": result.cost_estimate,
        "validationPassed": result.validation_passed,
    }


def run_agent_task(
    task_name: str,
    agent_id: str,
    payload: dict[str, Any],
    agent_run: Callable[[AgentContext], AgentResult],
) -> dict[str, Any]:
    ctx = payload_to_context(payload)
    logger.info(
        "Celery agent task starting",
        extra={
            "task": task_name,
            "agentId": agent_id,
            "pipelineRunId": ctx.pipeline_run_id,
            "applicationId": ctx.application_id,
            "mode": ctx.mode,
        },
    )
    result = agent_run(ctx)
    task_result = agent_result_to_task_result(agent_id, ctx.pipeline_run_id, result)
    logger.info(
        "Celery agent task completed",
        extra={
            "task": task_name,
            "agentId": agent_id,
            "pipelineRunId": ctx.pipeline_run_id,
            "validationPassed": task_result["validationPassed"],
        },
    )
    return task_result


def _publish_stage_completed(pipeline_run_id: str, stage: str, duration_ms: int) -> None:
    publish_pipeline_event(
        pipeline_run_id,
        PipelineEventType.stage_completed,
        {"stage": stage, "duration_ms": duration_ms},
    )


def _publish_pipeline_completed(pipeline_run_id: str, *, status: str = "completed") -> None:
    publish_pipeline_event(
        pipeline_run_id,
        PipelineEventType.pipeline_completed,
        {"status": status},
    )


def _publish_stage_failed(pipeline_run_id: str, stage: str, error: str) -> None:
    publish_pipeline_event(
        pipeline_run_id,
        PipelineEventType.stage_failed,
        {"stage": stage, "error": error},
    )


def run_discovery(payload: dict[str, Any]) -> dict[str, Any]:
    agent = DiscoveryAgent()
    pipeline_run_id = payload["pipelineRunId"]
    application_id = payload["applicationId"]
    started = time.monotonic()
    snapshot: PageSnapshot | None = None
    crawl_result = None
    crawl_overrides = payload.get("crawlConfigOverrides")

    try:
        crawl_result = crawl_application(
            application_id,
            crawl_overrides=crawl_overrides,
            pipeline_run_id=pipeline_run_id,
            persist=True,
        )
        if crawl_result.pages:
            snapshot = crawl_result.pages[0]
        if crawl_result.halted:
            _publish_stage_failed(
                pipeline_run_id,
                DISCOVERY_STAGE,
                crawl_result.halt_reason or "Crawl halted",
            )
            _publish_pipeline_completed(pipeline_run_id, status="failed")
            return {
                "ok": False,
                "pipelineRunId": pipeline_run_id,
                "agentId": agent.id,
                "error": crawl_result.halt_reason,
                "output": {
                    "discovery_worker": {
                        "pages": [page.model_dump() for page in crawl_result.pages],
                        "stats": crawl_result.stats.model_dump(),
                        "halted": True,
                        "halt_url": crawl_result.halt_url,
                        "authenticated": crawl_result.authenticated,
                    }
                },
            }
    except AuthError as exc:
        _publish_stage_failed(pipeline_run_id, DISCOVERY_STAGE, exc.message)
        _publish_pipeline_completed(pipeline_run_id, status="failed")
        raise
    except CrawlHaltError as exc:
        _publish_stage_failed(pipeline_run_id, DISCOVERY_STAGE, exc.message)
        _publish_pipeline_completed(pipeline_run_id, status="failed")
        raise
    except ValueError:
        logger.warning(
            "DiscoveryWorker skipped fetch — application not in DB (stub/test payload)",
            extra={"applicationId": application_id, "pipelineRunId": pipeline_run_id},
        )

    def _run(ctx: AgentContext) -> AgentResult:
        discovery_input = DiscoveryInput(
            base_url=snapshot.url if snapshot else "https://example.com",
        )
        return agent.run(discovery_input, ctx)

    try:
        result = run_agent_task("aqa.tasks.discover", agent.id, payload, _run)
    except Exception as exc:
        _publish_stage_failed(pipeline_run_id, DISCOVERY_STAGE, str(exc))
        _publish_pipeline_completed(pipeline_run_id, status="failed")
        raise

    duration_ms = int((time.monotonic() - started) * 1000)
    aqa_crawl_time_seconds.observe(duration_ms / 1000.0)
    if crawl_result is not None:
        stats = crawl_result.stats
        if stats.states_discovered:
            aqa_cic_states_total.inc(stats.states_discovered)
        if stats.interactions_executed:
            aqa_cic_interactions_total.inc(stats.interactions_executed)
        if stats.skipped_interaction_safety:
            aqa_cic_safety_skips_total.inc(stats.skipped_interaction_safety)
    _publish_stage_completed(pipeline_run_id, DISCOVERY_STAGE, duration_ms)
    _publish_pipeline_completed(pipeline_run_id)

    if crawl_result is not None:
        worker_output = {
            "pages": [page.model_dump() for page in crawl_result.pages],
            "stats": crawl_result.stats.model_dump(),
            "authenticated": crawl_result.authenticated,
        }
        if snapshot is not None:
            worker_output["homepage"] = snapshot.model_dump()
        result.setdefault("output", {})
        if isinstance(result["output"], dict):
            result["output"]["discovery_worker"] = worker_output
    elif snapshot is not None:
        worker_output = snapshot.model_dump()
        result.setdefault("output", {})
        if isinstance(result["output"], dict):
            result["output"]["discovery_worker"] = worker_output

    return result


def run_design(payload: dict[str, Any]) -> dict[str, Any]:
    agent = TestDesignAgent()

    def _run(ctx: AgentContext) -> AgentResult:
        return agent.run(TestDesignInput(), ctx)

    return run_agent_task("aqa.tasks.design", agent.id, payload, _run)


def run_generate_scripts(payload: dict[str, Any]) -> dict[str, Any]:
    agent = ScriptGenerationAgent()

    def _run(ctx: AgentContext) -> AgentResult:
        return agent.run(ScriptGenerationInput(), ctx)

    return run_agent_task("aqa.tasks.generate_scripts", agent.id, payload, _run)


def run_analyze(payload: dict[str, Any]) -> dict[str, Any]:
    agent = IntelligenceAgent()

    def _run(ctx: AgentContext) -> AgentResult:
        return agent.run(IntelligenceInput(), ctx)

    return run_agent_task("aqa.tasks.analyze", agent.id, payload, _run)
