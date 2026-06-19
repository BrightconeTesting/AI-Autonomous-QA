import type {
  Application,
  ArtifactMeta,
  PipelineEvent,
  PipelineRun,
  TestCaseDetail,
  TestCaseSummary,
  TestRunDetail,
  TestRunSummary,
} from "./types";

export type { Application, TestCaseSummary, PipelineRun } from "./types";

/** REST + SSE base — bypass Next.js proxy for streaming (avoids buffered SSE). */
export const API_ORIGIN =
  typeof window !== "undefined"
    ? process.env.NEXT_PUBLIC_API_ORIGIN || "http://localhost:3001"
    : process.env.API_URL?.replace(/\/api\/v1\/?$/, "") || "http://localhost:3001";

const API_BASE =
  typeof window === "undefined"
    ? process.env.API_URL || "http://localhost:3001/api/v1"
    : "/api/v1";

const PIPELINE_API_BASE = `${API_ORIGIN}/api/v1`;

const SERVER_FETCH_MS = 3000;

export class ApiError extends Error {
  status: number;
  body: Record<string, unknown>;

  constructor(message: string, status: number, body: Record<string, unknown>) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

function parseApiError(status: number, body: string): ApiError {
  try {
    const json = JSON.parse(body) as Record<string, unknown>;
    const detail = typeof json.detail === "string" ? json.detail : body;
    return new ApiError(detail, status, json);
  } catch {
    return new ApiError(body || String(status), status, {});
  }
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const signal =
    typeof window === "undefined"
      ? AbortSignal.timeout(SERVER_FETCH_MS)
      : init?.signal;

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    signal,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text();
    throw parseApiError(res.status, body);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export type ApplicationList = { items: Application[]; total: number };
export type TestCaseList = { items: TestCaseSummary[]; total: number };
export type TestRunList = { items: TestRunSummary[]; total: number };

export const apiClient = {
  listApps: () => api<ApplicationList>("/apps"),
  getApp: (id: string) => api<Application>(`/apps/${id}`),
  getActivePipeline: (appId: string) =>
    api<{ pipeline_run: PipelineRun | null }>(`/apps/${appId}/active-pipeline`),
  createApp: (body: unknown) =>
    api<Application>("/apps", { method: "POST", body: JSON.stringify(body) }),
  discover: (
    id: string,
    opts?: { force?: boolean; crawlConfig?: Record<string, unknown> }
  ) =>
    api<{ pipeline_run_id: string; status: string; current_stage: string }>(
      `/apps/${id}/discover`,
      {
        method: "POST",
        body: JSON.stringify({
          force: opts?.force ?? false,
          ...(opts?.crawlConfig ? { crawlConfigOverrides: opts.crawlConfig } : {}),
        }),
      }
    ),
  generateTests: (id: string, opts?: { max_tests?: number }) =>
    api<{ pipeline_run_id: string; status: string; current_stage: string }>(
      `/apps/${id}/generate-tests`,
      {
        method: "POST",
        body: JSON.stringify({
          force: true,
          requireAppmapV2: false,
          max_tests: opts?.max_tests ?? 200,
          priorities: ["critical", "high", "medium"],
        }),
      }
    ),
  listTestCases: (id: string) => api<TestCaseList>(`/apps/${id}/test-cases`),
  getTestCase: (id: string) => api<TestCaseDetail>(`/test-cases/${id}`),
  exportFeature: async (appId: string): Promise<string> => {
    const res = await fetch(`${API_BASE}/apps/${appId}/test-cases/export.feature`);
    if (!res.ok) throw new Error(`${res.status}`);
    return res.text();
  },
  execute: (
    id: string,
    testcaseIds: string[],
    opts?: { capture_video?: boolean; retry_from_run_id?: string; retry_mode?: string }
  ) =>
    api<{ pipeline_run_id: string; test_run_id: string }>(`/apps/${id}/execute`, {
      method: "POST",
      body: JSON.stringify({
        testcase_ids: testcaseIds,
        force: true,
        capture_video: opts?.capture_video ?? true,
        capture_trace: true,
        retry_from_run_id: opts?.retry_from_run_id ?? null,
        retry_mode: opts?.retry_mode ?? null,
      }),
    }),
  getPipelineRun: (id: string) => api<PipelineRun>(`/pipeline-runs/${id}`),
  getPipelineEvents: async (id: string): Promise<PipelineEvent[]> => {
    const res = await fetch(`${PIPELINE_API_BASE}/pipeline-runs/${id}/events`, {
      cache: "no-store",
    });
    if (!res.ok) return [];
    const rows = (await res.json()) as Array<{ id: string; event: string; data: Record<string, unknown> }>;
    return rows.map((row) => ({ id: row.id, event: row.event, data: row.data }));
  },
  cancelPipeline: (id: string) =>
    api<PipelineRun>(`/pipeline-runs/${id}/cancel`, { method: "POST", body: "{}" }),
  listRuns: (appId: string) => api<TestRunList>(`/apps/${appId}/runs`),
  getRun: (runId: string) => api<TestRunDetail>(`/runs/${runId}`),
  getArtifactMeta: (id: string) => api<ArtifactMeta>(`/artifacts/${id}/meta`),
  deleteArtifact: (id: string) =>
    api<void>(`/artifacts/${id}`, { method: "DELETE" }),
  artifactUrl: (id: string) => `${API_BASE}/artifacts/${id}`,
  artifactStreamUrl: (id: string) => `${API_ORIGIN}/api/v1/artifacts/${id}`,
  health: () =>
    fetch("/health", { signal: AbortSignal.timeout(3000) })
      .then((r) => r.json())
      .catch(() => ({ status: "down" })),
  queueStats: () => api<{ queues: Record<string, number> }>("/queues/stats").catch(() => null),
  getDashboardSummary: () => api<import("./types").DashboardSummary>("/dashboard/summary"),
  getAppMap: (appId: string) => api<import("./types").AppMapResponse>(`/apps/${appId}/appmap`),
  pageScreenshotUrl: (appId: string, pageId: string) =>
    `${API_BASE}/apps/${appId}/pages/${pageId}/screenshot`,
};

export const pipelineStreamBase = `${PIPELINE_API_BASE}/pipeline-runs`;
