import dagre from "@dagrejs/dagre";
import type { Edge, Node } from "@xyflow/react";
import type { ApiDependencyGraph, ApiDependencyGraphEdge, AppMapApiEndpoint } from "@/lib/types";
import {
  type ApiFlowLayoutMode,
  buildChildrenMap,
  endpointPath,
  friendlyApiTitle,
  moduleColor,
} from "@/lib/apiFlowUtils";

const NODE_WIDTH = 240;
const NODE_HEIGHT = 96;
const GROUP_PADDING = 40;

export type ApiFlowNodeData = {
  endpointId: string;
  method: string;
  title: string;
  path: string;
  depth: number;
  moduleId?: string | null;
  moduleName?: string | null;
  requiresAuth: boolean;
  isAuthSource: boolean;
  riskScore?: number | null;
  riskTier?: string | null;
  complexityScore?: number | null;
  isEntry?: boolean;
  isLeaf?: boolean;
  seenCount?: number;
  riskFactors?: string[];
  authInheritedFrom?: string | null;
  isLoginEndpoint?: boolean;
  isSessionCheck?: boolean;
  collapsedCount?: number;
  isCollapsedSummary?: boolean;
  isHighlighted?: boolean;
  isDimmed?: boolean;
  qaEntry?: boolean;
  qaLeaf?: boolean;
  qaCritical?: boolean;
  qaUntested?: boolean;
  qaCovered?: boolean;
  colorMode: "default" | "risk" | "complexity";
  canCollapse?: boolean;
  collapsed?: boolean;
};

function layoutWithDagre(
  nodes: Node<ApiFlowNodeData>[],
  edges: Edge[],
  rankdir: "LR" | "TB" = "LR"
): Node<ApiFlowNodeData>[] {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir,
    ranksep: Math.max(120, 80 + nodes.length * 2),
    nodesep: Math.max(60, 40 + nodes.length),
    marginx: 40,
    marginy: 40,
  });

  for (const node of nodes) {
    graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const edge of edges) {
    graph.setEdge(edge.source, edge.target);
  }

  dagre.layout(graph);

  return nodes.map((node) => {
    const position = graph.node(node.id);
    return {
      ...node,
      position: {
        x: position.x - NODE_WIDTH / 2,
        y: position.y - NODE_HEIGHT / 2,
      },
    };
  });
}

function groupByModule(
  nodes: Node<ApiFlowNodeData>[]
): Map<string, { name: string; nodes: Node<ApiFlowNodeData>[] }> {
  const groups = new Map<string, { name: string; nodes: Node<ApiFlowNodeData>[] }>();
  for (const node of nodes) {
    const key = node.data.moduleId || node.data.moduleName || "uncategorized";
    const name = node.data.moduleName || "Uncategorized";
    const group = groups.get(key) ?? { name, nodes: [] };
    group.nodes.push(node);
    groups.set(key, group);
  }
  return groups;
}

export function buildApiFlowGraphModel(input: {
  graph: ApiDependencyGraph;
  endpoints: AppMapApiEndpoint[];
  visibleNodeIds: Set<string>;
  collapsedRoots: Set<string>;
  collapsedCounts: Map<string, number>;
  colorMode: "default" | "risk" | "complexity";
  layoutMode: ApiFlowLayoutMode;
  highlightedIds: Set<string>;
  dimmedIds: Set<string>;
  authSourceIds: Set<string>;
  loginEndpointId?: string | null;
  qaOverlays?: {
    entryIds: Set<string>;
    leafIds: Set<string>;
    criticalIds: Set<string>;
    untestedIds: Set<string>;
    coveredIds: Set<string>;
  };
}): { nodes: Node<ApiFlowNodeData>[]; edges: Edge[]; depthLanes: number[] } {
  const {
    graph,
    endpoints,
    visibleNodeIds,
    collapsedRoots,
    collapsedCounts,
    colorMode,
    layoutMode,
    highlightedIds,
    dimmedIds,
    authSourceIds,
    loginEndpointId,
    qaOverlays,
  } = input;

  const endpointById = new Map(endpoints.map((item) => [item.endpoint_id, item]));
  const childrenMap = buildChildrenMap(graph.edges);

  const baseNodes: Node<ApiFlowNodeData>[] = [];
  for (const node of graph.nodes) {
    if (!visibleNodeIds.has(node.endpoint_id)) continue;
    if (collapsedCounts.has(node.endpoint_id)) continue;

    const endpoint = endpointById.get(node.endpoint_id);
    const path = endpointPath(endpoint, node.path_pattern || node.path);
    const method = (endpoint?.method || node.method || "GET").toUpperCase();
    const childCount = childrenMap.get(node.endpoint_id)?.length ?? 0;

    baseNodes.push({
      id: node.endpoint_id,
      type: "apiEndpoint",
      position: { x: 0, y: 0 },
      data: {
        endpointId: node.endpoint_id,
        method,
        title: friendlyApiTitle(path, method),
        path,
        depth: node.depth ?? 0,
        moduleId: node.module_id,
        moduleName: node.module_name,
        requiresAuth: Boolean(node.requires_auth),
        isAuthSource: Boolean(
          loginEndpointId
            ? node.endpoint_id === loginEndpointId
            : node.is_login_endpoint || authSourceIds.has(node.endpoint_id)
        ),
        isLoginEndpoint: Boolean(node.is_login_endpoint ?? (loginEndpointId === node.endpoint_id)),
        isSessionCheck: Boolean(node.is_session_check),
        riskScore: node.risk_score ?? endpoint?.risk_score,
        riskTier: node.risk_tier ?? null,
        complexityScore: endpoint?.automation_complexity_score,
        isEntry: node.is_entry,
        isLeaf: node.is_leaf,
        seenCount: node.seen_count ?? endpoint?.seen_count,
        riskFactors: endpoint?.risk_factors,
        authInheritedFrom: node.auth_inherited_from,
        isHighlighted: highlightedIds.has(node.endpoint_id),
        isDimmed: dimmedIds.has(node.endpoint_id),
        qaEntry: qaOverlays?.entryIds.has(node.endpoint_id),
        qaLeaf: qaOverlays?.leafIds.has(node.endpoint_id),
        qaCritical: qaOverlays?.criticalIds.has(node.endpoint_id),
        qaUntested: qaOverlays?.untestedIds.has(node.endpoint_id),
        qaCovered: qaOverlays?.coveredIds.has(node.endpoint_id),
        colorMode,
        canCollapse: childCount > 0,
        collapsed: collapsedRoots.has(node.endpoint_id),
      },
    });
  }

  for (const [parentId, count] of collapsedCounts) {
    if (!visibleNodeIds.has(parentId)) continue;
    const parent = graph.nodes.find((node) => node.endpoint_id === parentId);
    if (!parent) continue;
    baseNodes.push({
      id: `collapsed-${parentId}`,
      type: "collapsedSummary",
      position: { x: 0, y: 0 },
      data: {
        endpointId: parentId,
        method: "",
        title: `+${count} APIs`,
        path: "",
        depth: (parent.depth ?? 0) + 1,
        requiresAuth: false,
        isAuthSource: false,
        collapsedCount: count,
        isCollapsedSummary: true,
        colorMode,
      },
    });
  }

  const visibleEdges = (graph.edges ?? []).filter((edge: ApiDependencyGraphEdge) => {
    if (edge.edge_type === "auth_dependency") {
      if (!loginEndpointId) return false;
      if (edge.from_endpoint_id !== loginEndpointId) return false;
    }
    return (
      visibleNodeIds.has(edge.from_endpoint_id) &&
      (visibleNodeIds.has(edge.to_endpoint_id) || collapsedCounts.has(edge.from_endpoint_id))
    );
  });

  const flowEdges: Edge[] = visibleEdges.flatMap((edge, index) => {
    const fromVisible =
      visibleNodeIds.has(edge.from_endpoint_id) || collapsedCounts.has(edge.from_endpoint_id);
    const target = collapsedCounts.has(edge.from_endpoint_id)
      ? `collapsed-${edge.from_endpoint_id}`
      : edge.to_endpoint_id;
    const toVisible = visibleNodeIds.has(edge.to_endpoint_id) || target.startsWith("collapsed-");
    if (!fromVisible || !toVisible) return [];
    const isAuth = edge.edge_type === "auth_dependency";
    return [
      {
        id: `${edge.from_endpoint_id}-${edge.to_endpoint_id}-${index}`,
        source: edge.from_endpoint_id,
        target,
        sourceHandle: isAuth ? "bottom" : undefined,
        targetHandle: isAuth ? "top" : undefined,
        type: "smoothstep",
        animated: edge.edge_type === "sequential" && edge.is_primary !== false,
        label: edge.dependency_keys?.length
          ? edge.dependency_keys.slice(0, 3).join(", ")
          : edge.parallel_group_id
            ? "Parallel"
            : undefined,
        style: {
          strokeWidth: qaOverlays?.criticalIds.has(edge.to_endpoint_id) ? 3 : 2,
        },
      },
    ];
  });

  let positioned: Node<ApiFlowNodeData>[] = baseNodes;
  const layoutEdges = flowEdges.filter((edge) => {
    const graphEdge = (graph.edges ?? []).find(
      (item) =>
        item.from_endpoint_id === edge.source &&
        (item.to_endpoint_id === edge.target || edge.target.startsWith("collapsed-"))
    );
    return graphEdge?.edge_type !== "auth_dependency";
  });

  if (layoutMode === "module") {
    const groups = groupByModule(baseNodes.filter((node) => !node.data.isCollapsedSummary));
    const groupNodes: Node<ApiFlowNodeData>[] = [];
    let offsetX = 0;
    let groupIndex = 0;
    for (const [groupId, group] of groups) {
      const laidOut = layoutWithDagre(
        group.nodes,
        layoutEdges.filter((edge) =>
          group.nodes.some((node) => node.id === edge.source || node.id === edge.target)
        )
      );
      const minX = Math.min(...laidOut.map((node) => node.position.x));
      const maxX = Math.max(...laidOut.map((node) => node.position.x));
      const shifted = laidOut.map((node) => ({
        ...node,
        position: {
          x: node.position.x - minX + offsetX,
          y: node.position.y + GROUP_PADDING,
        },
        parentId: `module-${groupId}`,
        extent: "parent" as const,
      }));
      const width = maxX - minX + NODE_WIDTH + GROUP_PADDING;
      groupNodes.push({
        id: `module-${groupId}`,
        type: "moduleGroup",
        position: { x: offsetX - 20, y: 0 },
        data: {
          endpointId: groupId,
          method: "",
          title: group.name,
          path: "",
          depth: 0,
          requiresAuth: false,
          isAuthSource: false,
          colorMode,
          moduleName: group.name,
        },
        style: {
          width,
          height: Math.max(200, ...shifted.map((node) => node.position.y + NODE_HEIGHT)) + GROUP_PADDING,
          backgroundColor: `${moduleColor(groupId, groupIndex)}15`,
          border: `1px solid ${moduleColor(groupId, groupIndex)}55`,
          borderRadius: 12,
          padding: 12,
        },
      });
      groupNodes.push(...shifted);
      offsetX += width + 80;
      groupIndex += 1;
    }
    const summaries = baseNodes.filter((node) => node.data.isCollapsedSummary);
    positioned = layoutWithDagre([...groupNodes, ...summaries], layoutEdges);
  } else {
    positioned = layoutWithDagre(baseNodes, layoutEdges);
  }

  const depthLanes = [
    ...new Set(
      graph.nodes
        .filter((node) => visibleNodeIds.has(node.endpoint_id))
        .map((node) => node.depth ?? 0)
    ),
  ].sort((a, b) => a - b);

  return { nodes: positioned, edges: flowEdges, depthLanes };
}
