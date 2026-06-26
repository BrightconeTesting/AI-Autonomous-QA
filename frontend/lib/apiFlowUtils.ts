import type {
  ApiDependencyGraph,
  ApiDependencyGraphEdge,
  ApiDependencyGraphNode,
  AppMapApiEndpoint,
} from "@/lib/types";

export type EdgeMeta = {
  label: string;
  hint: string;
  color: string;
  dashed: boolean;
  animated: boolean;
};

export const EDGE_META: Record<string, EdgeMeta> = {
  sequential: {
    label: "Then calls",
    hint: "The app called this API right after the previous one",
    color: "#3b82f6",
    dashed: false,
    animated: true,
  },
  auth_dependency: {
    label: "Needs login",
    hint: "This API only works after the user is signed in",
    color: "#f59e0b",
    dashed: true,
    animated: false,
  },
  ui_chain: {
    label: "UI action",
    hint: "A button or form on the page triggered this API",
    color: "#a855f7",
    dashed: false,
    animated: false,
  },
  schema_ref: {
    label: "Uses data",
    hint: "This API reuses data returned by the previous API",
    color: "#64748b",
    dashed: true,
    animated: false,
  },
};

export const METHOD_COLORS: Record<string, { bg: string; text: string }> = {
  GET: { bg: "#14532d", text: "#86efac" },
  POST: { bg: "#1e3a5f", text: "#93c5fd" },
  PUT: { bg: "#713f12", text: "#fcd34d" },
  PATCH: { bg: "#713f12", text: "#fcd34d" },
  DELETE: { bg: "#7f1d1d", text: "#fca5a5" },
};

export const RISK_TIER_COLORS: Record<string, string> = {
  low: "#22c55e",
  medium: "#eab308",
  high: "#f97316",
  critical: "#ef4444",
};

export const MODULE_PALETTE = [
  "#3b82f6",
  "#22c55e",
  "#a855f7",
  "#f59e0b",
  "#ec4899",
  "#14b8a6",
  "#f97316",
  "#6366f1",
];

export type ApiFlowColorMode = "default" | "risk" | "complexity";
export type ApiFlowLayoutMode = "dag" | "module";
export type ApiFlowDepthFilter = "all" | "0" | "1" | "2" | "3+";

export function friendlyApiTitle(path: string, method: string): string {
  const normalized = path
    .replace(/\{[^}]+\}/g, "")
    .replace(/\/+/g, "/")
    .replace(/^\/api\//, "")
    .replace(/^\//, "")
    .split("/")
    .filter(Boolean)
    .join(" ");

  if (!normalized) return method === "GET" ? "Load page data" : "Send data";

  const lower = normalized.toLowerCase();
  if (lower.includes("auth") && lower.includes("me")) return "Check who is logged in";
  if (lower.includes("login")) return "Sign in";
  if (lower.includes("logout")) return "Sign out";
  if (lower.includes("user")) return "Load users";
  if (lower.includes("setting")) return "Load settings";

  return normalized
    .split(/[-_]/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function endpointPath(
  endpoint: AppMapApiEndpoint | undefined,
  fallbackPath: string
): string {
  return endpoint?.path_pattern || endpoint?.path || fallbackPath || "";
}

export function edgeLabel(edge: ApiDependencyGraphEdge): string {
  const keys = edge.dependency_keys?.filter(Boolean) ?? [];
  if (keys.length > 0) {
    const shown = keys.slice(0, 3).join(", ");
    return keys.length > 3 ? `${shown} +${keys.length - 3}` : shown;
  }
  if (edge.parallel_group_id) return "Parallel";
  return EDGE_META[edge.edge_type]?.label ?? edge.edge_type;
}

export function mergeNodeData(
  node: ApiDependencyGraphNode,
  endpoint?: AppMapApiEndpoint
): ApiDependencyGraphNode & AppMapApiEndpoint {
  return { ...endpoint, ...node };
}

export function buildChildrenMap(edges: ApiDependencyGraphEdge[]): Map<string, string[]> {
  const map = new Map<string, string[]>();
  for (const edge of edges) {
    if (edge.is_primary === false) continue;
    const list = map.get(edge.from_endpoint_id) ?? [];
    list.push(edge.to_endpoint_id);
    map.set(edge.from_endpoint_id, list);
  }
  return map;
}

export function collectDescendants(rootId: string, childrenMap: Map<string, string[]>): Set<string> {
  const seen = new Set<string>();
  const stack = [...(childrenMap.get(rootId) ?? [])];
  while (stack.length > 0) {
    const current = stack.pop()!;
    if (seen.has(current)) continue;
    seen.add(current);
    stack.push(...(childrenMap.get(current) ?? []));
  }
  return seen;
}

export function moduleColor(moduleId: string | null | undefined, index: number): string {
  if (!moduleId) return "#64748b";
  let hash = 0;
  for (let i = 0; i < moduleId.length; i++) {
    hash = (hash + moduleId.charCodeAt(i) * 17) % MODULE_PALETTE.length;
  }
  return MODULE_PALETTE[(hash + index) % MODULE_PALETTE.length];
}

export function matchesSearch(
  node: ApiDependencyGraphNode,
  endpoint: AppMapApiEndpoint | undefined,
  query: string
): boolean {
  if (!query.trim()) return true;
  const q = query.trim().toLowerCase();
  const path = endpointPath(endpoint, node.path_pattern || node.path);
  const title = friendlyApiTitle(path, node.method);
  return (
    path.toLowerCase().includes(q) ||
    node.method.toLowerCase().includes(q) ||
    title.toLowerCase().includes(q) ||
    (node.module_name?.toLowerCase().includes(q) ?? false)
  );
}

export function depthMatchesFilter(depth: number | undefined, filter: ApiFlowDepthFilter): boolean {
  const value = depth ?? 0;
  if (filter === "all") return true;
  if (filter === "3+") return value >= 3;
  return value === Number(filter);
}

export type GuideStep = {
  depth: number;
  title: string;
  path: string;
  method: string;
  children?: GuideStep[];
};

export function buildGuideTree(
  graph: ApiDependencyGraph | null | undefined,
  endpoints: AppMapApiEndpoint[]
): GuideStep[] {
  if (!graph?.nodes?.length) return [];
  const endpointById = new Map(endpoints.map((item) => [item.endpoint_id, item]));
  const childrenMap = buildChildrenMap(graph.edges ?? []);
  const entries = graph.nodes.filter((node) => node.is_entry);
  const roots = entries.length > 0 ? entries : graph.nodes.filter((node) => (node.depth ?? 0) === 0);

  const buildStep = (node: ApiDependencyGraphNode): GuideStep => {
    const endpoint = endpointById.get(node.endpoint_id);
    const path = endpointPath(endpoint, node.path_pattern || node.path);
    const method = (endpoint?.method || node.method || "GET").toUpperCase();
    const childIds = childrenMap.get(node.endpoint_id) ?? [];
    const childNodes = childIds
      .map((id) => graph.nodes.find((item) => item.endpoint_id === id))
      .filter((item): item is ApiDependencyGraphNode => Boolean(item));
    return {
      depth: node.depth ?? 0,
      title: friendlyApiTitle(path, method),
      path,
      method,
      children: childNodes.length > 0 ? childNodes.map(buildStep) : undefined,
    };
  };

  return roots.map(buildStep);
}
