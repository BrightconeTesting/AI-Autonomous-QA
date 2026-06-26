"use client";

import { useCallback, useEffect, useState } from "react";
import { apiClient } from "@/lib/api";
import type { AppMapResponse, RecommendedTestArea } from "@/lib/types";

type Props = {
  appId: string;
  appmap: AppMapResponse | null;
};

export function RecommendedTestAreasEditor({ appId, appmap }: Props) {
  const areas = appmap?.recommended_test_areas ?? [];
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [localDecisions, setLocalDecisions] = useState<Record<string, string>>({});

  useEffect(() => {
    const initial: Record<string, string> = {};
    for (const area of areas) {
      const id = area.area_id;
      if (!id) continue;
      initial[id] = area.decision || "approved";
    }
    setLocalDecisions(initial);
  }, [areas]);

  const setDecision = useCallback(
    async (area: RecommendedTestArea, status: "approved" | "dismissed") => {
      const areaId = area.area_id;
      if (!areaId) return;
      setBusyId(areaId);
      setError(null);
      setLocalDecisions((prev) => ({ ...prev, [areaId]: status }));
      try {
        await apiClient.updateTestAreaDecisions(appId, [{ area_id: areaId, status }]);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to save decision");
        setLocalDecisions((prev) => ({ ...prev, [areaId]: area.decision || "approved" }));
      } finally {
        setBusyId(null);
      }
    },
    [appId]
  );

  if (areas.length === 0) {
    return (
      <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
        <h3 className="text-sm font-semibold text-[var(--text)]">Recommended test areas</h3>
        <p className="mt-2 text-sm text-[var(--muted)]">
          Discovery will suggest test areas when forms or mutating APIs are found. None were generated
          for this crawl yet.
        </p>
      </section>
    );
  }

  const approvedCount = areas.filter((area) => (localDecisions[area.area_id] || "approved") === "approved").length;

  return (
    <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-[var(--text)]">Recommended test areas</h3>
          <p className="mt-1 text-xs text-[var(--muted)]">
            Approve areas to include in test generation, or dismiss ones you do not want covered.
          </p>
        </div>
        <span className="text-xs text-[var(--muted)]">
          {approvedCount} approved · {areas.length - approvedCount} dismissed
        </span>
      </div>

      {error && <p className="mb-3 text-sm text-red-300">{error}</p>}

      <ul className="space-y-2">
        {areas
          .slice()
          .sort((a, b) => (b.priority_index ?? 0) - (a.priority_index ?? 0))
          .map((area) => {
            const decision = localDecisions[area.area_id] || area.decision || "approved";
            const dismissed = decision === "dismissed";
            return (
              <li
                key={area.area_id}
                className={`rounded-lg border p-3 ${
                  dismissed
                    ? "border-[var(--border)]/60 opacity-60"
                    : "border-[var(--border)]"
                }`}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-[var(--text)]">{area.area}</span>
                      {area.priority && (
                        <span className="rounded bg-blue-600/20 px-2 py-0.5 text-[10px] uppercase text-blue-300">
                          {area.priority}
                        </span>
                      )}
                      {area.area_type && (
                        <span className="rounded bg-[var(--bg)] px-2 py-0.5 text-[10px] text-[var(--muted)]">
                          {area.area_type.replace(/_/g, " ")}
                        </span>
                      )}
                    </div>
                    {area.rationale && (
                      <p className="mt-1 text-xs text-[var(--muted)]">{area.rationale}</p>
                    )}
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <button
                      type="button"
                      disabled={busyId === area.area_id || !dismissed}
                      onClick={() => setDecision(area, "approved")}
                      className="rounded border border-green-500/40 px-2 py-1 text-xs text-green-300 disabled:opacity-40"
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      disabled={busyId === area.area_id || dismissed}
                      onClick={() => setDecision(area, "dismissed")}
                      className="rounded border border-red-500/40 px-2 py-1 text-xs text-red-300 disabled:opacity-40"
                    >
                      Dismiss
                    </button>
                  </div>
                </div>
              </li>
            );
          })}
      </ul>
    </section>
  );
}
