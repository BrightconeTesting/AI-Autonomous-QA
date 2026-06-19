"use client";

import { CRAWL_LIMITS, type CicMode, type CrawlSettings } from "@/lib/crawlConfig";

type Props = {
  settings: CrawlSettings;
  onChange: (settings: CrawlSettings) => void;
  disabled?: boolean;
  /** Use `name` attributes for native form submit (registration). */
  useFormNames?: boolean;
};

const CIC_MODE_HELP: Record<CicMode, string> = {
  fast: "Speed-optimized — in-page widgets only; skips most nav buttons.",
  full: "Unlimited CIC — clicks all safe elements; URL changes become new pages; same-URL views become virtual pages.",
};

export function CrawlSettingsFields({
  settings,
  onChange,
  disabled = false,
  useFormNames = false,
}: Props) {
  return (
    <div className="space-y-4">
      <div>
        <label className="mb-1 block text-sm" htmlFor="crawl-cic-mode">
          CIC crawl mode
        </label>
        <select
          id="crawl-cic-mode"
          name={useFormNames ? "cic_mode" : undefined}
          value={settings.cicMode}
          disabled={disabled}
          onChange={(e) =>
            onChange({ ...settings, cicMode: e.target.value === "fast" ? "fast" : "full" })
          }
          className="w-full rounded border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm disabled:opacity-50"
        >
          <option value="full">Full — deep CIC (recommended for SPAs)</option>
          <option value="fast">Fast — link crawl + light in-page CIC</option>
        </select>
        <p className="mt-1 text-xs text-[var(--muted)]">{CIC_MODE_HELP[settings.cicMode]}</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-sm" htmlFor="crawl-max-pages">
            Max pages
          </label>
          <input
            id="crawl-max-pages"
            name={useFormNames ? "max_pages" : undefined}
            type="number"
            min={CRAWL_LIMITS.maxPages.min}
            max={CRAWL_LIMITS.maxPages.max}
            value={settings.maxPages}
            disabled={disabled}
            onChange={(e) =>
              onChange({ ...settings, maxPages: Number(e.target.value) || settings.maxPages })
            }
            className="w-full rounded border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm disabled:opacity-50"
          />
          <p className="mt-1 text-xs text-[var(--muted)]">
            {CRAWL_LIMITS.maxPages.min}–{CRAWL_LIMITS.maxPages.max} pages per crawl
          </p>
        </div>
        <div>
          <label className="mb-1 block text-sm" htmlFor="crawl-max-depth">
            Max depth
          </label>
          <input
            id="crawl-max-depth"
            name={useFormNames ? "max_depth" : undefined}
            type="number"
            min={CRAWL_LIMITS.maxDepth.min}
            max={CRAWL_LIMITS.maxDepth.max}
            value={settings.maxDepth}
            disabled={disabled}
            onChange={(e) =>
              onChange({ ...settings, maxDepth: Number(e.target.value) || settings.maxDepth })
            }
            className="w-full rounded border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm disabled:opacity-50"
          />
          <p className="mt-1 text-xs text-[var(--muted)]">
            Link hops from start URL ({CRAWL_LIMITS.maxDepth.min}–{CRAWL_LIMITS.maxDepth.max})
          </p>
        </div>
      </div>
    </div>
  );
}
