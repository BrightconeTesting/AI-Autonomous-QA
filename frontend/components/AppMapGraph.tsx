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
import type { AppMapResponse } from "@/lib/types";

type Props = {
  appmap: AppMapResponse | null;
};

function pageLabel(url: string, title: string | null): string {
  if (title) return title;
  try {
    const path = new URL(url).pathname;
    return path.length > 1 ? path : url;
  } catch {
    return url;
  }
}

export function AppMapGraph({ appmap }: Props) {
  const { nodes, edges } = useMemo(() => {
    if (!appmap || appmap.pages.length === 0) {
      return { nodes: [] as Node[], edges: [] as Edge[] };
    }

    const statePage = new Map(appmap.states.map((s) => [s.state_id, s.page_id]));
    const cols = Math.ceil(Math.sqrt(appmap.pages.length));
    const pageNodes: Node[] = appmap.pages.map((page, i) => ({
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

    const edgeSet = new Set<string>();
    const flowEdges: Edge[] = [];

    for (const t of appmap.transitions) {
      const fromPage = statePage.get(t.from_state_id);
      const toPage = statePage.get(t.to_state_id);
      if (!fromPage || !toPage || fromPage === toPage) continue;
      const key = `${fromPage}->${toPage}`;
      if (edgeSet.has(key)) continue;
      edgeSet.add(key);
      flowEdges.push({
        id: key,
        source: fromPage,
        target: toPage,
        animated: true,
        style: { stroke: "#60a5fa" },
      });
    }

    if (flowEdges.length === 0) {
      for (const flow of appmap.flows) {
        let prevPageId: string | null = null;
        for (const step of flow.steps) {
          if (String(step.action) !== "navigate") continue;
          const target = String(step.target ?? "");
          const page = appmap.pages.find((p) => p.url === target || target.includes(p.url));
          if (!page) continue;
          if (prevPageId && prevPageId !== page.page_id) {
            const key = `${prevPageId}->${page.page_id}`;
            if (!edgeSet.has(key)) {
              edgeSet.add(key);
              flowEdges.push({
                id: `${flow.flow_id}-${key}`,
                source: prevPageId,
                target: page.page_id,
                label: flow.name.slice(0, 24),
                style: { stroke: "#22c55e" },
              });
            }
          }
          prevPageId = page.page_id;
        }
      }
    }

    return { nodes: pageNodes, edges: flowEdges };
  }, [appmap]);

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
      <div className="flex flex-wrap gap-4 text-xs text-[var(--muted)]">
        <span>{appmap.stats.page_count} pages</span>
        <span>{appmap.stats.flow_count} flows</span>
        <span>{appmap.stats.state_count} states</span>
        <span>{appmap.stats.element_count} elements</span>
      </div>
      <div className="h-[480px] rounded-lg border border-[var(--border)] bg-[var(--bg)]">
        <ReactFlow nodes={nodes} edges={edges} fitView proOptions={{ hideAttribution: true }}>
          <Background gap={16} color="#2d3a4f" />
          <Controls />
          <MiniMap nodeColor="#1a2332" maskColor="rgba(0,0,0,0.6)" />
        </ReactFlow>
      </div>
    </div>
  );
}
