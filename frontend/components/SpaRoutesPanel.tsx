"use client";

import { useMemo, useState } from "react";
import type { AppMapModule, AppMapPage, AppMapResponse, AppMapSpaRoute } from "@/lib/types";

type Props = {
  appmap: AppMapResponse | null;
};

const METHOD_LABELS: Record<string, string> = {
  pushstate_listener: "Browser navigation (pushState)",
  replace_state_listener: "Browser navigation (replaceState)",
  popstate_listener: "Browser back/forward (popstate)",
  hash_route: "Hash URL (#/route)",
  cic_interaction: "UI interaction (CIC)",
  link_extraction: "Link on page",
};

function moduleName(moduleId: string | null | undefined, modules: AppMapModule[]): string {
  if (!moduleId) return "—";
  return modules.find((item) => item.module_id === moduleId)?.name || moduleId;
}

function pageTitle(pageId: string | null | undefined, pages: AppMapPage[]): string {
  if (!pageId) return "—";
  const page = pages.find((item) => item.page_id === pageId);
  if (!page) return pageId.slice(0, 8);
  return page.title || page.url;
}

function isVirtualAqaView(url: string): boolean {
  return url.includes("#__aqa_view__/");
}

function methodLabel(method: string): string {
  return METHOD_LABELS[method] || method.replace(/_/g, " ");
}

export function SpaRoutesPanel({ appmap }: Props) {
  const [view, setView] = useState<"routes" | "pages">("routes");

  const pages = appmap?.pages ?? [];
  const modules = appmap?.modules ?? [];
  const spaRoutes = appmap?.spa_routes ?? [];

  const { crawledPages, virtualViews } = useMemo(() => {
    const crawled: AppMapPage[] = [];
    const virtual: AppMapPage[] = [];
    for (const page of pages) {
      if (isVirtualAqaView(page.url)) virtual.push(page);
      else crawled.push(page);
    }
    return { crawledPages: crawled, virtualViews: virtual };
  }, [pages]);

  const routesByPattern = useMemo(() => {
    return [...spaRoutes].sort((a, b) => a.path_pattern.localeCompare(b.path_pattern));
  }, [spaRoutes]);

  const hasContent = crawledPages.length > 0 || routesByPattern.length > 0 || virtualViews.length > 0;

  if (!hasContent) {
    return (
      <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
        <h3 className="text-sm font-semibold text-[var(--text)]">Pages & SPA routes</h3>
        <p className="mt-2 text-sm text-[var(--muted)]">
          No pages or SPA routes captured yet. Run discovery on a single-page app to see hash and
          pushState routes here.
        </p>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
        <h3 className="text-sm font-semibold text-[var(--text)]">Pages & SPA routes</h3>
        <p className="mt-1 text-xs text-[var(--muted)]">
          <strong className="text-[var(--text)]">Crawled URLs</strong> are real addresses the browser
          visited. <strong className="text-[var(--text)]">SPA routes</strong> are path patterns from
          pushState/hash navigation. <strong className="text-[var(--text)]">Virtual views</strong> are
          same-URL UI states discovered via interactions (CIC).
        </p>
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            onClick={() => setView("routes")}
            className={`rounded px-3 py-1.5 text-xs ${
              view === "routes"
                ? "bg-blue-600 text-white"
                : "border border-[var(--border)] text-[var(--muted)]"
            }`}
          >
            SPA routes ({routesByPattern.length})
          </button>
          <button
            type="button"
            onClick={() => setView("pages")}
            className={`rounded px-3 py-1.5 text-xs ${
              view === "pages"
                ? "bg-blue-600 text-white"
                : "border border-[var(--border)] text-[var(--muted)]"
            }`}
          >
            URL breakdown ({crawledPages.length} real · {virtualViews.length} virtual)
          </button>
        </div>
      </div>

      {view === "routes" ? (
        routesByPattern.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">
            No SPA route patterns detected. Enable pushState listener in discovery for single-page
            apps.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--surface)] text-xs text-[var(--muted)]">
                  <th className="px-3 py-2 font-medium">Route pattern</th>
                  <th className="px-3 py-2 font-medium">How found</th>
                  <th className="px-3 py-2 font-medium">Example URLs</th>
                  <th className="px-3 py-2 font-medium">Module</th>
                  <th className="px-3 py-2 font-medium">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {routesByPattern.map((route) => (
                  <SpaRouteRow key={route.route_id} route={route} modules={modules} pages={pages} />
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <UrlListCard
            title="Real crawled URLs"
            description="Full browser addresses visited during discovery."
            items={crawledPages.map((page) => ({
              key: page.page_id,
              primary: page.title || "Untitled",
              secondary: page.url,
            }))}
          />
          <UrlListCard
            title="Virtual views (CIC)"
            description="UI states at the same URL — shown as #__aqa_view__/… during crawl."
            items={virtualViews.map((page) => ({
              key: page.page_id,
              primary: page.title || "UI state",
              secondary: page.url,
            }))}
            emptyMessage="No virtual views — enable CIC for deeper SPA interaction discovery."
          />
        </div>
      )}
    </section>
  );
}

function SpaRouteRow({
  route,
  modules,
  pages,
}: {
  route: AppMapSpaRoute;
  modules: AppMapModule[];
  pages: AppMapPage[];
}) {
  const methods = route.discovery_methods?.length
    ? route.discovery_methods
    : [route.discovery_method];
  return (
    <tr className="border-b border-[var(--border)]/60">
      <td className="px-3 py-2 font-mono text-xs text-[var(--text)]">{route.path_pattern}</td>
      <td className="px-3 py-2 text-xs text-[var(--muted)]">
        {methods.map((method) => methodLabel(method || "unknown")).join(", ")}
      </td>
      <td className="max-w-xs px-3 py-2 text-xs text-[var(--muted)]">
        {(route.url_examples || []).slice(0, 2).map((url) => (
          <div key={url} className="truncate" title={url}>
            {url}
          </div>
        ))}
      </td>
      <td className="px-3 py-2 text-xs text-[var(--muted)]">
        {moduleName(route.module_id, modules)}
        {route.page_id ? ` · ${pageTitle(route.page_id, pages)}` : ""}
      </td>
      <td className="px-3 py-2 text-xs text-[var(--muted)]">
        {Math.round((route.confidence || 0) * 100)}%
      </td>
    </tr>
  );
}

function UrlListCard({
  title,
  description,
  items,
  emptyMessage = "None",
}: {
  title: string;
  description: string;
  items: Array<{ key: string; primary: string; secondary: string }>;
  emptyMessage?: string;
}) {
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
      <h4 className="text-sm font-medium text-[var(--text)]">{title}</h4>
      <p className="mt-1 text-xs text-[var(--muted)]">{description}</p>
      {items.length === 0 ? (
        <p className="mt-3 text-sm text-[var(--muted)]">{emptyMessage}</p>
      ) : (
        <ul className="mt-3 max-h-64 space-y-2 overflow-y-auto text-sm">
          {items.map((item) => (
            <li key={item.key} className="rounded border border-[var(--border)] px-3 py-2">
              <div className="font-medium text-[var(--text)]">{item.primary}</div>
              <div className="mt-0.5 truncate font-mono text-[11px] text-[var(--muted)]" title={item.secondary}>
                {item.secondary}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
