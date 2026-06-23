"use client";

import { useMemo } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { AppMapFlow, AppMapModule, AppMapResponse } from "@/lib/types";
import type { ModuleColorMode } from "@/components/ModuleTree";

type Props = {
  appmap: AppMapResponse | null;
  moduleColorMode?: ModuleColorMode;
};

const MODULE_PALETTE = [
  "#3b82f6",
  "#22c55e",
  "#a855f7",
  "#f59e0b",
  "#ec4899",
  "#14b8a6",
  "#f97316",
  "#6366f1",
];

function pageLabel(url: string, title: string | null): string {
  if (title) return title;
  try {
    const path = new URL(url).pathname;
    return path.length > 1 ? path : url;
  } catch {
    return url;
  }
}

function moduleColor(moduleId: string, index: number): string {
  let hash = 0;
  for (let i = 0; i < moduleId.length; i++) hash = (hash + moduleId.charCodeAt(i) * 17) % MODULE_PALETTE.length;
  return MODULE_PALETTE[(hash + index) % MODULE_PALETTE.length];
}

function pageModuleMap(modules: AppMapModule[]): Map<string, AppMapModule> {
  const map = new Map<string, AppMapModule>();
  for (const mod of modules) {
    for (const pageId of mod.pages) {
      map.set(pageId, mod);
    }
  }
  return map;
}

function resolveNavigatePageId(
  step: Record<string, unknown>,
  pages: AppMapResponse["pages"]
): string | null {
  const pageId = step.page_id;
  if (pageId) return String(pageId);
  const url = String(step.url ?? step.target ?? "");
  if (!url) return null;
  const page = pages.find((p) => p.url === url || url.includes(p.url) || p.url.includes(url));
  return page?.page_id ?? null;
}

function moduleHeatColor(mod: AppMapModule, mode: ModuleColorMode, index: number): string {
  if (mode === "none") return moduleColor(mod.module_id, index);
  const score =
    mode === "risk"
      ? mod.risk_score
      : mode === "testability"
        ? mod.testability_score
        : mod.automation_complexity_score;
  if (score == null) return moduleColor(mod.module_id, index);
  const normalized = mode === "testability" ? score : 100 - score;
  const hue = Math.round((normalized / 100) * 120);
  return `hsl(${hue}, 65%, 50%)`;
}

function buildModuleLayout(
  appmap: AppMapResponse,
  modules: AppMapModule[],
  moduleColorMode: ModuleColorMode
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const edgeSet = new Set<string>();
  const pageByModule = pageModuleMap(modules);
  const assignedPages = new Set<string>();

  const columnWidth = 280;
  const moduleHeaderHeight = 56;
  const pageRowHeight = 96;
  const modulePadding = 16;

  modules.forEach((mod, colIndex) => {
    const color = moduleHeatColor(mod, moduleColorMode, colIndex);
    const modulePages = mod.pages
      .map((id) => appmap.pages.find((p) => p.page_id === id))
      .filter((p): p is NonNullable<typeof p> => Boolean(p));

    if (modulePages.length === 0) return;

    const groupHeight =
      moduleHeaderHeight + modulePadding + modulePages.length * pageRowHeight + modulePadding;
    const groupId = `module-${mod.module_id}`;

    nodes.push({
      id: groupId,
      type: "default",
      position: { x: colIndex * columnWidth, y: 0 },
      data: {
        label: (
          <div className="text-xs">
            <div className="font-semibold">{mod.name}</div>
            <div className="text-[var(--muted)]">
              {modulePages.length} pages · {mod.features.length} features
            </div>
          </div>
        ),
      },
      style: {
        width: columnWidth - 24,
        height: groupHeight,
        background: `${color}18`,
        border: `2px solid ${color}`,
        borderRadius: 12,
        padding: 8,
        color: "var(--text)",
      },
      draggable: true,
      selectable: true,
    });

    modulePages.forEach((page, rowIndex) => {
      assignedPages.add(page.page_id);
      nodes.push({
        id: page.page_id,
        parentId: groupId,
        extent: "parent",
        position: { x: modulePadding, y: moduleHeaderHeight + rowIndex * pageRowHeight },
        data: {
          label: (
            <div className="text-xs">
              <div className="font-medium">{pageLabel(page.url, page.title)}</div>
              <div className="max-w-[200px] truncate text-[var(--muted)]">{page.url}</div>
            </div>
          ),
        },
        style: {
          width: columnWidth - 48,
          background: "var(--surface)",
          border: `1px solid ${color}88`,
          borderRadius: 8,
          padding: 8,
          color: "var(--text)",
        },
        draggable: true,
      });
    });
  });

  const unassigned = appmap.pages.filter((p) => !assignedPages.has(p.page_id));
  if (unassigned.length > 0) {
    const colIndex = modules.length;
    const groupId = "module-unassigned";
    const groupHeight =
      moduleHeaderHeight + modulePadding + unassigned.length * pageRowHeight + modulePadding;
    nodes.push({
      id: groupId,
      type: "default",
      position: { x: colIndex * columnWidth, y: 0 },
      data: {
        label: (
          <div className="text-xs">
            <div className="font-semibold">Other pages</div>
            <div className="text-[var(--muted)]">{unassigned.length} ungrouped</div>
          </div>
        ),
      },
      style: {
        width: columnWidth - 24,
        height: groupHeight,
        background: "var(--surface)",
        border: "2px dashed var(--border)",
        borderRadius: 12,
        padding: 8,
      },
    });
    unassigned.forEach((page, rowIndex) => {
      nodes.push({
        id: page.page_id,
        parentId: groupId,
        extent: "parent",
        position: { x: modulePadding, y: moduleHeaderHeight + rowIndex * pageRowHeight },
        data: {
          label: (
            <div className="text-xs">
              <div className="font-medium">{pageLabel(page.url, page.title)}</div>
            </div>
          ),
        },
        style: {
          width: columnWidth - 48,
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: 8,
        },
      });
    });
  }

  addGraphEdges(appmap, edges, edgeSet);
  return { nodes, edges };
}

function buildFlatLayout(appmap: AppMapResponse): { nodes: Node[]; edges: Edge[] } {
  const cols = Math.ceil(Math.sqrt(appmap.pages.length));
  const nodes: Node[] = appmap.pages.map((page, i) => ({
    id: page.page_id,
    type: "default",
    position: { x: (i % cols) * 220, y: Math.floor(i / cols) * 120 },
    data: {
      label: (
        <div className="text-xs">
          <div className="font-medium">{pageLabel(page.url, page.title)}</div>
          <div className="max-w-[180px] truncate text-[var(--muted)]">{page.url}</div>
        </div>
      ),
    },
    style: {
      background: "var(--surface)",
      border: "1px solid var(--border)",
      borderRadius: 8,
      padding: 8,
      width: 200,
      color: "var(--text)",
    },
  }));

  const edges: Edge[] = [];
  addGraphEdges(appmap, edges, new Set());
  return { nodes, edges };
}

function addGraphEdges(appmap: AppMapResponse, flowEdges: Edge[], edgeSet: Set<string>) {
  const statePage = new Map(appmap.states.map((s) => [s.state_id, s.page_id]));

  for (const nav of appmap.navigation_graph ?? []) {
    const from = nav.from_page_id;
    const to = nav.to_page_id;
    if (!from || !to || from === to) continue;
    const key = `nav-${from}->${to}`;
    if (edgeSet.has(key)) continue;
    edgeSet.add(key);
    flowEdges.push({
      id: key,
      source: from,
      target: to,
      label: nav.label?.slice(0, 20) || nav.via || "nav",
      animated: nav.via === "interaction",
      style: { stroke: nav.via === "interaction" ? "#f59e0b" : "#60a5fa" },
    });
  }

  for (const t of appmap.transitions) {
    const fromPage = statePage.get(t.from_state_id);
    const toPage = statePage.get(t.to_state_id);
    if (!fromPage || !toPage || fromPage === toPage) continue;
    const key = `cic-${fromPage}->${toPage}`;
    if (edgeSet.has(key)) continue;
    edgeSet.add(key);
    flowEdges.push({
      id: key,
      source: fromPage,
      target: toPage,
      animated: true,
      label: "CIC",
      style: { stroke: "#a855f7" },
    });
  }

  for (const flow of appmap.flows) {
    let prevPageId: string | null = null;
    for (const step of flow.steps) {
      if (String(step.action) !== "navigate") continue;
      const pageId = resolveNavigatePageId(step, appmap.pages);
      if (!pageId) continue;
      if (prevPageId && prevPageId !== pageId) {
        const key = `flow-${flow.flow_id}-${prevPageId}->${pageId}`;
        if (!edgeSet.has(key)) {
          edgeSet.add(key);
          flowEdges.push({
            id: key,
            source: prevPageId,
            target: pageId,
            label: flow.name.slice(0, 20),
            style: { stroke: "#22c55e" },
          });
        }
      }
      prevPageId = pageId;
    }
  }
}

export function AppMapGraph({ appmap, moduleColorMode = "none" }: Props) {
  const modules = appmap?.modules ?? [];
  const hasModules = modules.length > 0;

  const { nodes, edges } = useMemo(() => {
    if (!appmap || appmap.pages.length === 0) {
      return { nodes: [] as Node[], edges: [] as Edge[] };
    }
    if (hasModules) {
      return buildModuleLayout(appmap, modules, moduleColorMode);
    }
    return buildFlatLayout(appmap);
  }, [appmap, hasModules, modules, moduleColorMode]);

  if (!appmap) {
    return <p className="text-sm text-[var(--muted)]">Loading AppMap…</p>;
  }

  if (appmap.pages.length === 0) {
    return (
      <p className="text-sm text-[var(--muted)]">
        No pages in AppMap yet. Run a crawl first.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {appmap.schema_version < 3 && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-2 text-sm text-amber-200">
          This AppMap is v{appmap.schema_version}. Re-run discovery to build the v3 module tree
          and module-grouped graph.
        </div>
      )}

      <div className="flex flex-wrap gap-4 text-xs text-[var(--muted)]">
        <span>{appmap.stats.page_count} pages</span>
        <span>{appmap.stats.flow_count} flows</span>
        {hasModules && <span>{modules.length} modules</span>}
        <span>{appmap.stats.state_count} states</span>
        <span>{appmap.stats.element_count} elements</span>
        {(appmap.navigation_graph?.length ?? 0) > 0 && (
          <span>{appmap.navigation_graph!.length} nav edges</span>
        )}
      </div>

      {hasModules && (
        <div className="flex flex-wrap gap-2">
          {modules.map((mod, i) => (
            <span
              key={mod.module_id}
              className="rounded px-2 py-0.5 text-xs"
              style={{
                background: `${moduleHeatColor(mod, moduleColorMode, i)}22`,
                border: `1px solid ${moduleHeatColor(mod, moduleColorMode, i)}`,
              }}
            >
              {mod.name}
              {moduleColorMode !== "none" &&
                (mod.risk_score != null || mod.testability_score != null) &&
                ` (${moduleColorMode === "risk" ? mod.risk_score : moduleColorMode === "testability" ? mod.testability_score : mod.automation_complexity_score})`}
            </span>
          ))}
        </div>
      )}

      <p className="text-xs text-[var(--muted)]">
        {hasModules
          ? "Pages are grouped by module. Orange edges = interaction navigation, blue = links, purple = CIC, green = flows."
          : "Flat page graph (re-crawl for module grouping)."}
      </p>

      {appmap.flows.length > 0 && <FlowConfidenceList flows={appmap.flows} />}

      <div className="h-[520px] rounded-lg border border-[var(--border)] bg-[var(--bg)]">
        <ReactFlow nodes={nodes} edges={edges} fitView proOptions={{ hideAttribution: true }}>
          <Background gap={16} color="#2d3a4f" />
          <Controls />
          <MiniMap nodeColor="#1a2332" maskColor="rgba(0,0,0,0.6)" />
        </ReactFlow>
      </div>
    </div>
  );
}

function confidenceLabel(score: number): { text: string; className: string } {
  if (score >= 0.85) return { text: "High", className: "bg-green-500/20 text-green-400" };
  if (score >= 0.6) return { text: "Medium", className: "bg-amber-500/20 text-amber-300" };
  return { text: "Low", className: "bg-red-500/20 text-red-300" };
}

function FlowConfidenceList({ flows }: { flows: AppMapFlow[] }) {
  const sorted = useMemo(
    () => [...flows].sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0)),
    [flows]
  );

  const hasConfidence = sorted.some((f) => f.confidence != null);
  if (!hasConfidence) return null;

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
      <p className="mb-2 text-xs font-medium text-[var(--muted)]">Flows by confidence</p>
      <ul className="max-h-40 space-y-1 overflow-y-auto text-sm">
        {sorted.map((flow) => {
          const score = flow.confidence ?? 0;
          const pill = confidenceLabel(score);
          const factors = flow.confidence_factors?.join(", ");
          return (
            <li
              key={flow.flow_id}
              className="flex flex-wrap items-center justify-between gap-2 rounded px-1 py-0.5 hover:bg-[var(--bg)]"
              title={factors || undefined}
            >
              <span className="truncate">{flow.name}</span>
              <span className={`shrink-0 rounded px-2 py-0.5 text-xs ${pill.className}`}>
                {pill.text} ({Math.round(score * 100)}%)
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
