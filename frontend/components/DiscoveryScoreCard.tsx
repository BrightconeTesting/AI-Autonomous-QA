"use client";

import type { AppMapResponse, ScoringSummary } from "@/lib/types";

type Props = {
  appmap: AppMapResponse | null;
};

function metricBarColor(value: number, higherIsWorse: boolean): string {
  if (higherIsWorse) {
    if (value >= 70) return "bg-red-500";
    if (value >= 45) return "bg-amber-500";
    return "bg-green-500";
  }
  if (value >= 70) return "bg-green-500";
  if (value >= 45) return "bg-amber-500";
  return "bg-red-500";
}

function metricTextColor(value: number, higherIsWorse: boolean): string {
  if (higherIsWorse) {
    if (value >= 70) return "text-red-300";
    if (value >= 45) return "text-amber-300";
    return "text-green-400";
  }
  if (value >= 70) return "text-green-400";
  if (value >= 45) return "text-amber-300";
  return "text-red-300";
}

function MetricBar({
  label,
  value,
  higherIsWorse = false,
}: {
  label: string;
  value: number;
  higherIsWorse?: boolean;
}) {
  const fill = Math.max(0, Math.min(100, value));
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs">
        <span className="text-[var(--muted)]">{label}</span>
        <span className={metricTextColor(value, higherIsWorse)}>{value}</span>
      </div>
      <div className="h-2 overflow-hidden rounded bg-[var(--bg)]">
        <div
          className={`h-full rounded ${metricBarColor(value, higherIsWorse)}`}
          style={{ width: `${fill}%` }}
        />
      </div>
    </div>
  );
}

function CompletenessRing({ score }: { score: number }) {
  const radius = 36;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  return (
    <div className="relative flex h-24 w-24 items-center justify-center">
      <svg className="-rotate-90" width="96" height="96" viewBox="0 0 96 96">
        <circle cx="48" cy="48" r={radius} fill="none" stroke="var(--border)" strokeWidth="8" />
        <circle
          cx="48"
          cy="48"
          r={radius}
          fill="none"
          stroke={score >= 70 ? "#22c55e" : score >= 45 ? "#f59e0b" : "#ef4444"}
          strokeWidth="8"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
        />
      </svg>
      <span className="absolute text-lg font-semibold">{score}</span>
    </div>
  );
}

export function DiscoveryScoreCard({ appmap }: Props) {
  if (!appmap) return null;

  const summary: ScoringSummary | null | undefined = appmap.scoring_summary;
  const completeness =
    appmap.discovery_completeness_score ?? summary?.discovery_completeness_score ?? null;

  if (completeness == null && !summary) {
    return (
      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 text-sm text-[var(--muted)]">
        Discovery scores appear after AppMap v3 is built. Re-run crawl if missing.
      </div>
    );
  }

  const recommendations =
    appmap.recommendations?.length ? appmap.recommendations : summary?.recommendations ?? [];

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
      <p className="mb-3 text-sm font-medium">Discovery scores</p>
      <div className="grid gap-4 md:grid-cols-[auto_1fr]">
        {completeness != null && (
          <div className="flex flex-col items-center gap-1">
            <CompletenessRing score={completeness} />
            <span className="text-xs text-[var(--muted)]">Completeness</span>
          </div>
        )}
        {summary && (
          <div className="space-y-3">
            <MetricBar label="App risk" value={summary.app_risk_score} higherIsWorse />
            <MetricBar label="Testability" value={summary.app_testability_score} />
            <MetricBar
              label="Automation complexity"
              value={summary.app_automation_complexity_score}
              higherIsWorse
            />
          </div>
        )}
      </div>

      {summary && summary.top_risk_modules.length > 0 && (
        <div className="mt-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
            Top risk areas
          </p>
          <ul className="space-y-1 text-sm">
            {summary.top_risk_modules.slice(0, 5).map((item) => (
              <li
                key={item.module_id}
                className="flex justify-between rounded border border-[var(--border)] px-2 py-1"
              >
                <span>{item.name ?? item.module_id}</span>
                <span className={metricTextColor(item.risk_score, true)}>{item.risk_score}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {recommendations.length > 0 && (
        <div className="mt-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
            Recommendations
          </p>
          <ul className="list-inside list-disc text-xs text-[var(--muted)]">
            {recommendations.map((rec) => (
              <li key={rec}>{rec}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
