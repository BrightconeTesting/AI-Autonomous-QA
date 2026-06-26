"use client";

import type {
  ApiFlowColorMode,
  ApiFlowDepthFilter,
  ApiFlowLayoutMode,
} from "@/lib/apiFlowUtils";

type Props = {
  view: "guide" | "diagram";
  onViewChange: (view: "guide" | "diagram") => void;
  depthFilter: ApiFlowDepthFilter;
  onDepthFilterChange: (value: ApiFlowDepthFilter) => void;
  layoutMode: ApiFlowLayoutMode;
  onLayoutModeChange: (value: ApiFlowLayoutMode) => void;
  colorMode: ApiFlowColorMode;
  onColorModeChange: (value: ApiFlowColorMode) => void;
  search: string;
  onSearchChange: (value: string) => void;
  qaOverlay: boolean;
  onQaOverlayChange: (value: boolean) => void;
  visibleCount: number;
  totalCount: number;
  selectedNodeId: string | null;
  onCenterSelected: () => void;
};

export function ApiFlowToolbar({
  view,
  onViewChange,
  depthFilter,
  onDepthFilterChange,
  layoutMode,
  onLayoutModeChange,
  colorMode,
  onColorModeChange,
  search,
  onSearchChange,
  qaOverlay,
  onQaOverlayChange,
  visibleCount,
  totalCount,
  selectedNodeId,
  onCenterSelected,
}: Props) {
  return (
    <div className="space-y-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-[var(--text)]">API flow</h3>
          <p className="text-xs text-[var(--muted)]">
            Showing {visibleCount} of {totalCount} APIs
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onViewChange("guide")}
            className={`rounded px-3 py-1.5 text-xs ${
              view === "guide" ? "bg-blue-600 text-white" : "border border-[var(--border)] text-[var(--muted)]"
            }`}
          >
            Simple guide
          </button>
          <button
            type="button"
            onClick={() => onViewChange("diagram")}
            className={`rounded px-3 py-1.5 text-xs ${
              view === "diagram" ? "bg-blue-600 text-white" : "border border-[var(--border)] text-[var(--muted)]"
            }`}
          >
            Visual diagram
          </button>
        </div>
      </div>

      {view === "diagram" && (
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="search"
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search path, method, module…"
            className="min-w-[200px] flex-1 rounded border border-[var(--border)] bg-[var(--bg)] px-3 py-1.5 text-xs text-[var(--text)]"
          />
          <select
            value={depthFilter}
            onChange={(event) => onDepthFilterChange(event.target.value as ApiFlowDepthFilter)}
            className="rounded border border-[var(--border)] bg-[var(--bg)] px-2 py-1.5 text-xs text-[var(--text)]"
          >
            <option value="all">All depths</option>
            <option value="0">Depth 0 — Entry</option>
            <option value="1">Depth 1</option>
            <option value="2">Depth 2</option>
            <option value="3+">Depth 3+</option>
          </select>
          <select
            value={layoutMode}
            onChange={(event) => onLayoutModeChange(event.target.value as ApiFlowLayoutMode)}
            className="rounded border border-[var(--border)] bg-[var(--bg)] px-2 py-1.5 text-xs text-[var(--text)]"
          >
            <option value="dag">Layout: DAG</option>
            <option value="module">Layout: Module groups</option>
          </select>
          <select
            value={colorMode}
            onChange={(event) => onColorModeChange(event.target.value as ApiFlowColorMode)}
            className="rounded border border-[var(--border)] bg-[var(--bg)] px-2 py-1.5 text-xs text-[var(--text)]"
          >
            <option value="default">Color: default</option>
            <option value="risk">Color: risk</option>
            <option value="complexity">Color: complexity</option>
          </select>
          <label className="flex items-center gap-2 text-xs text-[var(--muted)]">
            <input
              type="checkbox"
              checked={qaOverlay}
              onChange={(event) => onQaOverlayChange(event.target.checked)}
            />
            QA overlays
          </label>
          {selectedNodeId && (
            <button
              type="button"
              onClick={onCenterSelected}
              className="rounded border border-[var(--border)] px-2 py-1.5 text-xs text-[var(--text)]"
            >
              Center selected
            </button>
          )}
        </div>
      )}
    </div>
  );
}
