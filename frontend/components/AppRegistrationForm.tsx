"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CrawlSettingsFields } from "@/components/CrawlSettingsFields";
import {
  defaultCrawlSettings,
  parseCicMode,
  parseCrawlLimitInput,
  toCrawlConfigPayload,
  CRAWL_LIMITS,
} from "@/lib/crawlConfig";
import { loadSettings } from "@/lib/settings";

function parseApiError(text: string, status: number): string {
  if (status >= 500 || text.includes("Internal Server Error") || text.includes("socket hang up")) {
    return (
      "Backend API is not reachable on port 3001. From the project root run: pnpm dev:api " +
      "(and ensure PostgreSQL + Redis are running). If it was already running, restart it: " +
      "lsof -ti :3001 | xargs kill -9 && pnpm dev:api"
    );
  }
  try {
    const json = JSON.parse(text) as { detail?: unknown; title?: string };
    if (typeof json.detail === "string") return json.detail;
    if (Array.isArray(json.detail)) {
      return json.detail
        .map((d: { msg?: string; loc?: string[] }) => d.msg || JSON.stringify(d))
        .join("; ");
    }
    if (json.title) return json.title;
  } catch {
    /* plain text */
  }
  return text || "Registration failed";
}

export function AppRegistrationForm() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [includeLogin, setIncludeLogin] = useState(false);
  const [autoStartCrawl, setAutoStartCrawl] = useState(false);
  const [crawlSettings, setCrawlSettings] = useState(defaultCrawlSettings);

  useEffect(() => {
    setAutoStartCrawl(loadSettings().autoStartCrawl);
  }, []);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const form = new FormData(e.currentTarget);

    const settings = {
      maxPages: parseCrawlLimitInput(
        String(form.get("max_pages") ?? crawlSettings.maxPages),
        crawlSettings.maxPages,
        CRAWL_LIMITS.maxPages.min,
        CRAWL_LIMITS.maxPages.max
      ),
      maxDepth: parseCrawlLimitInput(
        String(form.get("max_depth") ?? crawlSettings.maxDepth),
        crawlSettings.maxDepth,
        CRAWL_LIMITS.maxDepth.min,
        CRAWL_LIMITS.maxDepth.max
      ),
      cicMode: parseCicMode(form.get("cic_mode") ?? crawlSettings.cicMode),
    };

    const body: Record<string, unknown> = {
      name: String(form.get("name")),
      base_url: String(form.get("base_url")),
      crawl_config: toCrawlConfigPayload(settings),
    };

    if (includeLogin) {
      const email = String(form.get("email") || "").trim();
      const password = String(form.get("password") || "").trim();
      const loginUrl = String(form.get("login_url") || "").trim();
      const emailSelector = String(form.get("email_selector") || "").trim();
      const passwordSelector = String(form.get("password_selector") || "").trim();
      const submitSelector = String(form.get("submit_selector") || "").trim();

      const authConfig: Record<string, unknown> = { type: "form" };
      if (loginUrl) authConfig.login_url = loginUrl;
      if (emailSelector) authConfig.email_selector = emailSelector;
      if (passwordSelector) authConfig.password_selector = passwordSelector;
      if (submitSelector) authConfig.submit_selector = submitSelector;

      if (email && password) {
        authConfig.credentials = { email, password };
      } else if (email || password) {
        setError("Provide both username/email and password, or leave login fields empty.");
        setLoading(false);
        return;
      }

      if (Object.keys(authConfig).length > 1 || authConfig.credentials) {
        body.auth_config = authConfig;
      }
    }

    try {
      const res = await fetch("/api/v1/apps", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(parseApiError(await res.text(), res.status));
      const app = await res.json();
      const qs = autoStartCrawl ? "?auto_crawl=1" : "";
      router.push(`/apps/${app.app_id}${qs}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="max-w-lg space-y-4">
      <div>
        <label className="mb-1 block text-sm">App name</label>
        <input
          name="name"
          required
          className="w-full rounded border border-[var(--border)] bg-[var(--surface)] px-3 py-2"
        />
      </div>
      <div>
        <label className="mb-1 block text-sm">Base URL</label>
        <input
          name="base_url"
          required
          type="url"
          placeholder="https://your-app.example.com"
          className="w-full rounded border border-[var(--border)] bg-[var(--surface)] px-3 py-2"
        />
      </div>

      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
        <p className="mb-3 text-sm font-medium">Crawl settings</p>
        <CrawlSettingsFields
          settings={crawlSettings}
          onChange={setCrawlSettings}
          useFormNames
        />
      </div>

      <label className="flex cursor-pointer items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={includeLogin}
          onChange={(e) => setIncludeLogin(e.target.checked)}
        />
        Include login credentials (optional)
      </label>

      {includeLogin && (
        <div className="space-y-4 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
          <div>
            <label className="mb-1 block text-sm">Username / email</label>
            <input
              name="email"
              className="w-full rounded border border-[var(--border)] bg-[var(--bg)] px-3 py-2"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm">Password</label>
            <input
              name="password"
              type="password"
              className="w-full rounded border border-[var(--border)] bg-[var(--bg)] px-3 py-2"
            />
          </div>
          <details className="text-sm text-[var(--muted)]">
            <summary className="cursor-pointer">Advanced login selectors</summary>
            <div className="mt-2 space-y-2">
              <input
                name="login_url"
                placeholder="Login URL path"
                className="w-full rounded border border-[var(--border)] bg-[var(--bg)] px-3 py-2"
              />
              <input
                name="email_selector"
                placeholder="Email selector (default: input[type=email])"
                className="w-full rounded border border-[var(--border)] bg-[var(--bg)] px-3 py-2"
              />
              <input
                name="password_selector"
                placeholder="Password selector (default: input[type=password])"
                className="w-full rounded border border-[var(--border)] bg-[var(--bg)] px-3 py-2"
              />
              <input
                name="submit_selector"
                placeholder="Submit selector (default: button[type=submit])"
                className="w-full rounded border border-[var(--border)] bg-[var(--bg)] px-3 py-2"
              />
            </div>
          </details>
        </div>
      )}

      <label className="flex cursor-pointer items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={autoStartCrawl}
          onChange={(e) => setAutoStartCrawl(e.target.checked)}
        />
        Auto-start crawl after registration
      </label>
      <p className="text-xs text-[var(--muted)]">
        Default can be changed in{" "}
        <a href="/settings" className="text-blue-400 hover:underline">
          Settings
        </a>
        .
      </p>

      {error && <p className="text-sm text-red-400">{error}</p>}
      <button
        disabled={loading}
        type="submit"
        className="rounded-lg bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50"
      >
        {loading ? "Registering…" : "Register & continue"}
      </button>
    </form>
  );
}
