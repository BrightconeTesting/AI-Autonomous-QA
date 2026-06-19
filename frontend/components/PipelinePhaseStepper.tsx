import type { PhaseState } from "@/lib/types";

const styles: Record<PhaseState, string> = {
  pending: "border-[var(--border)] bg-[var(--surface)] text-[var(--muted)]",
  running: "border-yellow-500 bg-yellow-500/10 text-yellow-400 animate-pulse",
  done: "border-green-600 bg-green-500/10 text-green-400",
  failed: "border-red-600 bg-red-500/10 text-red-400",
  cancelled: "border-orange-500 bg-orange-500/10 text-orange-400",
};

const icons: Record<PhaseState, string> = {
  pending: "○",
  running: "●",
  done: "✓",
  failed: "✗",
  cancelled: "⊘",
};

type Props = {
  crawl: PhaseState;
  generate: PhaseState;
  execute: PhaseState;
};

export function PipelinePhaseStepper({ crawl, generate, execute }: Props) {
  const phases = [
    { label: "1. Crawl", state: crawl },
    { label: "2. Generate Tests", state: generate },
    { label: "3. Execute", state: execute },
  ];

  return (
    <ol className="flex flex-wrap gap-3" aria-label="Pipeline phases">
      {phases.map((phase) => (
        <li
          key={phase.label}
          className={`rounded-lg border px-4 py-2 text-sm font-medium ${styles[phase.state]}`}
        >
          <span className="mr-2 opacity-70">{icons[phase.state]}</span>
          {phase.label}
        </li>
      ))}
    </ol>
  );
}

export type { PhaseState };
