"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";
import { formatBytes } from "@/lib/settings";
import type { DashboardSummary } from "@/lib/types";

export function MetricsPanel() {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiClient
      .getDashboardSummary()
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load metrics"));
  }, []);

  if (error) {
    return (
      <p className="text-sm text-red-400">
        Metrics unavailable — is the API running? ({error})
      </p>
    );
  }

  if (!data) {
    return <p className="text-sm text-[var(--muted)]">Loading metrics…</p>;
  }

  const cards = [
    { label: "Applications", value: data.app_count },
    { label: "Total runs", value: data.total_runs },
    { label: "Passed", value: data.total_passed, className: "text-green-400" },
    { label: "Failed", value: data.total_failed, className: "text-red-400" },
    { label: "Storage used", value: formatBytes(data.storage_bytes) },
  ];

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {cards.map((c) => (
          <div
            key={c.label}
            className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4"
          >
            <p className="text-xs text-[var(--muted)]">{c.label}</p>
            <p className={`text-2xl font-semibold ${c.className ?? ""}`}>{c.value}</p>
          </div>
        ))}
      </div>

      <section>
        <h2 className="mb-3 text-lg font-medium">Recent runs</h2>
        {data.recent_runs.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">No test runs yet.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
            <table className="w-full text-sm">
              <thead className="border-b border-[var(--border)] bg-[var(--surface)] text-left text-[var(--muted)]">
                <tr>
                  <th className="px-4 py-2">App</th>
                  <th className="px-4 py-2">Run</th>
                  <th className="px-4 py-2">Status</th>
                  <th className="px-4 py-2">Passed</th>
                  <th className="px-4 py-2">Failed</th>
                  <th className="px-4 py-2">Started</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {data.recent_runs.map((run) => (
                  <tr key={run.run_id} className="hover:bg-[var(--surface)]">
                    <td className="px-4 py-2">
                      <Link href={`/apps/${run.app_id}`} className="text-blue-400 hover:underline">
                        {run.app_name}
                      </Link>
                    </td>
                    <td className="px-4 py-2">
                      <Link
                        href={`/runs/${run.run_id}`}
                        className="font-mono text-xs text-blue-400 hover:underline"
                      >
                        {run.run_id.slice(0, 8)}…
                      </Link>
                    </td>
                    <td className="px-4 py-2 capitalize">{run.status}</td>
                    <td className="px-4 py-2 text-green-400">{run.summary.passed}</td>
                    <td className="px-4 py-2 text-red-400">{run.summary.failed}</td>
                    <td className="px-4 py-2 text-[var(--muted)]">
                      {run.started_at ? new Date(run.started_at).toLocaleString() : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
