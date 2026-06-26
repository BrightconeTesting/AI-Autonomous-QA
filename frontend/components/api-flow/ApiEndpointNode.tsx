"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { ApiFlowNodeData } from "@/lib/apiFlowLayout";
import { METHOD_COLORS, RISK_TIER_COLORS } from "@/lib/apiFlowUtils";

function borderColor(data: ApiFlowNodeData): string {
  if (data.qaUntested) return "#94a3b8";
  if (data.qaCritical) return "#ef4444";
  if (data.qaEntry) return "#22c55e";
  if (data.qaLeaf) return "#3b82f6";
  if (data.requiresAuth || data.isLoginEndpoint) return "#f59e0b";
  if (data.colorMode === "risk" && data.riskTier) {
    return RISK_TIER_COLORS[data.riskTier] ?? "var(--border)";
  }
  if (data.colorMode === "complexity" && data.complexityScore != null) {
    const hue = Math.max(0, 120 - data.complexityScore);
    return `hsl(${hue}, 70%, 45%)`;
  }
  return "var(--border)";
}

export function ApiEndpointNode({ data }: NodeProps) {
  const nodeData = data as ApiFlowNodeData;
  if (nodeData.isCollapsedSummary) {
    return (
      <div className="rounded-full border border-dashed border-[var(--border)] bg-[var(--surface)] px-4 py-2 text-xs font-semibold text-[var(--muted)]">
        {nodeData.title}
      </div>
    );
  }

  const method = (nodeData.method || "GET").toUpperCase();
  const colors = METHOD_COLORS[method] || { bg: "#334155", text: "#e2e8f0" };

  return (
    <div
      className={`rounded-xl border-2 bg-[var(--surface)] shadow-md transition-opacity ${
        nodeData.isDimmed ? "opacity-20" : ""
      } ${nodeData.isHighlighted ? "ring-2 ring-blue-400 ring-offset-2 ring-offset-[var(--bg)]" : ""}`}
      style={{
        borderColor: borderColor(nodeData),
        minWidth: 220,
        maxWidth: 260,
        padding: "10px 12px",
      }}
    >
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !bg-blue-400" />
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !bg-blue-400" />
      <Handle type="target" position={Position.Top} id="top" className="!h-2 !w-2 !bg-amber-400" />
      <Handle type="source" position={Position.Bottom} id="bottom" className="!h-2 !w-2 !bg-amber-400" />

      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <span className="rounded-full bg-slate-700 px-2 py-0.5 text-[10px] font-semibold text-slate-100">
          D{nodeData.depth}
        </span>
        {nodeData.isLoginEndpoint && (
          <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-medium text-amber-300">
            Login
          </span>
        )}
        {nodeData.isSessionCheck && (
          <span className="rounded-full bg-sky-500/20 px-2 py-0.5 text-[10px] font-medium text-sky-300">
            Session
          </span>
        )}
        {nodeData.requiresAuth && !nodeData.isLoginEndpoint && (
          <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-300">
            Secured
          </span>
        )}
        {nodeData.qaUntested && (
          <span className="rounded-full bg-slate-500/20 px-2 py-0.5 text-[10px] text-slate-300">
            Untested
          </span>
        )}
        {nodeData.qaCovered && (
          <span className="rounded-full bg-green-500/20 px-2 py-0.5 text-[10px] text-green-300">
            Covered
          </span>
        )}
        <span
          className="rounded px-1.5 py-0.5 text-[10px] font-bold"
          style={{ backgroundColor: colors.bg, color: colors.text }}
        >
          {method}
        </span>
      </div>
      <div className="text-sm font-semibold leading-snug text-[var(--text)]">{nodeData.title}</div>
      <div className="mt-1 truncate font-mono text-[10px] text-[var(--muted)]" title={nodeData.path}>
        {nodeData.path}
      </div>
      {nodeData.moduleName && (
        <div className="mt-1 text-[10px] text-[var(--muted)]">{nodeData.moduleName}</div>
      )}
    </div>
  );
}

export function ModuleGroupNode({ data }: NodeProps) {
  const nodeData = data as ApiFlowNodeData;
  return (
    <div className="pointer-events-none absolute left-3 top-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
      {nodeData.moduleName || nodeData.title}
    </div>
  );
}
