"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiClient } from "@/lib/api";
import type { AppMapDiffResponse, DiscoverRunSummary } from "@/lib/types";

type Props = {
  appId: string;
  defaultToRunId?: string | null;
};

function DiffSection({
  title,
  children,
  empty,
}: {
  title: string;
  children: React.ReactNode;
  empty?: boolean;
}) {
  if (empty) return null;
  return (
    <section className="rounded border border-[var(--border)] bg-[var(--surface)] p-3">
      <h4 className="mb-2 text-sm font-medium">{title}</h4>
      <div className="space-y-1 text-sm text-[var(--muted)]">{children}</div>
    </section>
  );
}

export function AppMapDiffPanel({ appId, defaultToRunId }: Props) {
  const [runs, setRuns] = useState<DiscoverRunSummary[]>([]);
  const [fromRunId, setFromRunId] = useState("");
  const [toRunId, setToRunId] = useState(defaultToRunId || "");
  const [diff, setDiff] = useState<AppMapDiffResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .listDiscoverRuns(appId)
      .then((response) => {
        if (cancelled) return;
        const items = response.items.filter((item) => item.has_artifact);
        setRuns(items);
        if (items.length >= 2) {
          setFromRunId(items[1].pipeline_run_id);
          setToRunId(defaultToRunId || items[0].pipeline_run_id);
        } else if (items.length === 1) {
          setToRunId(items[0].pipeline_run_id);
        }
      })
      .catch(() => {
        if (!cancelled) setRuns([]);
      });
    return () => {
      cancelled = true;
    };
  }, [appId, defaultToRunId]);

  const canCompare = fromRunId && toRunId && fromRunId !== toRunId;

  const loadDiff = useCallback(async () => {
    if (!canCompare) return;
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.getAppMapDiff(appId, fromRunId, toRunId);
      setDiff(response);
    } catch (err) {
      setDiff(null);
      setError(err instanceof Error ? err.message : "Failed to load diff");
    } finally {
      setLoading(false);
    }
  }, [appId, canCompare, fromRunId, toRunId]);

  const runLabel = useMemo(() => {
    const map = new Map(runs.map((run) => [run.pipeline_run_id, run]));
    return (runId: string) => {
      const run = map.get(runId);
      if (!run) return runId.slice(0, 8);
      const when = run.started_at ? new Date(run.started_at).toLocaleString() : runId.slice(0, 8);
      const pages = run.page_count != null ? `${run.page_count} pages` : "discover run";
      return `${when} · ${pages}`;
    };
  }, [runs]);

  return (
    <div className="space-y-4 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
      <div>
        <h3 className="text-sm font-medium">AppMap diff</h3>
        <p className="text-xs text-[var(--muted)]">
          Compare two completed discovery runs to see pages, APIs, modules, and score changes.
        </p>
      </div>

      {runs.length < 2 ? (
        <p className="text-sm text-[var(--muted)]">
          Run discovery at least twice to compare AppMap snapshots between pipeline runs.
        </p>
      ) : (
        <>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1 text-xs">
              <span className="text-[var(--muted)]">From run</span>
              <select
                value={fromRunId}
                onChange={(e) => setFromRunId(e.target.value)}
                className="w-full rounded border border-[var(--border)] bg-[var(--bg)] px-2 py-1.5 text-sm"
              >
                {runs.map((run) => (
                  <option key={run.pipeline_run_id} value={run.pipeline_run_id}>
                    {runLabel(run.pipeline_run_id)}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1 text-xs">
              <span className="text-[var(--muted)]">To run</span>
              <select
                value={toRunId}
                onChange={(e) => setToRunId(e.target.value)}
                className="w-full rounded border border-[var(--border)] bg-[var(--bg)] px-2 py-1.5 text-sm"
              >
                {runs.map((run) => (
                  <option key={run.pipeline_run_id} value={run.pipeline_run_id}>
                    {runLabel(run.pipeline_run_id)}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <button
            type="button"
            disabled={!canCompare || loading}
            onClick={() => loadDiff()}
            className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            {loading ? "Comparing…" : "Compare runs"}
          </button>
        </>
      )}

      {error && <p className="text-sm text-red-300">{error}</p>}

      {diff && (
        <div className="space-y-3">
          <p className="text-sm">
            {diff.unchanged ? (
              <span className="text-green-400">No structural changes detected.</span>
            ) : (
              <span>
                Changes from <code className="text-xs">{diff.from_appmap_hash?.slice(0, 12) || "—"}</code>{" "}
                to <code className="text-xs">{diff.to_appmap_hash?.slice(0, 12) || "—"}</code>
              </span>
            )}
          </p>

          <DiffSection title="Pages added" empty={diff.pages.added.length === 0}>
            {diff.pages.added.map((page) => (
              <div key={page.page_id}>+ {page.title || page.url}</div>
            ))}
          </DiffSection>
          <DiffSection title="Pages removed" empty={diff.pages.removed.length === 0}>
            {diff.pages.removed.map((page) => (
              <div key={page.page_id}>- {page.title || page.url}</div>
            ))}
          </DiffSection>
          <DiffSection title="Pages changed" empty={diff.pages.changed.length === 0}>
            {diff.pages.changed.map((page) => (
              <div key={page.page_id}>
                ~ {page.title || page.url} ({page.changed_fields.join(", ")})
              </div>
            ))}
          </DiffSection>
          <DiffSection title="Element count changes" empty={diff.elements.delta_by_page.length === 0}>
            {diff.elements.delta_by_page.map((item) => (
              <div key={item.page_id}>
                {item.page_id.slice(0, 8)}: {item.from_count} → {item.to_count} ({item.delta >= 0 ? "+" : ""}
                {item.delta})
              </div>
            ))}
          </DiffSection>
          <DiffSection title="API endpoints added" empty={diff.api_endpoints.added.length === 0}>
            {diff.api_endpoints.added.map((item) => (
              <div key={`${item.method}:${item.path}`}>
                + {item.method} {item.path}
              </div>
            ))}
          </DiffSection>
          <DiffSection title="API endpoints removed" empty={diff.api_endpoints.removed.length === 0}>
            {diff.api_endpoints.removed.map((item) => (
              <div key={`${item.method}:${item.path}`}>
                - {item.method} {item.path}
              </div>
            ))}
          </DiffSection>
          <DiffSection
            title="API dependency edges added"
            empty={(diff.api_dependency_graph?.edges_added?.length ?? 0) === 0}
          >
            {(diff.api_dependency_graph?.edges_added ?? []).map((edge) => (
              <div key={`${edge.from_endpoint_id}-${edge.to_endpoint_id}-${edge.edge_type}`}>
                + {edge.edge_type}: {edge.from_endpoint_id.slice(0, 8)} → {edge.to_endpoint_id.slice(0, 8)}
              </div>
            ))}
          </DiffSection>
          <DiffSection
            title="API dependency edges removed"
            empty={(diff.api_dependency_graph?.edges_removed?.length ?? 0) === 0}
          >
            {(diff.api_dependency_graph?.edges_removed ?? []).map((edge) => (
              <div key={`${edge.from_endpoint_id}-${edge.to_endpoint_id}-${edge.edge_type}`}>
                - {edge.edge_type}: {edge.from_endpoint_id.slice(0, 8)} → {edge.to_endpoint_id.slice(0, 8)}
              </div>
            ))}
          </DiffSection>
          <DiffSection title="Module changes" empty={!diff.modules.added.length && !diff.modules.removed.length && !diff.modules.changed.length}>
            {diff.modules.added.map((item) => (
              <div key={item.module_id}>+ module {item.name}</div>
            ))}
            {diff.modules.removed.map((item) => (
              <div key={item.module_id}>- module {item.name}</div>
            ))}
            {diff.modules.changed.map((item) => (
              <div key={item.module_id}>
                ~ {item.name} ({item.changed_fields.join(", ")})
              </div>
            ))}
          </DiffSection>
          <DiffSection title="Score deltas" empty={Object.keys(diff.scores).length === 0}>
            {Object.entries(diff.scores).map(([name, value]) => (
              <div key={name}>
                {name}: {value.from} → {value.to} ({value.delta >= 0 ? "+" : ""}
                {value.delta})
              </div>
            ))}
          </DiffSection>
          <DiffSection
            title="Recommended test areas"
            empty={!diff.recommended_test_areas.added.length && !diff.recommended_test_areas.removed.length}
          >
            {diff.recommended_test_areas.added.map((item) => (
              <div key={item.area_id}>+ {item.area}</div>
            ))}
            {diff.recommended_test_areas.removed.map((item) => (
              <div key={item.area_id}>- {item.area}</div>
            ))}
          </DiffSection>
        </div>
      )}
    </div>
  );
}
