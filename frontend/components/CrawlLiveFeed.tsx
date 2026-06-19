import type { CrawlProgress } from "@/lib/sse";
import type { PipelineEvent } from "@/lib/types";

type Props = {
  progress: CrawlProgress;
  events: PipelineEvent[];
  isActive: boolean;
};

export function CrawlLiveFeed({ progress, events, isActive }: Props) {
  const failed = [...events].reverse().find((e) => e.event === "stage_failed");
  const recent = events
    .filter(
      (e) =>
        e.event === "stage_progress" ||
        e.event === "stage_completed" ||
        e.event === "stage_failed"
    )
    .slice(-8)
    .reverse();

  if (!isActive && recent.length === 0 && !progress.currentUrl) {
    return (
      <p className="text-sm text-[var(--muted)]">
        Start a crawl to see live page discovery here.
      </p>
    );
  }

  return (
    <div className="space-y-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">Live crawl feed</span>
        {(isActive || progress.pagesDiscovered > 0) && (
          <span className="text-yellow-400">
            {progress.pagesDiscovered}
            {progress.maxPages != null ? ` / ${progress.maxPages}` : ""} pages
            {progress.statesDiscovered != null && progress.statesDiscovered > 0
              ? ` (${progress.statesDiscovered} CIC states)`
              : ""}{" "}
            discovered
          </span>
        )}
      </div>
      {isActive && progress.pagesDiscovered === 0 && !progress.currentUrl && !failed && (
        <p className="text-xs text-[var(--muted)]">
          Authenticating and starting crawl… page URLs will appear here as they are discovered.
        </p>
      )}
      {progress.currentUrl && (
        <p className="truncate text-xs text-[var(--muted)]">
          Current: <span className="text-[var(--text)]">{progress.currentUrl}</span>
        </p>
      )}
      {failed?.data.error != null && String(failed.data.error).length > 0 && (
        <p className="rounded border border-red-600/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {String(failed.data.error)}
        </p>
      )}
      <ul className="max-h-40 space-y-1 overflow-y-auto font-mono text-xs text-[var(--muted)]">
        {recent.map((ev, i) => (
          <li key={`${ev.id}-${i}`} className="truncate">
            <span
              className={
                ev.event === "stage_failed" ? "text-red-400/80" : "text-yellow-400/80"
              }
            >
              {ev.event}
            </span>{" "}
            {ev.data.error
              ? String(ev.data.error)
              : ev.data.current_url
                ? String(ev.data.current_url)
                : ev.data.stage
                  ? String(ev.data.stage)
                  : ""}
          </li>
        ))}
      </ul>
    </div>
  );
}
