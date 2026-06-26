"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ApiEndpointNode, ModuleGroupNode } from "@/components/api-flow/ApiEndpointNode";
import { ApiFlowTooltip } from "@/components/api-flow/ApiFlowTooltip";
import { buildApiFlowGraphModel, type ApiFlowNodeData } from "@/lib/apiFlowLayout";
import { computeVisibleNodeIds, allDepthLanesFromGraph, depthFilterForLane } from "@/lib/apiFlowFilters";
import {
  EDGE_META,
  type ApiFlowColorMode,
  type ApiFlowDepthFilter,
  type ApiFlowLayoutMode,
  matchesSearch,
  RISK_TIER_COLORS,
} from "@/lib/apiFlowUtils";
import type {
  ApiDependencyGraph,
  ApiDependencyGraphEdge,
  ApiEndpointCoverage,
  ApiFlowAnalysis,
  AppMapApiEndpoint,
  AuthIntelligence,
} from "@/lib/types";

const nodeTypes = {
  apiEndpoint: ApiEndpointNode,
  collapsedSummary: ApiEndpointNode,
  moduleGroup: ModuleGroupNode,
};

function styledEdges(edges: Edge[], graphEdges: ApiDependencyGraphEdge[]): Edge[] {
  return edges.map((edge, index) => {
    const graphEdge = graphEdges.find(
      (item) =>
        item.from_endpoint_id === edge.source &&
        (item.to_endpoint_id === edge.target || edge.target.startsWith("collapsed-"))
    );
    const edgeType = graphEdge?.edge_type ?? "sequential";
    const meta = EDGE_META[edgeType] ?? {
      label: edgeType,
      color: "#6366f1",
      dashed: false,
      animated: false,
      hint: "",
    };
    const isAuth = edgeType === "auth_dependency";
    const label =
      edge.label ||
      (graphEdge?.dependency_keys?.length
        ? graphEdge.dependency_keys.slice(0, 3).join(", ")
        : graphEdge?.parallel_group_id
          ? "Parallel"
          : meta.label);

    return {
      ...edge,
      id: edge.id || `edge-${index}`,
      sourceHandle: isAuth ? "bottom" : edge.sourceHandle,
      targetHandle: isAuth ? "top" : edge.targetHandle,
      animated: meta.animated && graphEdge?.is_primary !== false,
      label,
      title: meta.hint,
      markerEnd: { type: MarkerType.ArrowClosed, color: meta.color },
      style: {
        ...edge.style,
        stroke: meta.color,
        strokeDasharray: meta.dashed ? "6 4" : undefined,
      },
      labelStyle: { fill: "var(--text)", fontSize: 10, fontWeight: 600 },
      labelBgStyle: {
        fill: "var(--surface)",
        fillOpacity: 0.95,
        stroke: meta.color,
        strokeWidth: 1,
      },
    };
  });
}

export type ApiFlowGraphProps = {
  graph: ApiDependencyGraph;
  endpoints: AppMapApiEndpoint[];
  authIntelligence?: AuthIntelligence | null;
  flowAnalysis?: ApiFlowAnalysis | null;
  apiCoverage?: ApiEndpointCoverage | null;
  depthFilter: ApiFlowDepthFilter;
  onDepthFilterChange: (value: ApiFlowDepthFilter) => void;
  layoutMode: ApiFlowLayoutMode;
  colorMode: ApiFlowColorMode;
  search: string;
  qaOverlay: boolean;
  selectedNodeId: string | null;
  onSelectedNodeIdChange: (id: string | null) => void;
  centerToken: number;
};

export function ApiFlowGraph({
  graph,
  endpoints,
  authIntelligence,
  flowAnalysis,
  apiCoverage,
  depthFilter,
  onDepthFilterChange,
  layoutMode,
  colorMode,
  search,
  qaOverlay,
  selectedNodeId,
  onSelectedNodeIdChange,
  centerToken,
}: ApiFlowGraphProps) {
  const [collapsedRoots, setCollapsedRoots] = useState<Set<string>>(new Set());
  const [hovered, setHovered] = useState<{ id: string; position: { x: number; y: number } } | null>(
    null
  );
  const containerRef = useRef<HTMLDivElement>(null);
  const flowRef = useRef<ReactFlowInstance | null>(null);

  const loginEndpointId = authIntelligence?.login_api_endpoint_id ?? null;

  const authSourceIds = useMemo(() => {
    if (loginEndpointId) return new Set([loginEndpointId]);
    const authEdges = (graph.edges ?? []).filter((edge) => edge.edge_type === "auth_dependency");
    return new Set(authEdges.map((edge) => edge.from_endpoint_id));
  }, [graph.edges, loginEndpointId]);

  const endpointById = useMemo(
    () => new Map(endpoints.map((item) => [item.endpoint_id, item])),
    [endpoints]
  );

  const { visible, collapsedCounts } = useMemo(
    () => computeVisibleNodeIds({ graph, depthFilter, collapsedRoots }),
    [graph, depthFilter, collapsedRoots]
  );

  const searchActive = search.trim().length > 0;
  const highlightedIds = useMemo(() => {
    if (!searchActive) return new Set<string>();
    return new Set(
      graph.nodes
        .filter((node) => matchesSearch(node, endpointById.get(node.endpoint_id), search))
        .map((node) => node.endpoint_id)
    );
  }, [graph.nodes, endpointById, search, searchActive]);

  const dimmedIds = useMemo(() => {
    if (!searchActive) return new Set<string>();
    return new Set(
      [...visible].filter((id) => !highlightedIds.has(id))
    );
  }, [visible, highlightedIds, searchActive]);

  const qaOverlays = useMemo(() => {
    if (!qaOverlay) return undefined;
    return {
      entryIds: new Set(flowAnalysis?.entry_endpoint_ids ?? []),
      leafIds: new Set(flowAnalysis?.leaf_endpoint_ids ?? []),
      criticalIds: new Set(flowAnalysis?.critical_path_endpoint_ids ?? []),
      untestedIds: new Set(apiCoverage?.untested_endpoint_ids ?? []),
      coveredIds: new Set(apiCoverage?.covered_endpoint_ids ?? []),
    };
  }, [qaOverlay, flowAnalysis, apiCoverage]);

  const model = useMemo(() => {
    const built = buildApiFlowGraphModel({
      graph,
      endpoints,
      visibleNodeIds: visible,
      collapsedRoots,
      collapsedCounts,
      colorMode,
      layoutMode,
      highlightedIds,
      dimmedIds,
      authSourceIds,
      loginEndpointId,
      qaOverlays,
    });
    return { ...built, edges: styledEdges(built.edges, graph.edges ?? []) };
  }, [
    graph,
    endpoints,
    visible,
    collapsedRoots,
    collapsedCounts,
    colorMode,
    layoutMode,
    highlightedIds,
    dimmedIds,
    authSourceIds,
    loginEndpointId,
    qaOverlays,
  ]);

  const allDepthLanes = useMemo(() => allDepthLanesFromGraph(graph), [graph]);

  useEffect(() => {
    if (!flowRef.current) return;
    const timer = window.setTimeout(() => {
      flowRef.current?.fitView({ padding: 0.2, duration: 200 });
    }, 60);
    return () => window.clearTimeout(timer);
  }, [model.nodes, model.edges, depthFilter, layoutMode]);

  useEffect(() => {
    if (!selectedNodeId || !flowRef.current) return;
    const node = model.nodes.find((item) => item.id === selectedNodeId);
    if (!node) return;
    flowRef.current.setCenter(node.position.x + 120, node.position.y + 48, {
      zoom: 1.15,
      duration: 300,
    });
  }, [centerToken, selectedNodeId, model.nodes]);

  const onNodeClick: NodeMouseHandler = useCallback(
    (event, node) => {
      const data = node.data as ApiFlowNodeData;
      if (data.isCollapsedSummary && data.endpointId) {
        setCollapsedRoots((prev) => {
          const next = new Set(prev);
          next.delete(data.endpointId);
          return next;
        });
        return;
      }
      if (event.detail === 2 && data.canCollapse && data.endpointId) {
        setCollapsedRoots((prev) => {
          const next = new Set(prev);
          if (next.has(data.endpointId)) next.delete(data.endpointId);
          else next.add(data.endpointId);
          return next;
        });
        return;
      }
      onSelectedNodeIdChange(node.id);
    },
    [onSelectedNodeIdChange]
  );

  const hoveredData = useMemo(
    () => model.nodes.find((node) => node.id === hovered?.id)?.data ?? null,
    [hovered, model.nodes]
  );

  const flowNodes: Node[] = model.nodes.map((node) => ({
    ...node,
    selected: node.id === selectedNodeId,
  }));

  return (
    <div className="space-y-3">
      <div
        ref={containerRef}
        className="relative rounded-lg border border-[var(--border)] bg-[var(--bg)]"
        style={{ height: Math.max(480, 120 + model.nodes.length * 12) }}
      >
        <ReactFlow
          nodes={flowNodes}
          edges={model.edges}
          nodeTypes={nodeTypes}
          onInit={(instance) => {
            flowRef.current = instance;
          }}
          onNodeClick={onNodeClick}
          onNodeMouseEnter={(event, node) => {
            const bounds = containerRef.current?.getBoundingClientRect();
            if (!bounds) return;
            setHovered({
              id: node.id,
              position: {
                x: event.clientX - bounds.left,
                y: event.clientY - bounds.top,
              },
            });
          }}
          onNodeMouseLeave={() => setHovered(null)}
          onPaneClick={() => onSelectedNodeIdChange(null)}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={20} color="var(--border)" />
          <Controls showInteractive />
          <MiniMap
            nodeColor={(node) => {
              const data = node.data as ApiFlowNodeData;
              if (data.riskTier) return RISK_TIER_COLORS[data.riskTier] ?? "#1a2332";
              return "#1a2332";
            }}
            maskColor="rgba(0,0,0,0.6)"
          />
        </ReactFlow>
        <ApiFlowTooltip data={hoveredData} position={hovered?.position ?? null} />
      </div>

      {allDepthLanes.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => onDepthFilterChange("all")}
            className={`rounded border px-2 py-1 text-[10px] ${
              depthFilter === "all"
                ? "border-blue-500 bg-blue-600/20 text-blue-200"
                : "border-[var(--border)] text-[var(--muted)] hover:border-blue-400"
            }`}
          >
            All depths
          </button>
          {allDepthLanes.map((depth) => {
            const laneFilter = depthFilterForLane(depth);
            const active = depthFilter === laneFilter;
            return (
              <button
                key={depth}
                type="button"
                onClick={() => onDepthFilterChange(active ? "all" : laneFilter)}
                className={`rounded border px-2 py-1 text-[10px] ${
                  active
                    ? "border-blue-500 bg-blue-600/20 text-blue-200"
                    : "border-[var(--border)] text-[var(--muted)] hover:border-blue-400"
                }`}
              >
                {depth === 0 ? "Depth 0 — Entry" : `Depth ${depth}`}
              </button>
            );
          })}
        </div>
      )}

      <p className="text-xs text-[var(--muted)]">
        Double-click a node to collapse or expand its branch. Click a collapsed summary to expand.
      </p>
    </div>
  );
}
