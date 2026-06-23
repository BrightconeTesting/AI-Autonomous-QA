import type { CrawlProgress } from "@/lib/sse";
import type { PipelineEvent } from "@/lib/types";

type Props = {
  progress: CrawlProgress;
  events: PipelineEvent[];
  isActive: boolean;
};

function formatProgressEvent(ev: PipelineEvent): string {
  const d = ev.data;
  if (d.error) return String(d.error);
  if (d.discovered_url) return `+ ${String(d.discovered_url)}`;
  if (d.view_label && d.phase === "new_state") {
    return `state: ${String(d.view_label)}`;
  }
  if (d.view_label) return String(d.view_label);
  if (d.current_url) return String(d.current_url);
  if (d.stage) return String(d.stage);
  return "";
}

export function CrawlLiveFeed({ progress, events, isActive }: Props) {
  const failed = [...events].reverse().find((e) => e.event === "stage_failed");
  const recent = events
    .filter(
      (e) =>
        e.event === "stage_progress" ||
        e.event === "stage_completed" ||
        e.event === "stage_failed"
    )
    .slice(-12)
    .reverse();

  const exploringCic =
    isActive &&
    progress.pagesDiscovered === 0 &&
    (progress.statesDiscovered > 0 || progress.interactionsExecuted > 0);

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
        {(isActive || progress.pagesDiscovered > 0 || progress.statesDiscovered > 0) && (
          <span className="text-yellow-400">
            {progress.pagesDiscovered}
            {progress.maxPages != null ? ` / ${progress.maxPages}` : ""} pages
            {progress.statesDiscovered > 0
              ? ` · ${progress.statesDiscovered} CIC states`
              : ""}
            {progress.interactionsExecuted > 0
              ? ` · ${progress.interactionsExecuted} interactions`
              : ""}
          </span>
        )}
      </div>

      {isActive && progress.pagesDiscovered === 0 && !progress.currentUrl && !failed && (
        <p className="text-xs text-[var(--muted)]">
          Authenticating and starting crawl…
        </p>
      )}

      {exploringCic && (
        <p className="text-xs text-yellow-400/90">
          CIC exploring current page
          {progress.latestViewLabel ? `: ${progress.latestViewLabel}` : ""}
          …
        </p>
      )}

      {progress.currentUrl && (
        <p className="truncate text-xs text-[var(--muted)]">
          Current: <span className="text-[var(--text)]">{progress.currentUrl}</span>
        </p>
      )}

      {progress.discoveredUrls.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-[var(--muted)]">
            Found URLs ({progress.discoveredUrls.length})
          </p>
          <ul className="max-h-28 space-y-0.5 overflow-y-auto font-mono text-xs text-green-400/90">
            {progress.discoveredUrls.map((url) => (
              <li key={url} className="truncate">
                {url}
              </li>
            ))}
          </ul>
        </div>
      )}

      {failed?.data.error != null && String(failed.data.error).length > 0 && (
        <p className="rounded border border-red-600/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {String(failed.data.error)}
        </p>
      )}

      <ul className="max-h-40 space-y-1 overflow-y-auto font-mono text-xs text-[var(--muted)]">
        {recent.map((ev, i) => {
          const label = formatProgressEvent(ev);
          if (!label) return null;
          return (
            <li key={`${ev.id}-${i}`} className="truncate">
              <span
                className={
                  ev.event === "stage_failed" ? "text-red-400/80" : "text-yellow-400/80"
                }
              >
                {ev.event}
              </span>{" "}
              {label}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
