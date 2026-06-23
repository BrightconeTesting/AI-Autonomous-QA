"use client";

import { useMemo, useState, type CSSProperties } from "react";
import type { AppMapModule, AppMapPage, AppMapResponse } from "@/lib/types";

export type ModuleColorMode = "none" | "risk" | "testability" | "complexity";

type Props = {
  appmap: AppMapResponse | null;
  colorMode?: ModuleColorMode;
  onColorModeChange?: (mode: ModuleColorMode) => void;
};

type TreeNode = AppMapModule & { children: TreeNode[] };

const COLOR_MODES: { id: ModuleColorMode; label: string }[] = [
  { id: "none", label: "Default" },
  { id: "risk", label: "Risk" },
  { id: "testability", label: "Testability" },
  { id: "complexity", label: "Complexity" },
];

function buildTree(modules: AppMapModule[]): TreeNode[] {
  const nodes = new Map<string, TreeNode>();
  for (const mod of modules) {
    nodes.set(mod.module_id, { ...mod, children: [] });
  }
  const roots: TreeNode[] = [];
  for (const mod of modules) {
    const node = nodes.get(mod.module_id);
    if (!node) continue;
    const parentId = mod.parent_module_id;
    if (parentId && nodes.has(parentId)) {
      nodes.get(parentId)!.children.push(node);
    } else {
      roots.push(node);
    }
  }
  const sortNodes = (list: TreeNode[]) => {
    list.sort((a, b) => a.name.localeCompare(b.name));
    for (const node of list) sortNodes(node.children);
  };
  sortNodes(roots);
  return roots;
}

function moduleScore(mod: AppMapModule, mode: ModuleColorMode): number | null {
  if (mode === "risk") return mod.risk_score ?? null;
  if (mode === "testability") return mod.testability_score ?? null;
  if (mode === "complexity") return mod.automation_complexity_score ?? null;
  return null;
}

function heatmapStyle(score: number | null, mode: ModuleColorMode): CSSProperties {
  if (score == null || mode === "none") return {};
  const normalized = mode === "testability" ? score : 100 - score;
  const hue = Math.round((normalized / 100) * 120);
  return {
    borderLeft: `3px solid hsl(${hue}, 70%, 50%)`,
    backgroundColor: `hsla(${hue}, 60%, 45%, 0.08)`,
  };
}

function pageTitle(pageId: string, pages: AppMapPage[]): string {
  const page = pages.find((p) => p.page_id === pageId);
  if (!page) return pageId.slice(0, 8);
  if (page.title) return page.title;
  try {
    const path = new URL(page.url).pathname;
    return path.length > 1 ? path : page.url;
  } catch {
    return page.url;
  }
}

function ModuleNode({
  node,
  depth,
  pages,
  selectedId,
  colorMode,
  onSelect,
}: {
  node: TreeNode;
  depth: number;
  pages: AppMapPage[];
  selectedId: string | null;
  colorMode: ModuleColorMode;
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = useState(depth < 2);
  const hasChildren = node.children.length > 0;
  const isSelected = selectedId === node.module_id;
  const score = moduleScore(node, colorMode);

  return (
    <li>
      <div
        className={`flex items-center gap-2 rounded px-2 py-1 text-sm ${
          isSelected ? "bg-blue-500/15 text-blue-300" : "hover:bg-[var(--bg)]"
        }`}
        style={{ paddingLeft: `${depth * 12 + 8}px`, ...heatmapStyle(score, colorMode) }}
      >
        {hasChildren ? (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="w-4 text-[var(--muted)]"
            aria-label={open ? "Collapse" : "Expand"}
          >
            {open ? "▾" : "▸"}
          </button>
        ) : (
          <span className="w-4" />
        )}
        <button type="button" className="flex-1 text-left" onClick={() => onSelect(node.module_id)}>
          <span className="font-medium">{node.name}</span>
          <span className="ml-2 text-xs text-[var(--muted)]">
            {node.pages.length} pages · {node.features.length} features
          </span>
        </button>
        {score != null && colorMode !== "none" && (
          <span className="text-xs font-medium">{score}</span>
        )}
      </div>
      {open && hasChildren && (
        <ul>
          {node.children.map((child) => (
            <ModuleNode
              key={child.module_id}
              node={child}
              depth={depth + 1}
              pages={pages}
              selectedId={selectedId}
              colorMode={colorMode}
              onSelect={onSelect}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

export function ModuleTree({ appmap, colorMode = "none", onColorModeChange }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const modules = appmap?.modules ?? [];
  const tree = useMemo(() => buildTree(modules), [modules]);
  const selected = modules.find((m) => m.module_id === selectedId) ?? null;

  if (!appmap) {
    return <p className="text-sm text-[var(--muted)]">Loading modules…</p>;
  }

  if (modules.length === 0) {
    return (
      <p className="text-sm text-[var(--muted)]">
        No module tree yet. Re-run discovery to build AppMap v3 modules.
      </p>
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
            Module tree
          </p>
          {onColorModeChange && (
            <select
              value={colorMode}
              onChange={(e) => onColorModeChange(e.target.value as ModuleColorMode)}
              className="rounded border border-[var(--border)] bg-[var(--bg)] px-2 py-1 text-xs"
            >
              {COLOR_MODES.map((m) => (
                <option key={m.id} value={m.id}>
                  Color: {m.label}
                </option>
              ))}
            </select>
          )}
        </div>
        <ul>
          {tree.map((node) => (
            <ModuleNode
              key={node.module_id}
              node={node}
              depth={0}
              pages={appmap.pages}
              selectedId={selectedId}
              colorMode={colorMode}
              onSelect={setSelectedId}
            />
          ))}
        </ul>
      </div>
      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
        {selected ? (
          <div className="space-y-3 text-sm">
            <div>
              <p className="text-lg font-medium">{selected.name}</p>
              <p className="text-xs text-[var(--muted)]">module_id: {selected.module_id}</p>
              {selected.business_criticality && (
                <p className="mt-1 text-xs capitalize text-amber-300">
                  Criticality: {selected.business_criticality}
                </p>
              )}
            </div>
            {(selected.risk_score != null ||
              selected.testability_score != null ||
              selected.automation_complexity_score != null) && (
              <div className="grid grid-cols-3 gap-2 text-center text-xs">
                {selected.risk_score != null && (
                  <div className="rounded border border-[var(--border)] p-2">
                    <p className="text-[var(--muted)]">Risk</p>
                    <p className="text-lg font-semibold">{selected.risk_score}</p>
                  </div>
                )}
                {selected.testability_score != null && (
                  <div className="rounded border border-[var(--border)] p-2">
                    <p className="text-[var(--muted)]">Testability</p>
                    <p className="text-lg font-semibold">{selected.testability_score}</p>
                  </div>
                )}
                {selected.automation_complexity_score != null && (
                  <div className="rounded border border-[var(--border)] p-2">
                    <p className="text-[var(--muted)]">Complexity</p>
                    <p className="text-lg font-semibold">{selected.automation_complexity_score}</p>
                  </div>
                )}
              </div>
            )}
            <div>
              <p className="mb-1 font-medium">Pages</p>
              <ul className="list-inside list-disc text-[var(--muted)]">
                {selected.pages.map((pid) => (
                  <li key={pid}>{pageTitle(pid, appmap.pages)}</li>
                ))}
              </ul>
            </div>
            {selected.features.length > 0 && (
              <div>
                <p className="mb-1 font-medium">Features / flows</p>
                <ul className="space-y-1">
                  {selected.features.map((feature, index) => (
                    <li
                      key={`${feature.flow_id ?? feature.name}-${index}`}
                      className="rounded border border-[var(--border)] px-2 py-1"
                    >
                      {feature.name}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <p className="text-sm text-[var(--muted)]">Select a module to see pages and features.</p>
        )}
      </div>
    </div>
  );
}
