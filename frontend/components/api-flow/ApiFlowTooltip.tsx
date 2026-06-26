"use client";

import type { ApiFlowNodeData } from "@/lib/apiFlowLayout";

type Props = {
  data: ApiFlowNodeData | null;
  position: { x: number; y: number } | null;
};

export function ApiFlowTooltip({ data, position }: Props) {
  if (!data || !position || data.isCollapsedSummary) return null;

  return (
    <div
      className="pointer-events-none absolute z-50 w-64 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3 text-xs shadow-xl"
      style={{ left: position.x + 12, top: position.y + 12 }}
    >
      <div className="font-semibold text-[var(--text)]">
        {data.method} {data.path}
      </div>
      <dl className="mt-2 space-y-1 text-[var(--muted)]">
        <div className="flex justify-between gap-2">
          <dt>Depth</dt>
          <dd className="text-[var(--text)]">D{data.depth}</dd>
        </div>
        {data.moduleName && (
          <div className="flex justify-between gap-2">
            <dt>Module</dt>
            <dd className="text-[var(--text)]">{data.moduleName}</dd>
          </div>
        )}
        {data.riskScore != null && (
          <div className="flex justify-between gap-2">
            <dt>Risk</dt>
            <dd className="text-[var(--text)]">
              {data.riskScore}
              {data.riskTier ? ` (${data.riskTier})` : ""}
            </dd>
          </div>
        )}
        <div className="flex justify-between gap-2">
          <dt>Auth</dt>
          <dd className="text-[var(--text)]">
            {data.requiresAuth || data.isAuthSource ? "Required" : "Public"}
          </dd>
        </div>
        {data.seenCount != null && (
          <div className="flex justify-between gap-2">
            <dt>Call frequency</dt>
            <dd className="text-[var(--text)]">{data.seenCount}</dd>
          </div>
        )}
        <div className="flex justify-between gap-2">
          <dt>Response codes</dt>
          <dd className="text-[var(--text)]">—</dd>
        </div>
      </dl>
    </div>
  );
}
