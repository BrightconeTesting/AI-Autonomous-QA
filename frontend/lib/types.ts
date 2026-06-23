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
  confidence?: number;
  confidence_factors?: string[];
  risk_score?: number;
  testability_score?: number;
  automation_complexity_score?: number;
};

export type LlmBudgetUsage = {
  stages?: Record<string, { tokens_used?: number; budget?: number }>;
  total_tokens_used?: number;
  total_cap?: number;
  truncated?: boolean;
};

export type AppMapApprovalStatus = "none" | "pending" | "approved" | "rejected";

export type AppMapApprovalResponse = {
  application_id: string;
  pipeline_run_id: string | null;
  status: AppMapApprovalStatus;
  approved_at: string | null;
  rejection_reason: string | null;
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

export type AppMapModuleFeature = {
  name: string;
  flow_id: string | null;
  page_ids: string[];
};

export type AppMapModule = {
  module_id: string;
  name: string;
  parent_module_id: string | null;
  pages: string[];
  flow_ids: string[];
  features: AppMapModuleFeature[];
  confidence?: number;
  confidence_factors?: string[];
  review_required?: boolean;
  risk_score?: number;
  risk_factors?: string[];
  testability_score?: number;
  automation_complexity_score?: number;
  complexity_factors?: string[];
  business_criticality?: string;
};

export type TopRiskModule = {
  module_id: string;
  name?: string;
  risk_score: number;
  top_factor?: string;
};

export type ScoringSummary = {
  app_risk_score: number;
  app_testability_score: number;
  app_automation_complexity_score: number;
  discovery_completeness_score: number;
  high_risk_modules: string[];
  top_risk_modules: TopRiskModule[];
  recommendations: string[];
};

export type NavigationGraphEdge = {
  from_page_id: string | null;
  to_page_id: string | null;
  to_url?: string | null;
  via?: string | null;
  label?: string | null;
};

export type AppMapResponse = {
  schema_version: number;
  application_id: string;
  last_crawl_at: string | null;
  mvp?: boolean;
  pages: AppMapPage[];
  flows: AppMapFlow[];
  stats: {
    page_count: number;
    element_count: number;
    flow_count: number;
    state_count: number;
    interaction_count: number;
    module_count?: number;
  };
  states: AppMapState[];
  transitions: AppMapTransition[];
  modules?: AppMapModule[];
  navigation_graph?: NavigationGraphEdge[];
  discovery_completeness_score?: number | null;
  recommendations?: string[];
  scoring_summary?: ScoringSummary | null;
  llm_budget_usage?: LlmBudgetUsage;
};

export type DiscoverySummaryCounts = {
  pages: number;
  buttons: number;
  forms: number;
  links: number;
  api_endpoints: number;
  flows: number;
  entities: number;
  modules: number;
  spa_routes: number;
  api_dependency_edges: number;
};

export type DiscoverySummaryRiskArea = {
  module: string;
  risk_score: number;
  top_factor: string;
};

export type DiscoverySummaryModuleNode = {
  name: string;
  children: string[];
};

export type DiscoverySummaryAuth = {
  session_type: string;
  personas_authenticated: string[];
};

export type DiscoverySummaryResponse = {
  application_id: string;
  last_crawl_at: string | null;
  schema_version: number;
  counts: DiscoverySummaryCounts;
  scoring_summary?: ScoringSummary | null;
  discovery_completeness_score: number;
  recommendations: string[];
  what_pages_exist: string[];
  what_forms_exist: Array<{ name: string; page: string }>;
  what_apis_are_called: Array<{ method: string; path: string }>;
  what_should_be_tested_first: string[];
  top_risk_areas: DiscoverySummaryRiskArea[];
  module_tree: DiscoverySummaryModuleNode[];
  auth_summary: DiscoverySummaryAuth;
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
