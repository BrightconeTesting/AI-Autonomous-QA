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

export type AppMapApiEndpoint = {
  endpoint_id: string;
  method: string;
  path: string;
  path_pattern: string;
  risk_score?: number | null;
  risk_factors?: string[];
  automation_complexity_score?: number | null;
  priority_index?: number | null;
  body_keys?: string[];
  seen_count?: number;
};

export type ApiDependencyGraphEdge = {
  from_endpoint_id: string;
  to_endpoint_id: string;
  edge_type: string;
  confidence?: number;
  observed_count?: number;
  dependency_keys?: string[];
  parallel_group_id?: string | null;
  is_primary?: boolean;
};

export type ApiDependencyGraphNode = {
  endpoint_id: string;
  method: string;
  path: string;
  path_pattern: string;
  depth?: number;
  module_id?: string | null;
  module_name?: string | null;
  requires_auth?: boolean;
  auth_inherited_from?: string | null;
  risk_score?: number | null;
  risk_tier?: string | null;
  is_entry?: boolean;
  is_leaf?: boolean;
  seen_count?: number;
  branching_factor?: number;
  is_login_endpoint?: boolean;
  is_session_check?: boolean;
};

export type ApiDependencyGraph = {
  nodes: ApiDependencyGraphNode[];
  edges: ApiDependencyGraphEdge[];
};

export type ApiFlowAnalysis = {
  entry_endpoint_ids: string[];
  leaf_endpoint_ids: string[];
  critical_path_endpoint_ids: string[];
  max_depth: number;
  depth_counts: Record<string, number>;
  parallel_group_count: number;
};

export type ApiEndpointCoverage = {
  covered_endpoint_ids: string[];
  planned_endpoint_ids: string[];
  untested_endpoint_ids: string[];
  unplanned_endpoint_ids: string[];
};

export type RecommendedTestArea = {
  area_id: string;
  area: string;
  area_type?: string | null;
  priority?: string;
  priority_index?: number;
  rationale?: string | null;
  module_id?: string | null;
  decision?: string;
};

export type PersonaVisibility = {
  personas?: AuthIntelligencePersona[];
  page_personas?: Record<string, string[]>;
  pages?: Array<{ page_id?: string; url?: string; title?: string | null }>;
  visibility_matrix?: Record<string, { visible_module_ids?: string[]; exclusive_module_ids?: string[] }>;
};

export type AuthIntelligencePersona = {
  persona_id: string;
  label?: string | null;
  authenticated?: boolean;
  visible_module_ids?: string[];
  exclusive_module_ids?: string[];
};

export type AuthIntelligenceBlocker = {
  type: string;
  page_url?: string | null;
  message?: string | null;
};

export type AuthIntelligence = {
  session_type?: string;
  login_flow_id?: string | null;
  login_api_endpoint_id?: string | null;
  protected_page_ids?: string[];
  protected_api_endpoint_ids?: string[];
  cookie_names?: string[];
  storage_keys?: string[];
  personas?: AuthIntelligencePersona[];
  visibility_matrix?: Record<
    string,
    { visible_module_ids?: string[]; exclusive_module_ids?: string[] }
  >;
  blockers?: AuthIntelligenceBlocker[];
  authenticated?: boolean;
};

export type TestDataCatalogField = {
  name: string;
  display_name?: string | null;
  data_type?: string;
  required?: boolean;
  constraints?: Record<string, unknown>;
  suggested_safe_value?: string;
  pii_class?: string | null;
  element_id?: string | null;
  semantic_selector?: string | null;
  filled_during_crawl?: boolean;
  needs_test_data?: boolean;
};

export type TestDataCatalogEntry = {
  catalog_id: string;
  target_type: string;
  target_id: string;
  fields: TestDataCatalogField[];
  synthetic_strategy?: string;
  never_use_live_pii?: boolean;
  context_label?: string | null;
  unfilled_field_count?: number;
  filled_during_crawl?: boolean;
  reachable_via?: string[];
  alias_target_ids?: string[];
  state_key?: string | null;
  replay_steps?: Record<string, unknown>[];
};

export type AppMapSpaRoute = {
  route_id: string;
  path_pattern: string;
  url_examples?: string[];
  discovery_method?: string;
  discovery_methods?: string[];
  page_id?: string | null;
  module_id?: string | null;
  confidence?: number;
};

export type TestAreaDecisionsResponse = {
  application_id: string;
  pipeline_run_id: string;
  decisions: Record<string, string>;
};

export type DiscoverRunSummary = {
  pipeline_run_id: string;
  started_at: string | null;
  ended_at: string | null;
  appmap_hash: string | null;
  has_artifact: boolean;
  page_count?: number | null;
  element_count?: number | null;
  flow_count?: number | null;
};

export type AppMapDiffResponse = {
  application_id: string;
  from_run_id: string;
  to_run_id: string;
  from_appmap_hash: string | null;
  to_appmap_hash: string | null;
  unchanged: boolean;
  pages: {
    added: Array<{ page_id: string; url: string; title?: string | null; changed_fields?: string[] }>;
    removed: Array<{ page_id: string; url: string; title?: string | null }>;
    changed: Array<{ page_id: string; url: string; title?: string | null; changed_fields: string[] }>;
  };
  elements: {
    delta_by_page: Array<{ page_id: string; from_count: number; to_count: number; delta: number }>;
  };
  api_endpoints: {
    added: Array<{ endpoint_id: string; method: string; path: string }>;
    removed: Array<{ endpoint_id: string; method: string; path: string }>;
  };
  api_dependency_graph: {
    edges_added: ApiDependencyGraphEdge[];
    edges_removed: ApiDependencyGraphEdge[];
  };
  modules: {
    added: Array<{ module_id: string; name: string }>;
    removed: Array<{ module_id: string; name: string }>;
    changed: Array<{ module_id: string; name: string; changed_fields: string[] }>;
  };
  scores: Record<string, { from: number; to: number; delta: number }>;
  entities: {
    added: Array<{ entity_id: string; name: string }>;
    removed: Array<{ entity_id: string; name: string }>;
    crud_surfaces_changed: Array<{ entity_id: string; name: string }>;
  };
  recommended_test_areas: {
    added: RecommendedTestArea[];
    removed: RecommendedTestArea[];
  };
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
    spa_route_count?: number;
    test_data_catalog_count?: number;
  };
  states: AppMapState[];
  transitions: AppMapTransition[];
  modules?: AppMapModule[];
  navigation_graph?: NavigationGraphEdge[];
  api_endpoints?: AppMapApiEndpoint[];
  api_dependency_graph?: ApiDependencyGraph | null;
  api_flow_analysis?: ApiFlowAnalysis | null;
  api_coverage?: ApiEndpointCoverage | null;
  auth_intelligence?: AuthIntelligence | null;
  test_data_catalog?: TestDataCatalogEntry[];
  spa_routes?: AppMapSpaRoute[];
  recommended_test_areas?: RecommendedTestArea[];
  test_area_decisions?: Record<string, string>;
  persona_visibility?: PersonaVisibility | null;
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
