"use client";

import { useEffect, useRef, useState } from "react";
import { apiClient } from "@/lib/api";

type Props = {
  artifactId: string | null;
  seekToMs?: number | null;
  onDelete?: () => void;
};

export function VideoPlayer({ artifactId, seekToMs, onDelete }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    setLoadError(null);
  }, [artifactId]);

  useEffect(() => {
    if (seekToMs == null || !videoRef.current) return;
    videoRef.current.currentTime = seekToMs / 1000;
  }, [seekToMs, artifactId]);

  if (!artifactId) {
    return (
      <div className="flex aspect-video items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--surface)] text-sm text-[var(--muted)]">
        Video will appear when a scenario completes
      </div>
    );
  }

  const src = apiClient.artifactStreamUrl(artifactId);

  return (
    <div className="space-y-2">
      <video
        ref={videoRef}
        key={artifactId}
        controls
        preload="metadata"
        playsInline
        className="aspect-video w-full rounded-lg border border-[var(--border)] bg-black"
        src={src}
        onError={() =>
          setLoadError(
            "Video failed to load. Ensure pnpm dev:api is running on port 3001."
          )
        }
      >
        <track kind="captions" />
      </video>
      {loadError && (
        <p className="text-xs text-red-400">{loadError}</p>
      )}
      {onDelete && (
        <button
          type="button"
          onClick={onDelete}
          className="text-xs text-red-400 hover:underline"
        >
          Delete video
        </button>
      )}
    </div>
  );
}
