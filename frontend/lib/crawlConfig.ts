export const CRAWL_LIMITS = {
  maxPages: { min: 1, max: 500, default: 50 },
  maxDepth: { min: 1, max: 10, default: 5 },
} as const;

export type CicMode = "fast" | "full";

export type CrawlSettings = {
  maxPages: number;
  maxDepth: number;
  cicMode: CicMode;
};

/** @deprecated Use CrawlSettings */
export type CrawlLimits = Pick<CrawlSettings, "maxPages" | "maxDepth">;

export function defaultCrawlSettings(): CrawlSettings {
  return {
    maxPages: CRAWL_LIMITS.maxPages.default,
    maxDepth: CRAWL_LIMITS.maxDepth.default,
    cicMode: "full",
  };
}

/** @deprecated Use defaultCrawlSettings */
export function defaultCrawlLimits(): CrawlLimits {
  const { maxPages, maxDepth } = defaultCrawlSettings();
  return { maxPages, maxDepth };
}

export function parseCicMode(raw: unknown): CicMode {
  return raw === "fast" ? "fast" : "full";
}

export function crawlSettingsFromConfig(
  crawlConfig: Record<string, unknown> | null | undefined
): CrawlSettings {
  const maxPages = Number(crawlConfig?.max_pages);
  const maxDepth = Number(crawlConfig?.max_depth);
  return {
    maxPages: clamp(
      Number.isFinite(maxPages) ? maxPages : CRAWL_LIMITS.maxPages.default,
      CRAWL_LIMITS.maxPages.min,
      CRAWL_LIMITS.maxPages.max
    ),
    maxDepth: clamp(
      Number.isFinite(maxDepth) ? maxDepth : CRAWL_LIMITS.maxDepth.default,
      CRAWL_LIMITS.maxDepth.min,
      CRAWL_LIMITS.maxDepth.max
    ),
    cicMode: parseCicMode(crawlConfig?.cic_mode),
  };
}

/** @deprecated Use crawlSettingsFromConfig */
export function crawlLimitsFromConfig(
  crawlConfig: Record<string, unknown> | null | undefined
): CrawlLimits {
  const { maxPages, maxDepth } = crawlSettingsFromConfig(crawlConfig);
  return { maxPages, maxDepth };
}

export function toCrawlConfigPayload(settings: CrawlSettings): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    enable_cic: true,
    cic_mode: settings.cicMode,
    max_pages: clamp(
      settings.maxPages,
      CRAWL_LIMITS.maxPages.min,
      CRAWL_LIMITS.maxPages.max
    ),
    max_depth: clamp(
      settings.maxDepth,
      CRAWL_LIMITS.maxDepth.min,
      CRAWL_LIMITS.maxDepth.max
    ),
  };

  if (settings.cicMode === "full") {
    payload.cic_unlimited_interactions = true;
    payload.cic_in_page_only = false;
    payload.cic_rich_interactions = true;
    payload.cic_enable_tables = true;
    payload.cic_enable_date_pickers = true;
    payload.cic_enable_iframes = true;
    payload.safe_form_fill = true;
    payload.max_interaction_depth = 10;
    payload.max_states_per_url = 100;
    payload.max_states_total = 2000;
    payload.cic_max_options_per_select = 20;
  }

  return payload;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, Math.round(value)));
}

export function parseCrawlLimitInput(
  raw: string,
  fallback: number,
  min: number,
  max: number
): number {
  const n = Number(raw);
  if (!Number.isFinite(n)) return fallback;
  return clamp(n, min, max);
}
