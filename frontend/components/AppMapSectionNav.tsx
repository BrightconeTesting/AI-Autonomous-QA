"use client";

export type AppMapSection = "structure" | "insights";

type Props = {
  section: AppMapSection;
  onChange: (section: AppMapSection) => void;
};

const SECTIONS: { id: AppMapSection; label: string }[] = [
  { id: "structure", label: "Structure" },
  { id: "insights", label: "Insights" },
];

export function AppMapSectionNav({ section, onChange }: Props) {
  return (
    <div className="flex gap-1 border-b border-[var(--border)]">
      {SECTIONS.map((s) => (
        <button
          key={s.id}
          type="button"
          onClick={() => onChange(s.id)}
          className={`px-3 py-1.5 text-sm ${
            section === s.id
              ? "border-b-2 border-blue-500 text-[var(--text)]"
              : "text-[var(--muted)] hover:text-[var(--text)]"
          }`}
        >
          {s.label}
        </button>
      ))}
    </div>
  );
}
