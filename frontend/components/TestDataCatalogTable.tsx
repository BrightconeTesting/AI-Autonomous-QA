"use client";

import type { AppMapResponse, TestDataCatalogEntry } from "@/lib/types";

type Props = {
  appmap: AppMapResponse | null;
};

const TARGET_LABELS: Record<string, string> = {
  form: "Form",
  api_endpoint: "API endpoint",
  entity: "Data entity",
};

function targetLabel(entry: TestDataCatalogEntry): string {
  const kind = TARGET_LABELS[entry.target_type] || entry.target_type;
  return `${kind} · ${entry.target_id.slice(0, 8)}…`;
}

function formatConstraints(constraints: Record<string, unknown>): string {
  const parts: string[] = [];
  if (constraints.min_length != null) parts.push(`min ${constraints.min_length}`);
  if (constraints.max_length != null) parts.push(`max ${constraints.max_length}`);
  if (constraints.pattern) parts.push(`pattern ${String(constraints.pattern)}`);
  if (constraints.format) parts.push(String(constraints.format));
  return parts.join(", ") || "—";
}

export function TestDataCatalogTable({ appmap }: Props) {
  const catalog = appmap?.test_data_catalog ?? [];

  if (catalog.length === 0) {
    return (
      <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
        <h3 className="text-sm font-semibold text-[var(--text)]">Test data catalog</h3>
        <p className="mt-2 text-sm text-[var(--muted)]">
          No synthetic test values cataloged yet. Discovery builds this from form fields and API
          schemas when constrained inputs are detected.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="mb-3">
        <h3 className="text-sm font-semibold text-[var(--text)]">Test data catalog</h3>
        <p className="mt-1 text-xs text-[var(--muted)]">
          Safe sample values for automated tests — never live PII. Test design uses these for fill
          steps when available.
        </p>
      </div>

      <div className="space-y-4">
        {catalog.map((entry) => (
          <article
            key={entry.catalog_id}
            className="overflow-hidden rounded-lg border border-[var(--border)]"
          >
            <header className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] bg-[var(--bg)] px-3 py-2">
              <div>
                <p className="text-sm font-medium text-[var(--text)]">
                  {entry.context_label || targetLabel(entry)}
                </p>
                <p className="text-xs text-[var(--muted)]">
                  Strategy: {(entry.synthetic_strategy || "deterministic_fixture").replace(/_/g, " ")}
                  {entry.target_type === "form" && entry.unfilled_field_count != null && (
                    <> · {entry.unfilled_field_count} field(s) need test data</>
                  )}
                  {entry.reachable_via && entry.reachable_via.length > 0 && (
                    <> · Also via {entry.reachable_via.join(", ")}</>
                  )}
                </p>
              </div>
              <div className="flex flex-wrap gap-1">
                {entry.never_use_live_pii && (
                  <span className="rounded bg-green-500/15 px-2 py-0.5 text-[10px] font-medium text-green-300">
                    No live PII
                  </span>
                )}
                {entry.target_type === "form" && entry.filled_during_crawl && (
                  <span className="rounded bg-blue-500/15 px-2 py-0.5 text-[10px] font-medium text-blue-300">
                    Filled during crawl
                  </span>
                )}
              </div>
            </header>

            {entry.fields.length === 0 ? (
              <p className="px-3 py-2 text-sm text-[var(--muted)]">No fields cataloged.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[520px] text-left text-sm">
                  <thead>
                    <tr className="border-b border-[var(--border)] text-xs text-[var(--muted)]">
                      <th className="px-3 py-2 font-medium">Field</th>
                      <th className="px-3 py-2 font-medium">Type</th>
                      <th className="px-3 py-2 font-medium">Required</th>
                      <th className="px-3 py-2 font-medium">Safe test value</th>
                      <th className="px-3 py-2 font-medium">Status</th>
                      <th className="px-3 py-2 font-medium">Constraints</th>
                      <th className="px-3 py-2 font-medium">PII</th>
                    </tr>
                  </thead>
                  <tbody>
                    {entry.fields.map((field) => (
                      <tr
                        key={`${entry.catalog_id}-${field.name}`}
                        className="border-b border-[var(--border)]/50"
                      >
                        <td className="px-3 py-2 text-xs text-[var(--text)]">
                          <span className="font-medium">{field.display_name || field.name}</span>
                          {field.display_name && field.display_name !== field.name && (
                            <span className="mt-0.5 block font-mono text-[10px] text-[var(--muted)]">
                              {field.name}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-[var(--muted)]">{field.data_type}</td>
                        <td className="px-3 py-2 text-[var(--muted)]">
                          {field.required ? "Yes" : "No"}
                        </td>
                        <td className="px-3 py-2 font-mono text-xs text-green-300">
                          {field.suggested_safe_value && field.suggested_safe_value !== "***"
                            ? field.suggested_safe_value
                            : "—"}
                        </td>
                        <td className="px-3 py-2 text-xs">
                          {field.filled_during_crawl ? (
                            <span className="text-blue-300">Filled in crawl</span>
                          ) : field.needs_test_data !== false ? (
                            <span className="text-amber-300">Needs test data</span>
                          ) : (
                            <span className="text-[var(--muted)]">—</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-xs text-[var(--muted)]">
                          {formatConstraints(field.constraints || {})}
                        </td>
                        <td className="px-3 py-2 text-xs text-[var(--muted)]">
                          {field.pii_class || "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
