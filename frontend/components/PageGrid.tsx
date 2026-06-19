import type { AppMapPage } from "@/lib/types";
import { apiClient } from "@/lib/api";

type Props = {
  appId: string;
  pages: AppMapPage[];
};

export function PageGrid({ appId, pages }: Props) {
  if (pages.length === 0) {
    return (
      <p className="text-sm text-[var(--muted)]">No crawled pages yet. Run discovery first.</p>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {pages.map((page) => (
        <article
          key={page.page_id}
          className="overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--surface)]"
        >
          {page.screenshot_path ? (
            <img
              src={apiClient.pageScreenshotUrl(appId, page.page_id)}
              alt={page.title || page.url}
              className="aspect-video w-full border-b border-[var(--border)] bg-black/40 object-cover object-top"
            />
          ) : (
            <div className="flex aspect-video items-center justify-center border-b border-[var(--border)] text-xs text-[var(--muted)]">
              No screenshot
            </div>
          )}
          <div className="p-3">
            <h3 className="truncate text-sm font-medium">{page.title || "Untitled page"}</h3>
            <p className="mt-1 truncate text-xs text-[var(--muted)]">{page.url}</p>
          </div>
        </article>
      ))}
    </div>
  );
}
