"use client";

import type { AppMapResponse } from "@/lib/types";

type Props = {
  appmap: AppMapResponse | null;
};

export function AppMapStatsStrip({ appmap }: Props) {
  if (!appmap) {
    return (
      <p className="text-sm text-[var(--muted)]">
        No AppMap yet — run a crawl from Overview to discover structure.
      </p>
    );
  }

  const { stats } = appmap;
  const chips: string[] = [
    `${stats.page_count} pages`,
    `${stats.flow_count} flows`,
  ];
  if (stats.module_count != null) {
    chips.push(`${stats.module_count} modules`);
  }
  if (stats.state_count > 0) {
    chips.push(`${stats.state_count} states`);
  }
  if (appmap.discovery_completeness_score != null) {
    chips.push(`${appmap.discovery_completeness_score}% complete`);
  }
  if (appmap.schema_version >= 3) {
    chips.push(`v${appmap.schema_version}`);
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {chips.map((chip) => (
        <span
          key={chip}
          className="rounded-full border border-[var(--border)] bg-[var(--surface)] px-2.5 py-0.5 text-xs text-[var(--muted)]"
        >
          {chip}
        </span>
      ))}
    </div>
  );
}
