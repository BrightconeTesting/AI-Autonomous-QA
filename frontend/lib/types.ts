export type PhaseState = "pending" | "running" | "done" | "failed" | "cancelled";

export type GherkinStep = {
  keyword: string;
  text: string;
  action?: string;
  target?: string;
};

export type GherkinBlock = {
  feature: string;
  scenario: string;
  tags: string[];
  steps: GherkinStep[];
};

export type TestCaseSummary = {
  testcase_id: string;
  name: string;
  priority: string;
  status: string;
  flow_id: string | null;
  feature: string | null;
  tags: string[];
  step_count: number;
  created_at: string | null;
};

export type TestCaseDetail = {
  testcase_id: string;
  app_id: string;
  name: string;
  priority: string;
  status: string;
  flow_id: string | null;
  steps: {
    gherkin?: GherkinBlock;
    steps?: Array<{ action: string; target: string }>;
  };
  pipeline_run_id: string | null;
};

export type Application = {
  app_id: string;
  name: string;
  base_url: string;
  last_crawl_at: string | null;
  last_run_at: string | null;
  auth_config: { configured: boolean; type?: string };
  crawl_config?: Record<string, unknown>;
};

export type PipelineRun = {
  pipeline_run_id: string;
  application_id: string;
  status: string;
  current_stage: string;
  started_at: string | null;
  ended_at: string | null;
  error_message: string | null;
};

export type StepResult = {
  index: number;
  keyword: string | null;
  text: string | null;
  outcome: string;
  duration_ms: number | null;
  error: string | null;
};

export type ScenarioResult = {
  testcase_id: string;
  name: string;
  outcome: string;
  duration_ms: number | null;
  artifact_ids: string[];
  video_artifact_id?: string | null;
  step_results: StepResult[];
  step_timestamps_ms?: number[];
  error: string | null;
};

export type TestRunDetail = {
  run_id: string;
  app_id: string;
  pipeline_run_id: string | null;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  summary: { total: number; passed: number; failed: number; skipped: number };
  results: ScenarioResult[];
};

export type TestRunSummary = {
  run_id: string;
  app_id: string;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  summary: { total: number; passed: number; failed: number; skipped: number };
};

export type ArtifactMeta = {
  id: string;
  type: string;
  size_bytes: number;
  testcase_id: string | null;
  run_id: string | null;
  created_at: string;
};

export type PipelineEvent = {
  id: string;
  event: string;
  data: Record<string, unknown>;
};

export type ExecutionHighlight = {
  activeTestcaseId: string | null;
  activeStepIndex: number | null;
  stepOutcomes: Record<string, Record<number, StepResult>>;
  scenarioOutcomes: Record<
    string,
    { outcome: string; videoArtifactId?: string; traceArtifactId?: string }
  >;
  liveScreenshotArtifactId: string | null;
};

export type ScenarioFilters = {
  search: string;
  priorities: string[];
  tags: string[];
  feature: string | null;
};

export const EMPTY_HIGHLIGHT: ExecutionHighlight = {
  activeTestcaseId: null,
  activeStepIndex: null,
  stepOutcomes: {},
  scenarioOutcomes: {},
  liveScreenshotArtifactId: null,
};

export type AppMapPage = {
  page_id: string;
  url: string;
  title: string | null;
  screenshot_path: string | null;
};

export type AppMapFlow = {
  flow_id: string;
  name: string;
  description: string | null;
  source: string;
  steps: Array<Record<string, unknown>>;
};

export type AppMapState = {
  state_id: string;
  page_id: string;
  state_key: string;
  title: string | null;
};

export type AppMapTransition = {
  transition_id: string;
  from_state_id: string;
  to_state_id: string;
  action: Record<string, unknown>;
};

export type AppMapResponse = {
  schema_version: number;
  application_id: string;
  last_crawl_at: string | null;
  pages: AppMapPage[];
  flows: AppMapFlow[];
  stats: {
    page_count: number;
    element_count: number;
    flow_count: number;
    state_count: number;
    interaction_count: number;
  };
  states: AppMapState[];
  transitions: AppMapTransition[];
};

export type DashboardSummary = {
  app_count: number;
  total_runs: number;
  total_passed: number;
  total_failed: number;
  storage_bytes: number;
  recent_runs: Array<{
    run_id: string;
    app_id: string;
    app_name: string;
    status: string;
    started_at: string | null;
    summary: { total: number; passed: number; failed: number; skipped: number };
  }>;
};
