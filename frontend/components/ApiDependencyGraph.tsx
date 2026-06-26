"use client";

import { useMemo, useState } from "react";
import { ApiFlowGraph } from "@/components/api-flow/ApiFlowGraph";
import { ApiFlowToolbar } from "@/components/api-flow/ApiFlowToolbar";
import {
  buildGuideTree,
  EDGE_META,
  type ApiFlowColorMode,
  type ApiFlowDepthFilter,
  type ApiFlowLayoutMode,
} from "@/lib/apiFlowUtils";
import type {
  ApiDependencyGraph,
  ApiEndpointCoverage,
  ApiFlowAnalysis,
  AppMapApiEndpoint,
  AuthIntelligence,
} from "@/lib/types";

type Props = {
  graph: ApiDependencyGraph | null | undefined;
  endpoints?: AppMapApiEndpoint[];
  authIntelligence?: AuthIntelligence | null;
  flowAnalysis?: ApiFlowAnalysis | null;
  apiCoverage?: ApiEndpointCoverage | null;
};

function GuideTree({ steps, depth = 0 }: { steps: ReturnType<typeof buildGuideTree>; depth?: number }) {
  if (steps.length === 0) return null;
  return (
    <ol className={depth > 0 ? "ml-4 mt-2 space-y-2 border-l border-[var(--border)] pl-3" : "space-y-3"}>
      {steps.map((step) => (
        <li key={`${depth}-${step.path}-${step.method}`} className="rounded-lg border border-[var(--border)] p-3">
          <div className="flex items-start gap-3">
            <span className="rounded-full bg-slate-700 px-2 py-0.5 text-[10px] font-semibold text-white">
              D{step.depth}
            </span>
            <div className="min-w-0">
              <div className="text-sm font-medium text-[var(--text)]">{step.title}</div>
              <div className="mt-0.5 font-mono text-[11px] text-[var(--muted)]">
                {step.method} {step.path}
              </div>
            </div>
          </div>
          {step.children && step.children.length > 0 && (
            <GuideTree steps={step.children} depth={depth + 1} />
          )}
        </li>
      ))}
    </ol>
  );
}

export function ApiDependencyGraphView({
  graph,
  endpoints = [],
  authIntelligence,
  flowAnalysis,
  apiCoverage,
}: Props) {
  const [view, setView] = useState<"guide" | "diagram">("guide");
  const [depthFilter, setDepthFilter] = useState<ApiFlowDepthFilter>("all");
  const [layoutMode, setLayoutMode] = useState<ApiFlowLayoutMode>("dag");
  const [colorMode, setColorMode] = useState<ApiFlowColorMode>("default");
  const [search, setSearch] = useState("");
  const [qaOverlay, setQaOverlay] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [centerToken, setCenterToken] = useState(0);

  const resolvedGraph = useMemo<ApiDependencyGraph | null>(() => {
    if (graph?.nodes?.length) return graph;
    if (endpoints.length === 0) return null;
    return {
      nodes: endpoints.slice(0, 48).map((endpoint) => ({
        endpoint_id: endpoint.endpoint_id,
        method: endpoint.method,
        path: endpoint.path,
        path_pattern: endpoint.path_pattern,
        depth: 0,
      })),
      edges: [],
    };
  }, [graph, endpoints]);

  const guideTree = useMemo(
    () => (resolvedGraph ? buildGuideTree(resolvedGraph, endpoints) : []),
    [resolvedGraph, endpoints]
  );

  const usedEdgeTypes = useMemo(
    () => [...new Set((resolvedGraph?.edges ?? []).map((edge) => edge.edge_type))],
    [resolvedGraph?.edges]
  );

  if (!resolvedGraph || resolvedGraph.nodes.length === 0) {
    return (
      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-6 text-sm text-[var(--muted)]">
        No API activity captured yet. Re-run discovery with network capture enabled to see how the app
        talks to its backend.
      </div>
    );
  }

  const visibleCount =
    depthFilter === "all"
      ? resolvedGraph.nodes.length
      : resolvedGraph.nodes.filter((node) => {
          const depth = node.depth ?? 0;
          if (depthFilter === "3+") return depth >= 3;
          return depth === Number(depthFilter);
        }).length;

  return (
    <div className="space-y-4">
      <ApiFlowToolbar
        view={view}
        onViewChange={setView}
        depthFilter={depthFilter}
        onDepthFilterChange={setDepthFilter}
        layoutMode={layoutMode}
        onLayoutModeChange={setLayoutMode}
        colorMode={colorMode}
        onColorModeChange={setColorMode}
        search={search}
        onSearchChange={setSearch}
        qaOverlay={qaOverlay}
        onQaOverlayChange={setQaOverlay}
        visibleCount={visibleCount}
        totalCount={resolvedGraph.nodes.length}
        selectedNodeId={selectedNodeId}
        onCenterSelected={() => setCenterToken((value) => value + 1)}
      />

      {qaOverlay && flowAnalysis && (
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-xs text-[var(--muted)]">
          {(flowAnalysis.entry_endpoint_ids?.length ?? 0)} entry ·{" "}
          {(flowAnalysis.leaf_endpoint_ids?.length ?? 0)} leaf ·{" "}
          {(apiCoverage?.untested_endpoint_ids?.length ?? 0)} untested ·{" "}
          {(flowAnalysis.critical_path_endpoint_ids?.length ?? 0)} on critical path
        </div>
      )}

      {view === "guide" ? (
        <div className="space-y-4">
          <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
            <h4 className="text-sm font-medium text-[var(--text)]">API flow hierarchy</h4>
            <p className="mb-3 text-xs text-[var(--muted)]">
              Entry APIs fan out into dependent calls discovered during crawl.
            </p>
            <GuideTree steps={guideTree} />
          </section>
          {(resolvedGraph.edges?.length ?? 0) === 0 && (
            <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 text-sm text-[var(--muted)]">
              APIs were observed but no strong dependency links yet.
            </section>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {usedEdgeTypes.length > 0 && (
            <div className="flex flex-wrap gap-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-xs">
              <span className="font-medium text-[var(--text)]">Legend:</span>
              {usedEdgeTypes.map((type) => {
                const meta = EDGE_META[type] || {
                  label: type,
                  color: "#6366f1",
                  dashed: false,
                  hint: "",
                };
                return (
                  <span key={type} className="flex items-center gap-2 text-[var(--muted)]">
                    <span
                      className="inline-block h-0.5 w-8"
                      style={{
                        backgroundColor: meta.dashed ? "transparent" : meta.color,
                        borderTop: meta.dashed ? `2px dashed ${meta.color}` : undefined,
                      }}
                    />
                    <span className="font-medium text-[var(--text)]">{meta.label}</span>
                  </span>
                );
              })}
            </div>
          )}

          <ApiFlowGraph
            graph={resolvedGraph}
            endpoints={endpoints}
            authIntelligence={authIntelligence}
            flowAnalysis={flowAnalysis}
            apiCoverage={apiCoverage}
            depthFilter={depthFilter}
            onDepthFilterChange={setDepthFilter}
            layoutMode={layoutMode}
            colorMode={colorMode}
            search={search}
            qaOverlay={qaOverlay}
            selectedNodeId={selectedNodeId}
            onSelectedNodeIdChange={setSelectedNodeId}
            centerToken={centerToken}
          />
        </div>
      )}
    </div>
  );
}
