"use client";

import { useState } from "react";
import {
  LLM_BUDGET_DEFAULTS,
  type DiscoverPersona,
  type DiscoverSettings,
} from "@/lib/discoverConfig";
import { loadSettings, saveSettings } from "@/lib/settings";

type Props = {
  settings: DiscoverSettings;
  onChange: (settings: DiscoverSettings) => void;
  disabled?: boolean;
  onSkipApprovalChange?: (skip: boolean) => void;
};

export function DiscoverAdvancedFields({
  settings,
  onChange,
  disabled = false,
  onSkipApprovalChange,
}: Props) {
  const [open, setOpen] = useState(false);
  const [skipApproval, setSkipApproval] = useState(() => loadSettings().skipAppmapApproval);

  function updateBudget(key: keyof DiscoverSettings["llmBudgets"], raw: string) {
    const n = Number(raw);
    if (!Number.isFinite(n) || n < 0) return;
    onChange({
      ...settings,
      llmBudgets: { ...settings.llmBudgets, [key]: Math.round(n) },
    });
  }

  function updatePersona(index: number, patch: Partial<DiscoverPersona>) {
    const personas = settings.personas.map((p, i) => (i === index ? { ...p, ...patch } : p));
    onChange({ ...settings, personas });
  }

  function addPersona() {
    onChange({
      ...settings,
      personas: [...settings.personas, { personaId: "", label: "" }],
    });
  }

  function removePersona(index: number) {
    onChange({
      ...settings,
      personas: settings.personas.filter((_, i) => i !== index),
    });
  }

  function toggleSkipApproval(checked: boolean) {
    setSkipApproval(checked);
    saveSettings({ ...loadSettings(), skipAppmapApproval: checked });
    onSkipApprovalChange?.(checked);
  }

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)]">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium disabled:opacity-50"
      >
        Advanced discovery
        <span className="text-[var(--muted)]">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="space-y-4 border-t border-[var(--border)] px-4 py-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={settings.useLlm}
              disabled={disabled}
              onChange={(e) => onChange({ ...settings, useLlm: e.target.checked })}
            />
            Use LLM for flow structuring
          </label>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={settings.captureNetwork}
                disabled={disabled}
                onChange={(e) => onChange({ ...settings, captureNetwork: e.target.checked })}
              />
              Capture network APIs
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={settings.captureHar}
                disabled={disabled || !settings.captureNetwork}
                onChange={(e) => onChange({ ...settings, captureHar: e.target.checked })}
              />
              Save sanitized HAR
            </label>
          </div>

          <label className="block text-sm">
            <span className="mb-1 block text-[var(--muted)]">OpenAPI URL (optional)</span>
            <input
              type="url"
              value={settings.openapiUrl}
              disabled={disabled}
              placeholder="https://example.com/openapi.json"
              onChange={(e) => onChange({ ...settings, openapiUrl: e.target.value })}
              className="w-full rounded border border-[var(--border)] bg-[var(--bg)] px-2 py-1.5 text-sm"
            />
          </label>

          <div className="grid gap-3 sm:grid-cols-2">
            <BudgetField
              label="Flow structure budget"
              value={settings.llmBudgets.flowStructure}
              defaultValue={LLM_BUDGET_DEFAULTS.flowStructure}
              disabled={disabled}
              onChange={(v) => updateBudget("flowStructure", v)}
            />
            <BudgetField
              label="Module structure budget"
              value={settings.llmBudgets.moduleStructure}
              defaultValue={LLM_BUDGET_DEFAULTS.moduleStructure}
              disabled={disabled}
              onChange={(v) => updateBudget("moduleStructure", v)}
            />
            <BudgetField
              label="Entities budget"
              value={settings.llmBudgets.entities}
              defaultValue={LLM_BUDGET_DEFAULTS.entities}
              disabled={disabled}
              onChange={(v) => updateBudget("entities", v)}
            />
            <BudgetField
              label="Test areas budget"
              value={settings.llmBudgets.testAreas}
              defaultValue={LLM_BUDGET_DEFAULTS.testAreas}
              disabled={disabled}
              onChange={(v) => updateBudget("testAreas", v)}
            />
            <BudgetField
              label="Total token cap"
              value={settings.llmBudgets.totalCap}
              defaultValue={LLM_BUDGET_DEFAULTS.totalCap}
              disabled={disabled}
              onChange={(v) => updateBudget("totalCap", v)}
            />
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <p className="text-sm font-medium">Discovery personas</p>
              <button
                type="button"
                disabled={disabled}
                onClick={addPersona}
                className="text-xs text-blue-400 hover:underline disabled:opacity-50"
              >
                + Add persona
              </button>
            </div>
            {settings.personas.length === 0 ? (
              <p className="text-xs text-[var(--muted)]">
                Optional. Credentials reference AUTH_*_JSON env vars on the worker — not entered
                here.
              </p>
            ) : (
              <div className="space-y-2">
                {settings.personas.map((persona, index) => (
                  <div key={index} className="flex flex-wrap gap-2">
                    <input
                      type="text"
                      placeholder="persona_id"
                      value={persona.personaId}
                      disabled={disabled}
                      onChange={(e) => updatePersona(index, { personaId: e.target.value })}
                      className="min-w-[120px] flex-1 rounded border border-[var(--border)] bg-[var(--bg)] px-2 py-1 text-sm"
                    />
                    <input
                      type="text"
                      placeholder="Label"
                      value={persona.label}
                      disabled={disabled}
                      onChange={(e) => updatePersona(index, { label: e.target.value })}
                      className="min-w-[120px] flex-1 rounded border border-[var(--border)] bg-[var(--bg)] px-2 py-1 text-sm"
                    />
                    <button
                      type="button"
                      disabled={disabled}
                      onClick={() => removePersona(index)}
                      className="text-xs text-red-400 hover:underline disabled:opacity-50"
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <label className="flex items-start gap-2 border-t border-[var(--border)] pt-3 text-sm">
            <input
              type="checkbox"
              checked={skipApproval}
              disabled={disabled}
              onChange={(e) => toggleSkipApproval(e.target.checked)}
              className="mt-0.5"
            />
            <span>
              Skip AppMap approval for generate-tests
              <span className="mt-0.5 block text-xs text-[var(--muted)]">
                Dev/CI only — sends requireAppmapApproval=false when generating tests.
              </span>
            </span>
          </label>
        </div>
      )}
    </div>
  );
}

function BudgetField({
  label,
  value,
  defaultValue,
  disabled,
  onChange,
}: {
  label: string;
  value: number;
  defaultValue: number;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs text-[var(--muted)]">{label}</label>
      <input
        type="number"
        min={0}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded border border-[var(--border)] bg-[var(--bg)] px-2 py-1 text-sm disabled:opacity-50"
      />
      <p className="mt-0.5 text-xs text-[var(--muted)]">Default: {defaultValue}</p>
    </div>
  );
}
