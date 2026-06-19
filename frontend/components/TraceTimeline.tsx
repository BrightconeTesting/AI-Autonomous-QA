"use client";

import type { StepResult } from "@/lib/types";

type Props = {
  steps: StepResult[];
  activeIndex: number | null;
  onSeek?: (stepIndex: number) => void;
};

export function TraceTimeline({ steps, activeIndex, onSeek }: Props) {
  if (steps.length === 0) return null;

  return (
    <div className="space-y-1">
      <p className="text-xs text-[var(--muted)]">Step timeline</p>
      <div className="flex flex-wrap gap-1">
        {steps.map((step) => {
          const isActive = activeIndex === step.index;
          const color =
            step.outcome === "passed"
              ? "bg-green-600"
              : step.outcome === "failed"
                ? "bg-red-600"
                : "bg-[var(--border)]";
          return (
            <button
              key={step.index}
              type="button"
              title={`${step.keyword ?? ""} ${step.text ?? ""}`}
              onClick={() => onSeek?.(step.index)}
              className={`h-6 min-w-[1.5rem] rounded px-1 text-xs text-white ${color} ${
                isActive ? "ring-2 ring-yellow-400" : ""
              }`}
            >
              {step.index + 1}
            </button>
          );
        })}
      </div>
    </div>
  );
}
