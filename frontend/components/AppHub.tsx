"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AppMapGraph } from "@/components/AppMapGraph";
import { CrawlLiveFeed } from "@/components/CrawlLiveFeed";
import { CrawlSettingsFields } from "@/components/CrawlSettingsFields";
import { CucumberScenarioList } from "@/components/CucumberScenarioList";
import { ExecutionMediaPanel } from "@/components/ExecutionMediaPanel";
import { PhaseErrorPanel } from "@/components/PhaseErrorPanel";
import { PipelinePhaseStepper } from "@/components/PipelinePhaseStepper";
import { RunLauncher } from "@/components/RunLauncher";
import { RunResultsTable } from "@/components/RunResultsTable";
import { PageGrid } from "@/components/PageGrid";
import {
  ScenarioFilters,
  applyScenarioFilters,
} from "@/components/ScenarioFilters";
import { apiClient, ApiError } from "@/lib/api";
import { crawlSettingsFromConfig, defaultCrawlSettings, toCrawlConfigPayload } from "@/lib/crawlConfig";
import { notifyPhaseComplete, requestNotificationPermission, showToast } from "@/lib/notifications";
import { loadSettings } from "@/lib/settings";
import {
  derivePhaseStates,
  useCrawlProgress,
  useExecutionHighlight,
  usePipelinePoll,
  usePipelineStream,
} from "@/lib/sse";
import type {
  Application,
  PipelineRun,
  ScenarioFilters as FilterState,
  TestCaseSummary,
  TestRunSummary,
  AppMapResponse,
} from "@/lib/types";

type Tab = "overview" | "pages" | "appmap" | "scenarios" | "runs";

export function AppHub({ appId }: { appId: string }) {
  const searchParams = useSearchParams();
  const autoCrawlPending = useRef(searchParams.get("auto_crawl") === "1");
  const autoGeneratePending = useRef(false);
  const [app, setApp] = useState<Application | null>(null);
  const [cases, setCases] = useState<TestCaseSummary[]>([]);
  const [runs, setRuns] = useState<TestRunSummary[]>([]);
  const [appmap, setAppmap] = useState<AppMapResponse | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [tab, setTab] = useState<Tab>("overview");
  const [busy, setBusy] = useState(false);
  const [activePipelineRunId, setActivePipelineRunId] = useState<string | null>(null);
  const [activeRun, setActiveRun] = useState<PipelineRun | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [filters, setFilters] = useState<FilterState>({
    search: "",
    priorities: [],
    tags: [],
    feature: null,
  });
  const [healthOk, setHealthOk] = useState(true);
  const [crawlSettings, setCrawlSettings] = useState(defaultCrawlSettings);

  const { events, connected, error: sseError } = usePipelineStream(activePipelineRunId);
  const { highlight, reset: resetHighlight } = useExecutionHighlight(events);
  const crawlProgress = useCrawlProgress(events);
  const polledRun = usePipelinePoll(activePipelineRunId, !connected);

  const load = useCallback(async () => {
    const [appRes, casesRes, runsRes, activeRes] = await Promise.all([
      apiClient.getApp(appId),
      apiClient.listTestCases(appId).catch(() => ({ items: [], total: 0 })),
      apiClient.listRuns(appId).catch(() => ({ items: [], total: 0 })),
      apiClient.getActivePipeline(appId).catch(() => ({ pipeline_run: null })),
    ]);
    setApp(appRes);
    setCases(casesRes.items);
    setRuns(runsRes.items);
    setCrawlSettings(crawlSettingsFromConfig(appRes.crawl_config));
    const active = activeRes.pipeline_run;
    if (active && (active.status === "pending" || active.status === "running")) {
      setActivePipelineRunId(active.pipeline_run_id);
      setActiveRun(active);
    } else {
      setActivePipelineRunId(null);
      setActiveRun(null);
    }
    if (appRes.last_crawl_at) {
      apiClient
        .getAppMap(appId)
        .then(setAppmap)
        .catch(() => setAppmap(null));
    }
  }, [appId]);

  useEffect(() => {
    load().catch(console.error);
    requestNotificationPermission();
  }, [load]);

  useEffect(() => {
    if (tab !== "pages" && tab !== "appmap") return;
    apiClient
      .getAppMap(appId)
      .then(setAppmap)
      .catch(() => setAppmap(null));
  }, [appId, tab, events.length]);

  useEffect(() => {
    if (!autoCrawlPending.current || busy || !healthOk) return;
    autoCrawlPending.current = false;
    if (loadSettings().autoGenerateAfterCrawl) {
      autoGeneratePending.current = true;
    }
    startDiscover();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [healthOk]);

  useEffect(() => {
    apiClient.health().then((h) => setHealthOk(h?.status === "ok" && h?.redis === "ok")).catch(() => setHealthOk(false));
  }, []);

  useEffect(() => {
    if (polledRun) setActiveRun(polledRun);
  }, [polledRun]);

  useEffect(() => {
    const failed = [...events].reverse().find((e) => e.event === "stage_failed");
    if (failed?.data.error) {
      setErrorMsg(String(failed.data.error));
    }
  }, [events]);

  useEffect(() => {
    const terminal = events.filter((e) =>
      ["stage_completed", "stage_failed", "pipeline_completed", "pipeline_cancelled"].includes(
        e.event
      )
    );
    const last = terminal[terminal.length - 1];
    if (!last) return;

    if (last.event === "stage_completed") {
      const stage = String(last.data.stage ?? "");
      if (stage === "discover") {
        notifyPhaseComplete("crawl");
        showToast("Crawl complete");
        load();
        apiClient.getAppMap(appId).then(setAppmap).catch(() => setAppmap(null));
        if (loadSettings().autoGenerateAfterCrawl || autoGeneratePending.current) {
          autoGeneratePending.current = false;
          startGenerate();
        }
      }
      if (stage === "generate_scripts") {
        notifyPhaseComplete("generate");
        showToast("Tests generated");
        load();
      }
      if (stage === "execute") {
        notifyPhaseComplete("execute");
        showToast("Execution complete");
        load();
      }
    }

    if (
      last.event === "pipeline_completed" ||
      last.event === "stage_failed" ||
      last.event === "pipeline_cancelled"
    ) {
      setTimeout(() => {
        setActivePipelineRunId(null);
        load();
      }, 1500);
    }
  }, [events, load]);

  const phases = derivePhaseStates(app, cases, events, activeRun);
  const isPipelineActive =
    activeRun?.status === "running" ||
    activeRun?.status === "pending" ||
    phases.crawl === "running" ||
    phases.generate === "running" ||
    phases.execute === "running";

  const filteredCases = useMemo(
    () => applyScenarioFilters(cases, filters),
    [cases, filters]
  );

  const allTags = useMemo(
    () => [...new Set(cases.flatMap((c) => c.tags))].sort(),
    [cases]
  );
  const features = useMemo(
    () => [...new Set(cases.map((c) => c.feature || "Scenarios"))].sort(),
    [cases]
  );

  async function startDiscover(force = false) {
    setBusy(true);
    setErrorMsg(null);
    resetHighlight();
    const payload = toCrawlConfigPayload(crawlSettings);
    try {
      const run = await apiClient.discover(appId, { crawlConfig: payload, force });
      setActivePipelineRunId(run.pipeline_run_id);
      setActiveRun({
        pipeline_run_id: run.pipeline_run_id,
        application_id: appId,
        status: run.status,
        current_stage: run.current_stage,
        started_at: null,
        ended_at: null,
        error_message: null,
      });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const activeId =
          typeof err.body.active_pipeline_run_id === "string"
            ? err.body.active_pipeline_run_id
            : null;
        if (
          activeId &&
          window.confirm(
            "A pipeline is already running for this app (or stuck from a previous session). Cancel it and start a new crawl?"
          )
        ) {
          await apiClient.cancelPipeline(activeId);
          setActivePipelineRunId(null);
          setActiveRun(null);
          const run = await apiClient.discover(appId, { crawlConfig: payload, force: true });
          setActivePipelineRunId(run.pipeline_run_id);
          setActiveRun({
            pipeline_run_id: run.pipeline_run_id,
            application_id: appId,
            status: run.status,
            current_stage: run.current_stage,
            started_at: null,
            ended_at: null,
            error_message: null,
          });
          return;
        }
      }
      setErrorMsg(err instanceof Error ? err.message : "Crawl failed to start");
    } finally {
      setBusy(false);
    }
  }

  async function startGenerate() {
    setBusy(true);
    setErrorMsg(null);
    try {
      const run = await apiClient.generateTests(appId);
      setActivePipelineRunId(run.pipeline_run_id);
      setActiveRun({
        pipeline_run_id: run.pipeline_run_id,
        application_id: appId,
        status: run.status,
        current_stage: run.current_stage,
        started_at: null,
        ended_at: null,
        error_message: null,
      });
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Generate failed");
    } finally {
      setBusy(false);
    }
  }

  async function runSelected() {
    const ids = [...selected];
    const destructiveOnly =
      ids.length === 1 &&
      cases.find((c) => c.testcase_id === ids[0])?.tags.some((t) => t.includes("destructive"));
    if (destructiveOnly) {
      const ok = window.confirm(
        "This scenario is marked destructive (logout/delete). Run it anyway?"
      );
      if (!ok) return;
    }

    setBusy(true);
    setErrorMsg(null);
    resetHighlight();
    try {
      const run = await apiClient.execute(appId, ids);
      setActivePipelineRunId(run.pipeline_run_id);
      setTab("scenarios");
      const pr = await apiClient.getPipelineRun(run.pipeline_run_id);
      setActiveRun(pr);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Execute failed");
    } finally {
      setBusy(false);
    }
  }

  async function cancelPipelineById(pipelineRunId: string) {
    setBusy(true);
    try {
      await apiClient.cancelPipeline(pipelineRunId);
      setActivePipelineRunId(null);
      setActiveRun(null);
      showToast("Pipeline cancelled");
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function cancelPipeline() {
    if (!activePipelineRunId) return;
    await cancelPipelineById(activePipelineRunId);
  }

  async function exportFeature() {
    const content = await apiClient.exportFeature(appId);
    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${app?.name || "app"}-scenarios.feature`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const canRunScenarios =
    healthOk && cases.length > 0 && !isPipelineActive && phases.crawl !== "pending";

  const runDisabledReason = !healthOk
    ? "Workers offline — start pnpm dev:worker:celery"
    : cases.length === 0
      ? "Generate tests first (Overview → Generate tests)"
      : isPipelineActive
        ? "Wait for the current pipeline to finish"
        : phases.crawl === "pending"
          ? "Complete crawl before running scenarios"
          : null;

  const errorCondition =
    !healthOk
      ? ("workers" as const)
      : cases.length === 0 && phases.generate === "done"
        ? ("no_scenarios" as const)
        : phases.execute === "pending" && tab === "scenarios" && cases.length === 0
          ? ("generate_first" as const)
          : null;

  async function runFullPipeline() {
    autoGeneratePending.current = true;
    await startDiscover();
  }

  const tabs: { id: Tab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "pages", label: "Pages" },
    { id: "appmap", label: "AppMap" },
    { id: "scenarios", label: "Scenarios" },
    { id: "runs", label: "Runs" },
  ];

  return (
    <div className="space-y-6">
      <Link href="/apps" className="text-sm text-[var(--muted)] hover:underline">
        ← Back to apps
      </Link>
      <div>
        <h1 className="text-2xl font-semibold">{app?.name || "Loading…"}</h1>
        <p className="text-sm text-[var(--muted)]">{app?.base_url}</p>
      </div>

      <PipelinePhaseStepper
        crawl={phases.crawl}
        generate={phases.generate}
        execute={phases.execute}
      />

      {errorMsg && (
        <div className="rounded border border-red-600/50 bg-red-500/10 px-4 py-2 text-sm text-red-300">
          {errorMsg}
        </div>
      )}
      <PhaseErrorPanel condition={errorCondition} appId={appId} />

      <div className="flex gap-1 border-b border-[var(--border)]">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm ${
              tab === t.id
                ? "border-b-2 border-blue-500 text-[var(--text)]"
                : "text-[var(--muted)] hover:text-[var(--text)]"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="space-y-4">
          <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
            <p className="mb-3 text-sm font-medium">Crawl settings</p>
            <CrawlSettingsFields
              settings={crawlSettings}
              onChange={setCrawlSettings}
              disabled={busy || isPipelineActive}
            />
          </div>
          <div className="flex flex-wrap gap-2">
            {isPipelineActive && activePipelineRunId && (
              <p className="w-full text-sm text-amber-400/90">
                Pipeline in progress — use Stop pipeline to cancel before starting another crawl.
              </p>
            )}
            <button
              disabled={busy || !healthOk}
              onClick={() => startDiscover()}
              className="rounded bg-blue-600 px-3 py-2 text-sm text-white disabled:opacity-50"
            >
              Start crawl
            </button>
            <button
              disabled={busy || phases.crawl !== "done" || !healthOk}
              onClick={startGenerate}
              className="rounded border border-[var(--border)] px-3 py-2 text-sm disabled:opacity-50"
            >
              Generate tests
            </button>
            <button
              disabled={busy || !healthOk}
              onClick={runFullPipeline}
              className="rounded border border-blue-500/50 px-3 py-2 text-sm text-blue-400 disabled:opacity-50"
            >
              Crawl → Generate
            </button>
            {isPipelineActive && activePipelineRunId && (
              <button
                disabled={busy}
                onClick={cancelPipeline}
                className="rounded border border-orange-500/50 px-3 py-2 text-sm text-orange-400 disabled:opacity-50"
              >
                Stop pipeline
              </button>
            )}
          </div>
          {appmap && appmap.stats.page_count > 0 && phases.crawl === "done" && (
            <p className="text-sm text-green-400">
              Last crawl: {appmap.stats.page_count} pages, {appmap.stats.flow_count} flows
              {appmap.stats.state_count > 0 && `, ${appmap.stats.state_count} CIC states`} — open{" "}
              <button type="button" className="underline" onClick={() => setTab("pages")}>
                Pages
              </button>{" "}
              to view screenshots.
            </p>
          )}
          <CrawlLiveFeed
            progress={crawlProgress}
            events={events}
            isActive={phases.crawl === "running"}
          />
          {sseError && (
            <p className="text-xs text-[var(--muted)]">{sseError}</p>
          )}
          {activePipelineRunId && (
            <p className="font-mono text-xs text-[var(--muted)]">
              Pipeline: {activePipelineRunId}
            </p>
          )}
        </div>
      )}

      {tab === "pages" && (
        <PageGrid appId={appId} pages={appmap?.pages ?? []} />
      )}

      {tab === "appmap" && <AppMapGraph appmap={appmap} />}

      {tab === "scenarios" && (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="space-y-4">
            <ScenarioFilters
              filters={filters}
              onChange={setFilters}
              features={features}
              allTags={allTags}
            />
            <RunLauncher
              selectedCount={selected.size}
              filteredCount={filteredCases.length}
              busy={busy}
              canRun={canRunScenarios}
              disabledReason={runDisabledReason}
              onRun={runSelected}
              onExport={exportFeature}
              onSelectAll={() => setSelected(new Set(filteredCases.map((c) => c.testcase_id)))}
              onClearSelection={() => setSelected(new Set())}
            />
            <CucumberScenarioList
              cases={filteredCases}
              selected={selected}
              onSelectionChange={setSelected}
              highlight={highlight}
            />
          </div>
          <ExecutionMediaPanel highlight={highlight} onArtifactDeleted={load} />
        </div>
      )}

      {tab === "runs" && <RunResultsTable runs={runs} appId={appId} />}
    </div>
  );
}
