"use client";

import type { AppMapModule, AppMapPage, AppMapResponse, AuthIntelligence } from "@/lib/types";

type Props = {
  appmap: AppMapResponse | null;
};

const SESSION_LABELS: Record<string, string> = {
  cookie: "Cookie session",
  bearer: "Bearer / API token",
  form: "Form-based login",
  oauth: "OAuth / SSO",
  basic: "Basic authentication",
};

function moduleName(moduleId: string, modules: AppMapModule[]): string {
  const mod = modules.find((item) => item.module_id === moduleId);
  return mod?.name || moduleId;
}

function pageLabel(pageId: string, pages: AppMapPage[]): string {
  const page = pages.find((item) => item.page_id === pageId);
  if (!page) return pageId.slice(0, 8);
  return page.title || page.url;
}

function hasAuthSignals(auth: AuthIntelligence | null | undefined): boolean {
  if (!auth) return false;
  return Boolean(
    auth.login_flow_id ||
      auth.login_api_endpoint_id ||
      auth.authenticated ||
      (auth.personas?.length ?? 0) > 0 ||
      (auth.cookie_names?.length ?? 0) > 0 ||
      (auth.storage_keys?.length ?? 0) > 0 ||
      (auth.protected_page_ids?.length ?? 0) > 0 ||
      (auth.blockers?.length ?? 0) > 0
  );
}

export function AuthIntelligenceCard({ appmap }: Props) {
  const auth = appmap?.auth_intelligence;
  const modules = appmap?.modules ?? [];
  const pages = appmap?.pages ?? [];

  if (!hasAuthSignals(auth)) {
    return (
      <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
        <h3 className="text-sm font-semibold text-[var(--text)]">Authentication</h3>
        <p className="mt-2 text-sm text-[var(--muted)]">
          No login session was detected during discovery. If the app requires sign-in, add credentials
          under Advanced discovery → Personas and re-run the crawl.
        </p>
      </section>
    );
  }

  const sessionLabel = SESSION_LABELS[auth?.session_type || ""] || auth?.session_type || "Unknown";
  const matrix = auth?.visibility_matrix ?? {};
  const personaRows =
    auth?.personas && auth.personas.length > 0
      ? auth.personas
      : Object.keys(matrix).map((personaId) => ({
          persona_id: personaId,
          label: personaId,
          authenticated: true,
          visible_module_ids: matrix[personaId]?.visible_module_ids ?? [],
          exclusive_module_ids: matrix[personaId]?.exclusive_module_ids ?? [],
        }));

  return (
    <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-[var(--text)]">Authentication & access</h3>
          <p className="mt-1 text-xs text-[var(--muted)]">
            How discovery detected sign-in and which parts of the app each persona can reach.
          </p>
        </div>
        <span
          className={`rounded-full px-2.5 py-1 text-xs font-medium ${
            auth?.authenticated
              ? "bg-green-500/15 text-green-300"
              : "bg-amber-500/15 text-amber-300"
          }`}
        >
          {auth?.authenticated ? "Session active during crawl" : "Session not confirmed"}
        </span>
      </div>

      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <div className="rounded border border-[var(--border)] p-3">
          <dt className="text-xs text-[var(--muted)]">Session type</dt>
          <dd className="mt-1 text-sm font-medium text-[var(--text)]">{sessionLabel}</dd>
        </div>
        <div className="rounded border border-[var(--border)] p-3">
          <dt className="text-xs text-[var(--muted)]">Protected pages</dt>
          <dd className="mt-1 text-sm font-medium text-[var(--text)]">
            {auth?.protected_page_ids?.length ?? 0}
          </dd>
        </div>
        <div className="rounded border border-[var(--border)] p-3">
          <dt className="text-xs text-[var(--muted)]">Protected APIs</dt>
          <dd className="mt-1 text-sm font-medium text-[var(--text)]">
            {auth?.protected_api_endpoint_ids?.length ?? 0}
          </dd>
        </div>
      </dl>

      {(auth?.cookie_names?.length ?? 0) > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium text-[var(--muted)]">Session cookies observed</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {auth!.cookie_names!.map((name) => (
              <span
                key={name}
                className="rounded bg-[var(--bg)] px-2 py-0.5 font-mono text-[11px] text-[var(--text)]"
              >
                {name}
              </span>
            ))}
          </div>
        </div>
      )}

      {(auth?.storage_keys?.length ?? 0) > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium text-[var(--muted)]">Browser storage keys</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {auth!.storage_keys!.map((key) => (
              <span
                key={key}
                className="rounded bg-[var(--bg)] px-2 py-0.5 font-mono text-[11px] text-[var(--text)]"
              >
                {key}
              </span>
            ))}
          </div>
        </div>
      )}

      {personaRows.length > 0 && (
        <div className="mt-4">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
            Persona visibility
          </h4>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[480px] text-left text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] text-xs text-[var(--muted)]">
                  <th className="py-2 pr-3 font-medium">Persona</th>
                  <th className="py-2 pr-3 font-medium">Status</th>
                  <th className="py-2 pr-3 font-medium">Can see modules</th>
                  <th className="py-2 font-medium">Exclusive modules</th>
                </tr>
              </thead>
              <tbody>
                {personaRows.map((persona) => {
                  const visible =
                    persona.visible_module_ids?.length
                      ? persona.visible_module_ids
                      : matrix[persona.persona_id]?.visible_module_ids ?? [];
                  const exclusive =
                    persona.exclusive_module_ids?.length
                      ? persona.exclusive_module_ids
                      : matrix[persona.persona_id]?.exclusive_module_ids ?? [];
                  return (
                    <tr key={persona.persona_id} className="border-b border-[var(--border)]/60">
                      <td className="py-2 pr-3 font-medium text-[var(--text)]">
                        {persona.label || persona.persona_id}
                      </td>
                      <td className="py-2 pr-3 text-[var(--muted)]">
                        {persona.authenticated ? "Signed in" : "Anonymous"}
                      </td>
                      <td className="py-2 pr-3 text-[var(--muted)]">
                        {visible.length > 0
                          ? visible.map((id) => moduleName(id, modules)).join(", ")
                          : "—"}
                      </td>
                      <td className="py-2 text-[var(--muted)]">
                        {exclusive.length > 0
                          ? exclusive.map((id) => moduleName(id, modules)).join(", ")
                          : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {(auth?.protected_page_ids?.length ?? 0) > 0 && (
        <div className="mt-4">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
            Protected pages (sample)
          </h4>
          <ul className="mt-2 space-y-1 text-sm text-[var(--muted)]">
            {auth!.protected_page_ids!.slice(0, 6).map((pageId) => (
              <li key={pageId}>• {pageLabel(pageId, pages)}</li>
            ))}
          </ul>
        </div>
      )}

      {(auth?.blockers?.length ?? 0) > 0 && (
        <div className="mt-4 rounded border border-amber-500/30 bg-amber-500/5 p-3">
          <h4 className="text-xs font-semibold text-amber-200">Auth blockers</h4>
          <ul className="mt-2 space-y-1 text-sm text-[var(--muted)]">
            {auth!.blockers!.map((blocker, index) => (
              <li key={`${blocker.type}-${index}`}>
                • {blocker.message || blocker.type}
                {blocker.page_url ? ` (${blocker.page_url})` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
