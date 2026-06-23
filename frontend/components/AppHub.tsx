"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AppMapApprovalPanel } from "@/components/AppMapApprovalPanel";
import { DiscoveryScoreCard } from "@/components/DiscoveryScoreCard";
import { DiscoverySummaryPanel } from "@/components/DiscoverySummaryPanel";
import { ModuleTree, type ModuleColorMode } from "@/components/ModuleTree";
import { AppMapGraph } from "@/components/AppMapGraph";
import { CrawlLiveFeed } from "@/components/CrawlLiveFeed";
import { CrawlSettingsFields } from "@/components/CrawlSettingsFields";
import { DiscoverAdvancedFields } from "@/components/DiscoverAdvancedFields";
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
import { defaultDiscoverSettings, toDiscoverConfigPayload } from "@/lib/discoverConfig";
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
  AppMapApprovalResponse,
  PipelineRun,
  ScenarioFilters as FilterState,
  TestCaseSummary,
  TestRunSummary,
  AppMapResponse,
  DiscoverySummaryResponse,
} from "@/lib/types";

type Tab = "overview" | "pages" | "appmap" | "scenarios" | "runs";

export function AppHub({ appId }: { appId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const autoCrawlPending = useRef(searchParams.get("auto_crawl") === "1");
  const autoGeneratePending = useRef(false);
  const autoGenerateAfterApproval = useRef(false);
  const [app, setApp] = useState<Application | null>(null);
  const [cases, setCases] = useState<TestCaseSummary[]>([]);
  const [runs, setRuns] = useState<TestRunSummary[]>([]);
  const [appmap, setAppmap] = useState<AppMapResponse | null>(null);
  const [discoverySummary, setDiscoverySummary] = useState<DiscoverySummaryResponse | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
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
  const [discoverSettings, setDiscoverSettings] = useState(defaultDiscoverSettings);
  const [approval, setApproval] = useState<AppMapApprovalResponse | null>(null);
  const [skipApproval, setSkipApproval] = useState(() => loadSettings().skipAppmapApproval);
  const [appmapView, setAppmapView] = useState<"modules" | "graph">("graph");
  const [moduleColorMode, setModuleColorMode] = useState<ModuleColorMode>("risk");

  const refreshDiscoverySummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      const summary = await apiClient.getDiscoverySummary(appId);
      setDiscoverySummary(summary);
    } catch {
      setDiscoverySummary(null);
    } finally {
      setSummaryLoading(false);
    }
  }, [appId]);

  const refreshApproval = useCallback(async () => {
    try {
      const status = await apiClient.getAppMapApproval(appId);
      setApproval(status);
      return status;
    } catch {
      setApproval(null);
      return null;
    }
  }, [appId]);

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
      await Promise.all([
        apiClient
          .getAppMap(appId)
          .then(setAppmap)
          .catch(() => setAppmap(null)),
        refreshApproval(),
        refreshDiscoverySummary(),
      ]);
    } else {
      setAppmap(null);
      setApproval(null);
      setDiscoverySummary(null);
    }
  }, [appId, refreshApproval, refreshDiscoverySummary]);

  useEffect(() => {
    load().catch(console.error);
    requestNotificationPermission();
  }, [load]);

  useEffect(() => {
    if (tab !== "pages" && tab !== "appmap" && tab !== "overview") return;
    apiClient
      .getAppMap(appId)
      .then(setAppmap)
      .catch(() => setAppmap(null));
    if (tab === "appmap") {
      refreshApproval();
    }
    if (tab === "overview" || tab === "appmap") {
      refreshDiscoverySummary();
    }
  }, [appId, tab, events.length, refreshApproval, refreshDiscoverySummary]);

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
        showToast("Crawl complete — review AppMap before generating tests");
        load();
        apiClient.getAppMap(appId).then(setAppmap).catch(() => setAppmap(null));
        refreshApproval();
        refreshDiscoverySummary();
        if (loadSettings().autoGenerateAfterCrawl || autoGeneratePending.current) {
          autoGeneratePending.current = false;
          if (skipApproval) {
            startGenerate();
          } else {
            autoGenerateAfterApproval.current = true;
            showToast("Approve the AppMap to continue test generation");
          }
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
  }, [events, load, appId, refreshApproval, refreshDiscoverySummary]);

  const phases = derivePhaseStates(app, cases, events, activeRun, approval?.status ?? "none", skipApproval);
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
    const discoverConfig = toDiscoverConfigPayload(discoverSettings);
    try {
      const run = await apiClient.discover(appId, {
        crawlConfig: payload,
        force,
        useLlm: discoverSettings.useLlm,
        discoverConfig,
      });
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
          const run = await apiClient.discover(appId, {
            crawlConfig: payload,
            force: true,
            useLlm: discoverSettings.useLlm,
            discoverConfig,
          });
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
    const requireApproval = !skipApproval;
    try {
      const run = await apiClient.generateTests(appId, {
        requireAppmapApproval: requireApproval,
      });
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
      if (err instanceof ApiError && err.status === 422) {
        setErrorMsg(err.message);
        setTab("appmap");
      } else {
        setErrorMsg(err instanceof Error ? err.message : "Generate failed");
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleApproveAppMap() {
    setBusy(true);
    setErrorMsg(null);
    try {
      const status = await apiClient.approveAppMap(appId);
      setApproval(status);
      showToast("AppMap approved");
      if (autoGenerateAfterApproval.current) {
        autoGenerateAfterApproval.current = false;
        await startGenerate();
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Approve failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleRejectAppMap(reason: string) {
    setBusy(true);
    setErrorMsg(null);
    try {
      const status = await apiClient.rejectAppMap(appId, reason);
      setApproval(status);
      autoGenerateAfterApproval.current = false;
      showToast("AppMap rejected");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Reject failed");
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

  async function deleteApp() {
    if (!app) return;
    const confirmed = window.confirm(
      `Delete "${app.name}"?\n\nThis removes the app and all crawled pages, scenarios, runs, and artifacts from the database. This cannot be undone.`
    );
    if (!confirmed) return;

    setBusy(true);
    setErrorMsg(null);
    try {
      await apiClient.deleteApp(appId);
      showToast("Application deleted");
      router.push("/apps");
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setErrorMsg("Stop the active pipeline before deleting this application.");
      } else {
        setErrorMsg(err instanceof Error ? err.message : "Delete failed");
      }
    } finally {
      setBusy(false);
    }
  }

  const canGenerate =
    healthOk &&
    !busy &&
    !isPipelineActive &&
    phases.crawl === "done" &&
    (skipApproval || approval?.status === "approved");

  const generateDisabledReason = !healthOk
    ? "Workers offline"
    : phases.crawl !== "done"
      ? "Complete crawl first"
      : !skipApproval && approval?.status === "pending"
        ? "Approve AppMap first"
        : !skipApproval && approval?.status === "rejected"
          ? "AppMap was rejected — re-crawl or approve"
          : isPipelineActive
            ? "Wait for the current pipeline"
            : null;

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
      : !skipApproval && approval?.status === "pending" && phases.crawl === "done"
        ? ("approval_pending" as const)
        : !skipApproval && approval?.status === "rejected"
          ? ("approval_rejected" as const)
          : cases.length === 0 && phases.generate === "done"
            ? ("no_scenarios" as const)
            : phases.execute === "pending" && tab === "scenarios" && cases.length === 0
              ? ("generate_first" as const)
              : null;

  async function runFullPipeline() {
    autoGenerateAfterApproval.current = !skipApproval;
    autoGeneratePending.current = skipApproval;
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
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{app?.name || "Loading…"}</h1>
          <p className="text-sm text-[var(--muted)]">{app?.base_url}</p>
        </div>
        {app && (
          <button
            type="button"
            disabled={busy}
            onClick={() => deleteApp()}
            className="shrink-0 rounded border border-red-600/40 px-3 py-1.5 text-sm text-red-300 hover:bg-red-500/10 disabled:opacity-50"
          >
            Delete app
          </button>
        )}
      </div>

      <PipelinePhaseStepper
        crawl={phases.crawl}
        review={phases.review}
        generate={phases.generate}
        execute={phases.execute}
      />

      {errorMsg && (
        <div className="rounded border border-red-600/50 bg-red-500/10 px-4 py-2 text-sm text-red-300">
          {errorMsg}
        </div>
      )}
      <PhaseErrorPanel
        condition={errorCondition}
        appId={appId}
        onOpenAppMap={() => setTab("appmap")}
      />

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
          <DiscoverySummaryPanel summary={discoverySummary} loading={summaryLoading} />
          {appmap && <DiscoveryScoreCard appmap={appmap} />}
          <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
            <p className="mb-3 text-sm font-medium">Crawl settings</p>
            <CrawlSettingsFields
              settings={crawlSettings}
              onChange={setCrawlSettings}
              disabled={busy || isPipelineActive}
            />
          </div>
          <DiscoverAdvancedFields
            settings={discoverSettings}
            onChange={setDiscoverSettings}
            disabled={busy || isPipelineActive}
            onSkipApprovalChange={setSkipApproval}
          />
          <AppMapApprovalPanel
            approval={approval}
            busy={busy}
            onApprove={handleApproveAppMap}
            onReject={handleRejectAppMap}
          />
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
              disabled={!canGenerate}
              title={generateDisabledReason ?? undefined}
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

      {tab === "appmap" && (
        <div className="space-y-4">
          <AppMapApprovalPanel
            approval={approval}
            busy={busy}
            onApprove={handleApproveAppMap}
            onReject={handleRejectAppMap}
          />
          <DiscoveryScoreCard appmap={appmap} />
          <DiscoverySummaryPanel summary={discoverySummary} loading={summaryLoading} />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setAppmapView("modules")}
              className={`rounded px-3 py-1.5 text-sm ${
                appmapView === "modules"
                  ? "bg-blue-600 text-white"
                  : "border border-[var(--border)] text-[var(--muted)]"
              }`}
            >
              Modules
            </button>
            <button
              type="button"
              onClick={() => setAppmapView("graph")}
              className={`rounded px-3 py-1.5 text-sm ${
                appmapView === "graph"
                  ? "bg-blue-600 text-white"
                  : "border border-[var(--border)] text-[var(--muted)]"
              }`}
            >
              Graph
            </button>
            {appmap && appmap.schema_version >= 3 && (
              <span className="self-center text-xs text-green-400">
                AppMap v{appmap.schema_version}
                {appmap.stats.module_count != null && ` · ${appmap.stats.module_count} modules`}
                {appmap.discovery_completeness_score != null &&
                  ` · ${appmap.discovery_completeness_score}% complete`}
              </span>
            )}
            {(appmap?.modules?.length ?? 0) > 0 && (
              <select
                value={moduleColorMode}
                onChange={(e) => setModuleColorMode(e.target.value as ModuleColorMode)}
                className="ml-auto rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-xs"
              >
                <option value="none">Color: default</option>
                <option value="risk">Color: risk</option>
                <option value="testability">Color: testability</option>
                <option value="complexity">Color: complexity</option>
              </select>
            )}
          </div>
          {appmapView === "modules" ? (
            <ModuleTree
              appmap={appmap}
              colorMode={moduleColorMode}
              onColorModeChange={setModuleColorMode}
            />
          ) : (
            <AppMapGraph appmap={appmap} moduleColorMode={moduleColorMode} />
          )}
        </div>
      )}

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
