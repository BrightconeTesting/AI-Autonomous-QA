"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient, pipelineStreamBase } from "@/lib/api";
import type {
  Application,
  ExecutionHighlight,
  PhaseState,
  PipelineEvent,
  PipelineRun,
  StepResult,
  TestCaseSummary,
} from "./types";
import { EMPTY_HIGHLIGHT } from "./types";

const TERMINAL_SSE_EVENTS = new Set([
  "stage_failed",
  "pipeline_completed",
  "pipeline_cancelled",
]);

function mergePipelineEvents(
  prev: PipelineEvent[],
  incoming: PipelineEvent[]
): PipelineEvent[] {
  if (incoming.length === 0) return prev;
  const byId = new Map<string, PipelineEvent>();
  for (const e of prev) byId.set(e.id, e);
  for (const e of incoming) byId.set(e.id, e);
  return [...byId.values()].sort((a, b) => Number(a.id) - Number(b.id));
}

function parseEvent(raw: MessageEvent): PipelineEvent | null {
  try {
    const data = JSON.parse(raw.data as string) as Record<string, unknown>;
    return {
      id: raw.lastEventId || String(Date.now()),
      event: raw.type,
      data,
    };
  } catch {
    return null;
  }
}

export function usePipelineStream(pipelineRunId: string | null) {
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const terminalRef = useRef(false);

  useEffect(() => {
    if (!pipelineRunId) {
      setEvents([]);
      setConnected(false);
      return;
    }

    setEvents([]);
    setError(null);
    terminalRef.current = false;

    // Direct to API :3001 — Next.js dev proxy buffers SSE and live progress stalls at 0.
    const url = `${pipelineStreamBase}/${pipelineRunId}/stream`;
    const es = new EventSource(url);
    esRef.current = es;

    const onMessage = (e: MessageEvent) => {
      const parsed = parseEvent(e);
      if (!parsed) return;
      if (TERMINAL_SSE_EVENTS.has(parsed.event)) {
        terminalRef.current = true;
      }
      setEvents((prev) => mergePipelineEvents(prev, [parsed]));
    };

    const eventTypes = [
      "stage_started",
      "stage_progress",
      "stage_completed",
      "stage_failed",
      "pipeline_completed",
      "pipeline_cancelled",
      "scenario_started",
      "step_started",
      "step_completed",
      "step_screenshot",
      "scenario_completed",
    ];

    es.onopen = () => {
      setConnected(true);
      setError(null);
    };
    es.onerror = () => {
      setConnected(false);
      // EventSource fires onerror when the server closes after a terminal event — that is normal.
      if (!terminalRef.current) {
        setError("SSE disconnected — polling fallback active");
      }
    };

    for (const type of eventTypes) {
      es.addEventListener(type, onMessage);
    }

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [pipelineRunId]);

  // Poll stored Redis events — reliable fallback when SSE drops (e.g. after cancel) or buffers.
  useEffect(() => {
    if (!pipelineRunId) return;

    let cancelled = false;
    const poll = async () => {
      try {
        const fetched = await apiClient.getPipelineEvents(pipelineRunId);
        if (cancelled || fetched.length === 0) return;
        setEvents((prev) => mergePipelineEvents(prev, fetched));
      } catch {
        /* ignore */
      }
    };

    poll();
    const id = setInterval(poll, 2000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [pipelineRunId]);

  return { events, connected, error };
}

export function reduceExecutionHighlight(
  prev: ExecutionHighlight,
  event: PipelineEvent
): ExecutionHighlight {
  const d = event.data;
  const tcId = String(d.testcase_id ?? "");

  switch (event.event) {
    case "scenario_started":
      return {
        ...prev,
        activeTestcaseId: tcId,
        activeStepIndex: null,
        liveScreenshotArtifactId: null,
      };
    case "step_started":
      return {
        ...prev,
        activeTestcaseId: tcId,
        activeStepIndex: Number(d.step_index),
      };
    case "step_screenshot":
      return {
        ...prev,
        liveScreenshotArtifactId: String(d.artifact_id ?? ""),
      };
    case "step_completed": {
      const idx = Number(d.step_index);
      const stepResult: StepResult = {
        index: idx,
        keyword: String(d.keyword ?? ""),
        text: String(d.text ?? ""),
        outcome: String(d.outcome ?? "failed"),
        duration_ms: d.duration_ms != null ? Number(d.duration_ms) : null,
        error: d.error ? String(d.error) : null,
      };
      return {
        ...prev,
        stepOutcomes: {
          ...prev.stepOutcomes,
          [tcId]: { ...(prev.stepOutcomes[tcId] || {}), [idx]: stepResult },
        },
      };
    }
    case "scenario_completed":
      return {
        ...prev,
        activeTestcaseId: prev.activeTestcaseId === tcId ? null : prev.activeTestcaseId,
        activeStepIndex: prev.activeTestcaseId === tcId ? null : prev.activeStepIndex,
        scenarioOutcomes: {
          ...prev.scenarioOutcomes,
          [tcId]: {
            outcome: String(d.outcome ?? "failed"),
            videoArtifactId: d.video_artifact_id ? String(d.video_artifact_id) : undefined,
            traceArtifactId: d.trace_artifact_id ? String(d.trace_artifact_id) : undefined,
          },
        },
      };
    default:
      return prev;
  }
}

export function useExecutionHighlight(events: PipelineEvent[]) {
  const [highlight, setHighlight] = useState<ExecutionHighlight>(EMPTY_HIGHLIGHT);

  useEffect(() => {
    if (events.length === 0) return;
    setHighlight(events.reduce(reduceExecutionHighlight, EMPTY_HIGHLIGHT));
  }, [events]);

  const reset = useCallback(() => setHighlight(EMPTY_HIGHLIGHT), []);

  return { highlight, reset };
}

type PhaseMap = { crawl: PhaseState; generate: PhaseState; execute: PhaseState };

function stageFromData(data: Record<string, unknown>): string {
  return String(data.stage ?? data.current_stage ?? "");
}

export function derivePhaseStates(
  app: Application | null,
  testCases: TestCaseSummary[],
  events: PipelineEvent[],
  activeRun: PipelineRun | null
): PhaseMap {
  let crawl: PhaseState = app?.last_crawl_at ? "done" : "pending";
  let generate: PhaseState = testCases.length > 0 ? "done" : crawl === "done" ? "pending" : "pending";
  let execute: PhaseState = app?.last_run_at ? "done" : "pending";

  if (activeRun) {
    const stage = activeRun.current_stage;
    const isActive = activeRun.status === "running" || activeRun.status === "pending";

    if (isActive) {
      if (stage === "discover") crawl = "running";
      else if (stage === "generate_tests" || stage === "generate_scripts") generate = "running";
      else if (stage === "execute") execute = "running";
    }
  }

  const activeStage = activeRun?.current_stage ?? "";

  for (const ev of events) {
    const st = stageFromData(ev.data);
    switch (ev.event) {
      case "stage_started":
        if (st === "discover") crawl = "running";
        if (st === "generate_tests" || st === "generate_scripts") generate = "running";
        if (st === "execute") execute = "running";
        break;
      case "stage_completed":
        if (st === "discover") crawl = "done";
        if (st === "generate_tests") generate = "running";
        if (st === "generate_scripts") generate = "done";
        if (st === "execute") execute = "done";
        break;
      case "stage_failed":
        if (st === "discover") crawl = "failed";
        if (st === "generate_tests" || st === "generate_scripts") generate = "failed";
        if (st === "execute") execute = "failed";
        break;
      case "pipeline_cancelled":
        if (st === "discover" || activeStage === "discover") crawl = "cancelled";
        else if (st === "execute" || activeStage === "execute") execute = "cancelled";
        else generate = "cancelled";
        break;
      case "scenario_started":
      case "step_started":
        execute = "running";
        break;
    }
  }

  if (activeRun?.status === "failed") {
    const stage = activeRun.current_stage;
    if (stage === "discover") crawl = "failed";
    else if (stage === "execute") execute = "failed";
    else if (stage.includes("generate")) generate = "failed";
  }
  if (activeRun?.status === "cancelled") {
    const stage = activeRun.current_stage;
    if (stage === "discover") crawl = "cancelled";
    else if (stage === "execute") execute = "cancelled";
  }

  return { crawl, generate, execute };
}

export type CrawlProgress = {
  currentUrl: string | null;
  pagesDiscovered: number;
  maxPages: number | null;
  statesDiscovered: number;
};

export function useCrawlProgress(events: PipelineEvent[]): CrawlProgress {
  const [progress, setProgress] = useState<CrawlProgress>({
    currentUrl: null,
    pagesDiscovered: 0,
    maxPages: null,
    statesDiscovered: 0,
  });

  useEffect(() => {
    let currentUrl: string | null = null;
    let pagesDiscovered = 0;
    let maxPages: number | null = null;
    let statesDiscovered = 0;
    for (const ev of events) {
      if (ev.event !== "stage_progress") continue;
      const d = ev.data;
      if (d.current_url) currentUrl = String(d.current_url);
      if (d.pages_discovered != null) pagesDiscovered = Number(d.pages_discovered);
      if (d.max_pages != null) maxPages = Number(d.max_pages);
      if (d.states_discovered != null) statesDiscovered = Number(d.states_discovered);
    }
    if (currentUrl !== null || pagesDiscovered > 0 || maxPages != null || statesDiscovered > 0) {
      setProgress({ currentUrl, pagesDiscovered, maxPages, statesDiscovered });
    }
  }, [events]);

  return progress;
}

export function usePipelinePoll(pipelineRunId: string | null, enabled: boolean) {
  const [run, setRun] = useState<PipelineRun | null>(null);

  useEffect(() => {
    if (!pipelineRunId || !enabled) return;

    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch(`${pipelineStreamBase}/${pipelineRunId}`);
        if (!res.ok) return;
        const data = (await res.json()) as PipelineRun;
        if (!cancelled) setRun(data);
      } catch {
        /* ignore */
      }
    };

    poll();
    const id = setInterval(poll, 3000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [pipelineRunId, enabled]);

  return run;
}
