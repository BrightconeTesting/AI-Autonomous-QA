import type { ScenarioFilters as Filters } from "@/lib/types";

type Props = {
  filters: Filters;
  onChange: (next: Filters) => void;
  features: string[];
  allTags: string[];
};

const PRIORITIES = ["critical", "high", "medium", "low"];

export function ScenarioFilters({ filters, onChange, features, allTags }: Props) {
  const togglePriority = (p: string) => {
    const set = new Set(filters.priorities);
    if (set.has(p)) set.delete(p);
    else set.add(p);
    onChange({ ...filters, priorities: [...set] });
  };

  const toggleTag = (t: string) => {
    const set = new Set(filters.tags);
    if (set.has(t)) set.delete(t);
    else set.add(t);
    onChange({ ...filters, tags: [...set] });
  };

  return (
    <div className="space-y-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
      <input
        type="search"
        placeholder="Search scenarios or steps…"
        value={filters.search}
        onChange={(e) => onChange({ ...filters, search: e.target.value })}
        className="w-full rounded border border-[var(--border)] bg-[var(--bg)] px-3 py-2 text-sm"
      />
      <div className="flex flex-wrap gap-2">
        <span className="text-xs text-[var(--muted)]">Priority:</span>
        {PRIORITIES.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => togglePriority(p)}
            className={`rounded-full px-2 py-0.5 text-xs capitalize ${
              filters.priorities.includes(p)
                ? "bg-blue-600 text-white"
                : "border border-[var(--border)] text-[var(--muted)]"
            }`}
          >
            {p}
          </button>
        ))}
      </div>
      {allTags.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <span className="text-xs text-[var(--muted)]">Tags:</span>
          {allTags.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => toggleTag(t)}
              className={`rounded-full px-2 py-0.5 text-xs ${
                filters.tags.includes(t)
                  ? "bg-blue-600 text-white"
                  : "border border-[var(--border)] text-[var(--muted)]"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      )}
      {features.length > 1 && (
        <select
          value={filters.feature ?? ""}
          onChange={(e) =>
            onChange({ ...filters, feature: e.target.value || null })
          }
          className="rounded border border-[var(--border)] bg-[var(--bg)] px-2 py-1 text-sm"
        >
          <option value="">All features</option>
          {features.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}

export function applyScenarioFilters<T extends { name: string; priority: string; feature: string | null; tags: string[] }>(
  items: T[],
  filters: Filters
): T[] {
  return items.filter((tc) => {
    if (filters.feature && tc.feature !== filters.feature) return false;
    if (filters.priorities.length && !filters.priorities.includes(tc.priority)) return false;
    if (filters.tags.length && !filters.tags.some((t) => tc.tags.includes(t))) return false;
    if (filters.search) {
      const q = filters.search.toLowerCase();
      const hay = `${tc.name} ${tc.feature ?? ""} ${tc.tags.join(" ")}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}
