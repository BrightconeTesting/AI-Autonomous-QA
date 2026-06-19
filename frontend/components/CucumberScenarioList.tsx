"use client";

import { useEffect, useRef, useState } from "react";
import { apiClient } from "@/lib/api";
import type { ExecutionHighlight, GherkinStep, TestCaseSummary } from "@/lib/types";

type Props = {
  cases: TestCaseSummary[];
  selected: Set<string>;
  onSelectionChange: (next: Set<string>) => void;
  highlight: ExecutionHighlight;
};

function stepClass(
  testcaseId: string,
  stepIndex: number,
  highlight: ExecutionHighlight
): string {
  const outcomes = highlight.stepOutcomes[testcaseId];
  const outcome = outcomes?.[stepIndex];
  const isActive =
    highlight.activeTestcaseId === testcaseId && highlight.activeStepIndex === stepIndex;

  if (isActive) return "bg-yellow-500/20 border-l-2 border-yellow-500";
  if (outcome?.outcome === "passed") return "bg-green-500/10 text-green-300";
  if (outcome?.outcome === "failed") return "bg-red-500/10 text-red-300";
  return "";
}

function ScenarioRow({
  tc,
  selected,
  onToggle,
  highlight,
}: {
  tc: TestCaseSummary;
  selected: boolean;
  onToggle: (checked: boolean) => void;
  highlight: ExecutionHighlight;
}) {
  const [expanded, setExpanded] = useState(false);
  const [steps, setSteps] = useState<GherkinStep[] | null>(null);
  const rowRef = useRef<HTMLLIElement>(null);
  const isDestructive = tc.tags.some((t) => t.includes("destructive"));
  const isActive = highlight.activeTestcaseId === tc.testcase_id;
  const scenarioOutcome = highlight.scenarioOutcomes[tc.testcase_id];

  useEffect(() => {
    if (isActive && rowRef.current) {
      rowRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [isActive]);

  useEffect(() => {
    if (!expanded || steps) return;
    apiClient.getTestCase(tc.testcase_id).then((detail) => {
      setSteps(detail.steps?.gherkin?.steps ?? []);
    });
  }, [expanded, steps, tc.testcase_id]);

  let border = "border-[var(--border)]";
  if (isActive) border = "border-yellow-500 animate-pulse";
  else if (scenarioOutcome?.outcome === "passed") border = "border-green-600";
  else if (scenarioOutcome?.outcome === "failed") border = "border-red-600";

  return (
    <li
      ref={rowRef}
      className={`rounded border ${border} bg-[var(--surface)]`}
    >
      <div className="flex items-start gap-2 p-3">
        <input
          type="checkbox"
          checked={selected}
          onChange={(e) => onToggle(e.target.checked)}
          className="mt-1"
        />
        <div className="min-w-0 flex-1">
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="w-full text-left"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{tc.name}</span>
              {isDestructive && (
                <span className="rounded bg-orange-500/20 px-1.5 py-0.5 text-xs text-orange-400">
                  Destructive
                </span>
              )}
              {scenarioOutcome && (
                <span
                  className={`text-xs ${scenarioOutcome.outcome === "passed" ? "text-green-400" : "text-red-400"}`}
                >
                  {scenarioOutcome.outcome === "passed" ? "✓" : "✗"}
                </span>
              )}
            </div>
            <div className="mt-1 text-xs text-[var(--muted)]">
              {tc.tags.join(" ")} · {tc.step_count} steps · {tc.priority}
            </div>
          </button>
          {expanded && (
            <ol className="mt-3 space-y-1 border-t border-[var(--border)] pt-2 text-sm">
              {(steps ?? []).map((step, i) => {
                const outcome = highlight.stepOutcomes[tc.testcase_id]?.[i];
                return (
                  <li
                    key={i}
                    className={`rounded px-2 py-1 ${stepClass(tc.testcase_id, i, highlight)}`}
                  >
                    <span className="font-semibold text-[var(--muted)]">{step.keyword}</span>{" "}
                    {step.text}
                    {outcome?.duration_ms != null && (
                      <span className="ml-2 text-xs text-[var(--muted)]">
                        {outcome.duration_ms}ms
                      </span>
                    )}
                    {outcome?.error && (
                      <p className="mt-1 text-xs text-red-400">{outcome.error}</p>
                    )}
                  </li>
                );
              })}
              {!steps && (
                <li className="text-xs text-[var(--muted)]">Loading steps…</li>
              )}
            </ol>
          )}
        </div>
      </div>
    </li>
  );
}

export function CucumberScenarioList({ cases, selected, onSelectionChange, highlight }: Props) {
  const grouped = new Map<string, TestCaseSummary[]>();
  for (const tc of cases) {
    const feature = tc.feature || "Scenarios";
    if (!grouped.has(feature)) grouped.set(feature, []);
    grouped.get(feature)!.push(tc);
  }

  if (cases.length === 0) {
    return (
      <p className="text-sm text-[var(--muted)]">
        No scenarios yet. Complete crawl and generate tests first.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {[...grouped.entries()].map(([feature, items]) => (
        <section key={feature}>
          <h3 className="mb-2 font-mono text-sm text-[var(--muted)]">Feature: {feature}</h3>
          <ul className="space-y-2">
            {items.map((tc) => (
              <ScenarioRow
                key={tc.testcase_id}
                tc={tc}
                selected={selected.has(tc.testcase_id)}
                onToggle={(checked) => {
                  const next = new Set(selected);
                  if (checked) next.add(tc.testcase_id);
                  else next.delete(tc.testcase_id);
                  onSelectionChange(next);
                }}
                highlight={highlight}
              />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
