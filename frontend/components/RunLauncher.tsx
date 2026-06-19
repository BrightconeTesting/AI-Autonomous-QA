"use client";

type Props = {
  selectedCount: number;
  filteredCount: number;
  busy: boolean;
  canRun: boolean;
  disabledReason?: string | null;
  onRun: () => void;
  onExport: () => void;
  onSelectAll: () => void;
  onClearSelection: () => void;
};

export function RunLauncher({
  selectedCount,
  filteredCount,
  busy,
  canRun,
  disabledReason,
  onRun,
  onExport,
  onSelectAll,
  onClearSelection,
}: Props) {
  const runBlocked = busy || !canRun || selectedCount === 0;
  const runHint =
    selectedCount === 0 && canRun
      ? "Select scenarios below, then click Run."
      : disabledReason;

  return (
    <div className="sticky top-0 z-10 space-y-2 rounded-lg border border-[var(--border)] bg-[var(--bg)]/95 p-3 backdrop-blur">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={runBlocked}
          onClick={onRun}
          title={runHint ?? undefined}
          className={`rounded px-4 py-2 text-sm font-medium ${
            runBlocked
              ? "cursor-not-allowed border border-[var(--border)] bg-[var(--surface)] text-[var(--muted)]"
              : "bg-blue-600 text-white hover:bg-blue-500"
          }`}
        >
          ▶ Run selected ({selectedCount})
        </button>
        <button
          type="button"
          disabled={busy || filteredCount === 0}
          onClick={onSelectAll}
          className="rounded border border-[var(--border)] px-3 py-2 text-sm disabled:opacity-50"
        >
          Select all ({filteredCount})
        </button>
        <button
          type="button"
          disabled={selectedCount === 0}
          onClick={onClearSelection}
          className="rounded border border-[var(--border)] px-3 py-2 text-sm disabled:opacity-50"
        >
          Clear
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onExport}
          className="rounded border border-[var(--border)] px-3 py-2 text-sm disabled:opacity-50"
        >
          Export .feature
        </button>
      </div>
      {runHint && (
        <p className="text-xs text-amber-400/90">{runHint}</p>
      )}
    </div>
  );
}
