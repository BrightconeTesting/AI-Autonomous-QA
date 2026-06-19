"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { TraceTimeline } from "@/components/TraceTimeline";
import { VideoPlayer } from "@/components/VideoPlayer";
import { apiClient } from "@/lib/api";
import type { TestRunDetail } from "@/lib/types";

export default function RunDetailPage({ params }: { params: { id: string } }) {
  const runId = params.id;
  const [run, setRun] = useState<TestRunDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [activeVideo, setActiveVideo] = useState<string | null>(null);
  const [activeScenarioId, setActiveScenarioId] = useState<string | null>(null);
  const [seekToMs, setSeekToMs] = useState<number | null>(null);

  const load = useCallback(async () => {
    const detail = await apiClient.getRun(runId);
    setRun(detail);
    const firstVideo = detail.results
      .map((r) => r.video_artifact_id)
      .find((id) => id);
    if (firstVideo && !activeVideo) setActiveVideo(firstVideo);
  }, [runId, activeVideo]);

  useEffect(() => {
    load().catch(console.error);
  }, [load]);

  async function retryFailed() {
    if (!run) return;
    const failedIds = run.results.filter((r) => r.outcome === "failed").map((r) => r.testcase_id);
    if (failedIds.length === 0) return;
    setBusy(true);
    try {
      const result = await apiClient.execute(run.app_id, failedIds, {
        retry_from_run_id: runId,
        retry_mode: "failed_only",
      });
      window.location.href = `/apps/${run.app_id}`;
    } catch (err) {
      alert(err instanceof Error ? err.message : "Retry failed");
    } finally {
      setBusy(false);
    }
  }

  if (!run) {
    return <p className="text-[var(--muted)]">Loading run…</p>;
  }

  const failedCount = run.results.filter((r) => r.outcome === "failed").length;

  return (
    <div className="space-y-6">
      <Link href={`/apps/${run.app_id}`} className="text-sm text-[var(--muted)] hover:underline">
        ← Back to app
      </Link>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Run {run.run_id.slice(0, 8)}…</h1>
          <p className="text-sm capitalize text-[var(--muted)]">{run.status}</p>
        </div>
        {failedCount > 0 && (
          <button
            disabled={busy}
            onClick={retryFailed}
            className="rounded bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            Re-run failed ({failedCount})
          </button>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-4">
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 text-center">
          <div className="text-2xl font-semibold">{run.summary.total}</div>
          <div className="text-xs text-[var(--muted)]">Total</div>
        </div>
        <div className="rounded-lg border border-green-600/30 bg-green-500/10 p-4 text-center">
          <div className="text-2xl font-semibold text-green-400">{run.summary.passed}</div>
          <div className="text-xs text-[var(--muted)]">Passed</div>
        </div>
        <div className="rounded-lg border border-red-600/30 bg-red-500/10 p-4 text-center">
          <div className="text-2xl font-semibold text-red-400">{run.summary.failed}</div>
          <div className="text-xs text-[var(--muted)]">Failed</div>
        </div>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 text-center">
          <div className="text-2xl font-semibold">{run.summary.skipped}</div>
          <div className="text-xs text-[var(--muted)]">Skipped</div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <ul className="space-y-2">
          {run.results.map((result) => (
            <li
              key={result.testcase_id}
              className={`rounded border p-3 ${
                result.outcome === "passed"
                  ? "border-green-600/40"
                  : result.outcome === "failed"
                    ? "border-red-600/40"
                    : "border-[var(--border)]"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">{result.name}</span>
                <span
                  className={`text-xs capitalize ${
                    result.outcome === "passed" ? "text-green-400" : "text-red-400"
                  }`}
                >
                  {result.outcome}
                </span>
              </div>
              {result.error && (
                <p className="mt-1 text-xs text-red-400">{result.error}</p>
              )}
              {result.video_artifact_id && (
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    key={result.video_artifact_id}
                    type="button"
                    onClick={() => {
                      setActiveScenarioId(result.testcase_id);
                      setActiveVideo(result.video_artifact_id!);
                      setSeekToMs(null);
                    }}
                    className="text-xs text-blue-400 hover:underline"
                  >
                    Play recording
                  </button>
                </div>
              )}
              <ol className="mt-2 space-y-0.5 text-xs text-[var(--muted)]">
                {result.step_results.map((step) => (
                  <li
                    key={step.index}
                    className={
                      step.outcome === "failed" ? "text-red-400" : step.outcome === "passed" ? "text-green-400/80" : ""
                    }
                  >
                    {step.keyword} {step.text}
                    {step.duration_ms != null && ` (${step.duration_ms}ms)`}
                  </li>
                ))}
              </ol>
            </li>
          ))}
        </ul>
        <div className="space-y-3">
          <VideoPlayer
            artifactId={activeVideo}
            seekToMs={seekToMs}
            onDelete={
              activeVideo
                ? async () => {
                    await apiClient.deleteArtifact(activeVideo);
                    setActiveVideo(null);
                    load();
                  }
                : undefined
            }
          />
          {activeScenarioId && (
            <TraceTimeline
              steps={
                run.results.find((r) => r.testcase_id === activeScenarioId)?.step_results ?? []
              }
              activeIndex={null}
              onSeek={(stepIndex) => {
                const scenario = run.results.find((r) => r.testcase_id === activeScenarioId);
                const ts = scenario?.step_timestamps_ms?.[stepIndex];
                if (ts != null) setSeekToMs(ts);
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
