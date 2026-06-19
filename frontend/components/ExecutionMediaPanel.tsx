"use client";

import { useMemo, useState } from "react";
import { apiClient } from "@/lib/api";
import type { ExecutionHighlight } from "@/lib/types";
import { TraceTimeline } from "./TraceTimeline";
import { VideoPlayer } from "./VideoPlayer";

type Props = {
  highlight: ExecutionHighlight;
  onArtifactDeleted?: () => void;
};

export function ExecutionMediaPanel({ highlight, onArtifactDeleted }: Props) {
  const activeScenario = highlight.activeTestcaseId;
  const scenarioResult = activeScenario
    ? highlight.scenarioOutcomes[activeScenario]
    : null;

  const videoId =
    scenarioResult?.videoArtifactId ??
    Object.values(highlight.scenarioOutcomes).find((s) => s.videoArtifactId)
      ?.videoArtifactId ??
    null;

  const stepResults = useMemo(() => {
    if (!activeScenario) return [];
    return Object.values(highlight.stepOutcomes[activeScenario] ?? {}).sort(
      (a, b) => a.index - b.index
    );
  }, [activeScenario, highlight.stepOutcomes]);

  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    if (!videoId || deleting) return;
    setDeleting(true);
    try {
      await apiClient.deleteArtifact(videoId);
      onArtifactDeleted?.();
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-4 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
      <h3 className="text-sm font-medium">Execution media</h3>
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <p className="mb-2 text-xs text-[var(--muted)]">Live screenshot</p>
          {highlight.liveScreenshotArtifactId ? (
            <img
              src={apiClient.artifactStreamUrl(highlight.liveScreenshotArtifactId)}
              alt="Step screenshot"
              className="max-h-48 w-full rounded border border-[var(--border)] object-contain bg-black/40"
            />
          ) : (
            <div className="flex h-32 items-center justify-center rounded border border-dashed border-[var(--border)] text-xs text-[var(--muted)]">
              Screenshot appears during execution
            </div>
          )}
        </div>
        <div>
          <p className="mb-2 text-xs text-[var(--muted)]">Recording</p>
          <VideoPlayer
            artifactId={videoId}
            onDelete={videoId ? handleDelete : undefined}
          />
        </div>
      </div>
      <TraceTimeline
        steps={stepResults}
        activeIndex={highlight.activeStepIndex}
      />
    </div>
  );
}
