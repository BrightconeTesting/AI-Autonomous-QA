"use client";

import { useMemo } from "react";
import type { AppMapModule, AppMapResponse } from "@/lib/types";

type Props = {
  appmap: AppMapResponse | null;
};

type PersonaColumn = {
  id: string;
  label: string;
  authenticated: boolean;
};

type ModuleRow = {
  moduleId: string;
  name: string;
};

function moduleName(moduleId: string, modules: AppMapModule[]): string {
  return modules.find((item) => item.module_id === moduleId)?.name || moduleId;
}

function personaColumns(appmap: AppMapResponse): PersonaColumn[] {
  const auth = appmap.auth_intelligence;
  const matrix = auth?.visibility_matrix ?? {};
  const fromAuth = (auth?.personas ?? []).map((persona) => ({
    id: persona.persona_id,
    label: persona.label || persona.persona_id,
    authenticated: Boolean(persona.authenticated),
  }));
  if (fromAuth.length > 0) return fromAuth;

  return Object.keys(matrix).map((personaId) => ({
    id: personaId,
    label: personaId,
    authenticated: true,
  }));
}

function visibleModules(persona: PersonaColumn, appmap: AppMapResponse): Set<string> {
  const authPersona = appmap.auth_intelligence?.personas?.find((item) => item.persona_id === persona.id);
  const matrixEntry = appmap.auth_intelligence?.visibility_matrix?.[persona.id];
  const ids = authPersona?.visible_module_ids?.length
    ? authPersona.visible_module_ids
    : matrixEntry?.visible_module_ids ?? [];
  return new Set(ids.map(String));
}

function exclusiveModules(persona: PersonaColumn, appmap: AppMapResponse): Set<string> {
  const authPersona = appmap.auth_intelligence?.personas?.find((item) => item.persona_id === persona.id);
  const matrixEntry = appmap.auth_intelligence?.visibility_matrix?.[persona.id];
  const ids = authPersona?.exclusive_module_ids?.length
    ? authPersona.exclusive_module_ids
    : matrixEntry?.exclusive_module_ids ?? [];
  return new Set(ids.map(String));
}

function moduleRows(appmap: AppMapResponse): ModuleRow[] {
  const modules = appmap.modules ?? [];
  if (modules.length > 0) {
    return modules.map((module) => ({
      moduleId: module.module_id,
      name: module.name,
    }));
  }
  const matrix = appmap.auth_intelligence?.visibility_matrix ?? {};
  const ids = new Set<string>();
  for (const entry of Object.values(matrix)) {
    for (const moduleId of entry.visible_module_ids ?? []) ids.add(String(moduleId));
  }
  return [...ids].map((moduleId) => ({ moduleId, name: moduleId }));
}

function cellLabel(visible: boolean, exclusive: boolean): { text: string; className: string } {
  if (exclusive) return { text: "Exclusive", className: "text-green-300" };
  if (visible) return { text: "Visible", className: "text-blue-300" };
  return { text: "Hidden", className: "text-[var(--muted)]" };
}

export function PersonaMergeDiff({ appmap }: Props) {
  const personas = useMemo(() => (appmap ? personaColumns(appmap) : []), [appmap]);
  const rows = useMemo(() => (appmap ? moduleRows(appmap) : []), [appmap]);
  const pagePersonas = appmap?.persona_visibility?.page_personas ?? {};

  if (!appmap || personas.length < 1) {
    return (
      <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
        <h3 className="text-sm font-semibold text-[var(--text)]">Persona visibility diff</h3>
        <p className="mt-2 text-sm text-[var(--muted)]">
          Add multiple personas under Advanced discovery and re-run crawl to compare which modules each
          user role can access.
        </p>
      </section>
    );
  }

  const singlePersona = personas.length === 1;

  return (
    <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="mb-3">
        <h3 className="text-sm font-semibold text-[var(--text)]">Persona visibility diff</h3>
        <p className="mt-1 text-xs text-[var(--muted)]">
          Side-by-side view of which modules each persona could reach during discovery.
          {singlePersona ? " Add another persona to compare roles." : ""}
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-left text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-xs text-[var(--muted)]">
              <th className="py-2 pr-3 font-medium">Module</th>
              {personas.map((persona) => (
                <th key={persona.id} className="py-2 px-3 font-medium">
                  <div className="text-[var(--text)]">{persona.label}</div>
                  <div className="font-normal">{persona.authenticated ? "Signed in" : "Anonymous"}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.moduleId} className="border-b border-[var(--border)]/60">
                <td className="py-2 pr-3 font-medium text-[var(--text)]">{row.name}</td>
                {personas.map((persona) => {
                  const visible = visibleModules(persona, appmap).has(row.moduleId);
                  const exclusive = exclusiveModules(persona, appmap).has(row.moduleId);
                  const cell = cellLabel(visible, exclusive);
                  return (
                    <td key={`${row.moduleId}-${persona.id}`} className={`px-3 py-2 ${cell.className}`}>
                      {cell.text}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {Object.keys(pagePersonas).length > 0 && (
        <details className="mt-4 rounded border border-[var(--border)] p-3">
          <summary className="cursor-pointer text-xs font-medium text-[var(--text)]">
            Page-level persona map ({Object.keys(pagePersonas).length} URLs)
          </summary>
          <ul className="mt-2 max-h-40 space-y-1 overflow-y-auto text-xs text-[var(--muted)]">
            {Object.entries(pagePersonas)
              .slice(0, 20)
              .map(([url, personaIds]) => (
                <li key={url} className="truncate">
                  <span className="text-[var(--text)]">{url}</span> → {(personaIds as string[]).join(", ")}
                </li>
              ))}
          </ul>
        </details>
      )}
    </section>
  );
}
