"use client";

import { useState } from "react";
import type { AppMapApprovalResponse } from "@/lib/types";

type Props = {
  approval: AppMapApprovalResponse | null;
  busy?: boolean;
  onApprove: () => Promise<void>;
  onReject: (reason: string) => Promise<void>;
};

const STATUS_STYLES: Record<string, string> = {
  pending: "border-amber-500/50 bg-amber-500/10 text-amber-300",
  approved: "border-green-600/50 bg-green-500/10 text-green-400",
  rejected: "border-red-600/50 bg-red-500/10 text-red-300",
  none: "border-[var(--border)] bg-[var(--surface)] text-[var(--muted)]",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "Pending review",
  approved: "Approved",
  rejected: "Rejected",
  none: "No crawl yet",
};

export function AppMapApprovalPanel({ approval, busy = false, onApprove, onReject }: Props) {
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  if (!approval || approval.status === "none") {
    return null;
  }

  const status = approval.status;

  async function handleReject() {
    await onReject(rejectReason);
    setRejectOpen(false);
    setRejectReason("");
  }

  return (
    <div
      className={`rounded-lg border px-4 py-3 ${STATUS_STYLES[status] ?? STATUS_STYLES.none}`}
      role="region"
      aria-label="AppMap approval"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium">AppMap review — {STATUS_LABELS[status]}</p>
          {status === "pending" && (
            <p className="mt-1 text-xs opacity-90">
              Discovery finished. Review the AppMap, then approve to generate tests.
            </p>
          )}
          {status === "rejected" && approval.rejection_reason && (
            <p className="mt-1 text-xs opacity-90">Reason: {approval.rejection_reason}</p>
          )}
          {status === "approved" && approval.approved_at && (
            <p className="mt-1 text-xs opacity-90">
              Approved {new Date(approval.approved_at).toLocaleString()}
            </p>
          )}
        </div>
        {(status === "pending" || status === "rejected") && (
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => onApprove()}
              className="rounded bg-green-600 px-3 py-1.5 text-sm text-white disabled:opacity-50"
            >
              Approve AppMap
            </button>
            {!rejectOpen ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => setRejectOpen(true)}
                className="rounded border border-red-500/50 px-3 py-1.5 text-sm text-red-300 disabled:opacity-50"
              >
                Reject
              </button>
            ) : (
              <div className="flex w-full flex-col gap-2 sm:w-auto">
                <input
                  type="text"
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  placeholder="Rejection reason (optional)"
                  className="rounded border border-[var(--border)] bg-[var(--bg)] px-2 py-1 text-sm text-[var(--text)]"
                />
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={handleReject}
                    className="rounded border border-red-500/50 px-2 py-1 text-xs text-red-300 disabled:opacity-50"
                  >
                    Confirm reject
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      setRejectOpen(false);
                      setRejectReason("");
                    }}
                    className="rounded border border-[var(--border)] px-2 py-1 text-xs disabled:opacity-50"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
