"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiClient, ApiError } from "@/lib/api";
import type { Application } from "@/lib/types";

type Props = {
  initialApps: Application[];
};

export function AppList({ initialApps }: Props) {
  const router = useRouter();
  const [apps, setApps] = useState(initialApps);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function deleteApp(app: Application) {
    const confirmed = window.confirm(
      `Delete "${app.name}"?\n\nThis removes the app and all crawled pages, scenarios, runs, and artifacts from the database. This cannot be undone.`
    );
    if (!confirmed) return;

    setBusyId(app.app_id);
    setError(null);
    try {
      await apiClient.deleteApp(app.app_id);
      setApps((prev) => prev.filter((a) => a.app_id !== app.app_id));
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError(
          `Cannot delete "${app.name}" while a pipeline is running. Open the app and stop the pipeline first.`
        );
      } else {
        setError(err instanceof Error ? err.message : "Delete failed");
      }
    } finally {
      setBusyId(null);
    }
  }

  if (apps.length === 0) {
    return (
      <p className="text-sm text-[var(--muted)]">
        No applications yet. Register one to get started.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {error && (
        <p className="rounded border border-red-600/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {error}
        </p>
      )}
      <ul className="divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
        {apps.map((app) => (
          <li key={app.app_id} className="flex items-center gap-3 px-4 py-3">
            <Link href={`/apps/${app.app_id}`} className="min-w-0 flex-1 hover:opacity-90">
              <div className="font-medium">{app.name}</div>
              <div className="truncate text-sm text-[var(--muted)]">{app.base_url}</div>
            </Link>
            <button
              type="button"
              disabled={busyId === app.app_id}
              onClick={() => deleteApp(app)}
              className="shrink-0 rounded border border-red-600/40 px-2 py-1 text-xs text-red-300 hover:bg-red-500/10 disabled:opacity-50"
            >
              {busyId === app.app_id ? "Deleting…" : "Delete"}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
