"use client";

import type { DiscoverySummaryResponse } from "@/lib/types";

type Props = {
  summary: DiscoverySummaryResponse | null;
  loading?: boolean;
};

function CountGrid({ counts }: { counts: DiscoverySummaryResponse["counts"] }) {
  const items = [
    { label: "Pages", value: counts.pages },
    { label: "Flows", value: counts.flows },
    { label: "Modules", value: counts.modules },
    { label: "Buttons", value: counts.buttons },
    { label: "Forms", value: counts.forms },
    { label: "Links", value: counts.links },
    { label: "APIs", value: counts.api_endpoints },
    { label: "SPA routes", value: counts.spa_routes },
  ];

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {items.map((item) => (
        <div key={item.label} className="rounded border border-[var(--border)] bg-[var(--bg)] px-3 py-2">
          <p className="text-xs text-[var(--muted)]">{item.label}</p>
          <p className="text-lg font-semibold">{item.value}</p>
        </div>
      ))}
    </div>
  );
}

function Skeleton() {
  return (
    <div className="animate-pulse space-y-3">
      <div className="grid grid-cols-4 gap-2">
        {Array.from({ length: 8 }).map((_, index) => (
          <div key={index} className="h-14 rounded bg-[var(--border)]/40" />
        ))}
      </div>
      <div className="h-20 rounded bg-[var(--border)]/30" />
      <div className="h-16 rounded bg-[var(--border)]/30" />
    </div>
  );
}

export function DiscoverySummaryPanel({ summary, loading = false }: Props) {
  if (loading) {
    return (
      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
        <p className="mb-3 text-sm font-medium">Discovery summary</p>
        <Skeleton />
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
        <p className="text-sm text-[var(--muted)]">
          Run a crawl to generate a discovery summary for this application.
        </p>
      </div>
    );
  }

  const completeness = summary.discovery_completeness_score;

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium">Discovery summary</p>
        <span
          className={`text-xs ${
            completeness >= 70
              ? "text-green-400"
              : completeness >= 45
                ? "text-amber-300"
                : "text-red-300"
          }`}
        >
          {completeness}% complete
        </span>
      </div>

      <CountGrid counts={summary.counts} />

      {summary.what_should_be_tested_first.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
            Test first
          </p>
          <ul className="list-inside list-disc space-y-1 text-sm">
            {summary.what_should_be_tested_first.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {summary.top_risk_areas.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
            Top risk areas
          </p>
          <ul className="space-y-1 text-sm">
            {summary.top_risk_areas.map((area) => (
              <li
                key={`${area.module}-${area.top_factor}`}
                className="flex flex-wrap items-center justify-between gap-2 rounded border border-[var(--border)] bg-[var(--bg)] px-3 py-2"
              >
                <span>{area.module}</span>
                <span className="text-xs text-[var(--muted)]">
                  risk {area.risk_score} · {area.top_factor.replace(/_/g, " ")}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {summary.what_pages_exist.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
            Pages discovered
          </p>
          <p className="text-sm text-[var(--muted)]">
            {summary.what_pages_exist.slice(0, 12).join(" · ")}
            {summary.what_pages_exist.length > 12 &&
              ` · +${summary.what_pages_exist.length - 12} more`}
          </p>
        </div>
      )}

      {summary.what_forms_exist.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
            Forms
          </p>
          <ul className="space-y-1 text-sm">
            {summary.what_forms_exist.slice(0, 6).map((form) => (
              <li key={`${form.page}-${form.name}`}>
                {form.name} <span className="text-[var(--muted)]">({form.page})</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {summary.recommendations.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
            Recommendations
          </p>
          <ul className="list-inside list-disc space-y-1 text-sm text-amber-200/90">
            {summary.recommendations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {summary.module_tree.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
            Module tree
          </p>
          <ul className="space-y-2 text-sm">
            {summary.module_tree.map((node) => (
              <li key={node.name}>
                <span className="font-medium">{node.name}</span>
                {node.children.length > 0 && (
                  <span className="text-[var(--muted)]"> — {node.children.join(", ")}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
