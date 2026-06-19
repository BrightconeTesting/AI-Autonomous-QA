"use client";

import { useEffect, useState } from "react";

type Health = { status?: string; db?: string; redis?: string };
type QueueStats = { queues?: Record<string, number> } | null;

export function SystemStatusBar() {
  const [health, setHealth] = useState<Health | null>(null);
  const [queues, setQueues] = useState<QueueStats>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch("/health", { signal: AbortSignal.timeout(3000) });
        setHealth(await res.json());
      } catch {
        setHealth({ status: "down" });
      }
      setQueues(
        await fetch("/api/v1/queues/stats", { signal: AbortSignal.timeout(3000) })
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null)
      );
    };
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, []);

  const dot = (ok: boolean | undefined) => (
    <span
      className={`inline-block h-2 w-2 rounded-full ${ok ? "bg-green-500" : "bg-red-500"}`}
      aria-hidden
    />
  );

  const apiOk = health?.status === "ok";
  const redisOk = health?.redis === "ok";
  const dbOk = health?.db === "ok";
  const queueDepth = queues?.queues
    ? Object.values(queues.queues).reduce((a, b) => a + b, 0)
    : null;

  const showBanner = health && (!apiOk || !redisOk);

  return (
    <>
      <div className="border-b border-[var(--border)] bg-[var(--surface)] px-4 py-2 text-xs text-[var(--muted)]">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4">
          <span className="flex items-center gap-1">
            {dot(apiOk)} API
          </span>
          <span className="flex items-center gap-1">
            {dot(dbOk)} DB
          </span>
          <span className="flex items-center gap-1">
            {dot(redisOk)} Redis
          </span>
          {queueDepth != null && (
            <span className="text-[var(--muted)]">
              Queue depth: {queueDepth}
            </span>
          )}
        </div>
      </div>
      {showBanner && (
        <div className="border-b border-red-600/40 bg-red-500/10 px-4 py-2 text-center text-xs text-red-300">
          {!apiOk ? (
            <>
              API not running on port 3001 — in a <strong>new terminal</strong> from the project root run:{" "}
              <code className="rounded bg-black/30 px-1">pnpm dev:api</code>
            </>
          ) : (
            <>
              Redis unavailable — start Redis:{" "}
              <code className="rounded bg-black/30 px-1">brew services start redis</code>
            </>
          )}
        </div>
      )}
    </>
  );
}
