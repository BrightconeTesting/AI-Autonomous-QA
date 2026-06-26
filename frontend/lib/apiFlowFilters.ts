import type { ApiDependencyGraph } from "@/lib/types";
import { buildChildrenMap, collectDescendants, type ApiFlowDepthFilter } from "@/lib/apiFlowUtils";

function matchesDepth(depth: number, filter: ApiFlowDepthFilter): boolean {
  if (filter === "all") return true;
  if (filter === "3+") return depth >= 3;
  return depth === Number(filter);
}

export function computeVisibleNodeIds(input: {
  graph: ApiDependencyGraph;
  depthFilter: ApiFlowDepthFilter;
  collapsedRoots: Set<string>;
}): { visible: Set<string>; collapsedCounts: Map<string, number> } {
  const { graph, depthFilter, collapsedRoots } = input;
  const childrenMap = buildChildrenMap(graph.edges ?? []);
  const hidden = new Set<string>();
  const collapsedCounts = new Map<string, number>();

  for (const rootId of collapsedRoots) {
    const descendants = collectDescendants(rootId, childrenMap);
    if (descendants.size > 0) {
      collapsedCounts.set(rootId, descendants.size);
      for (const id of descendants) hidden.add(id);
    }
  }

  const visible = new Set<string>();
  for (const node of graph.nodes) {
    if (hidden.has(node.endpoint_id)) continue;
    const depth = node.depth ?? 0;

    if (depthFilter === "all") {
      visible.add(node.endpoint_id);
      continue;
    }

    if (matchesDepth(depth, depthFilter)) {
      visible.add(node.endpoint_id);
      continue;
    }

    // Keep entry nodes visible when filtering deeper layers for navigation context.
    if (depth === 0 && depthFilter !== "0") {
      visible.add(node.endpoint_id);
    }
  }

  return { visible, collapsedCounts };
}

export function allDepthLanesFromGraph(graph: ApiDependencyGraph): number[] {
  return [
    ...new Set(graph.nodes.map((node) => node.depth ?? 0)),
  ].sort((a, b) => a - b);
}

export function depthFilterForLane(depth: number): ApiFlowDepthFilter {
  if (depth >= 3) return "3+";
  return String(depth) as ApiFlowDepthFilter;
}
