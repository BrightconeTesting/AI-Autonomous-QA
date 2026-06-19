import Link from "next/link";
import type { TestRunSummary } from "@/lib/types";

type Props = {
  runs: TestRunSummary[];
  appId: string;
};

export function RunResultsTable({ runs, appId }: Props) {
  if (runs.length === 0) {
    return (
      <p className="text-sm text-[var(--muted)]">No test runs yet for this application.</p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
      <table className="w-full text-sm">
        <thead className="border-b border-[var(--border)] bg-[var(--surface)] text-left text-[var(--muted)]">
          <tr>
            <th className="px-4 py-2 font-medium">Run</th>
            <th className="px-4 py-2 font-medium">Status</th>
            <th className="px-4 py-2 font-medium">Passed</th>
            <th className="px-4 py-2 font-medium">Failed</th>
            <th className="px-4 py-2 font-medium">Started</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--border)]">
          {runs.map((run) => (
            <tr key={run.run_id} className="hover:bg-[var(--surface)]">
              <td className="px-4 py-2">
                <Link
                  href={`/runs/${run.run_id}`}
                  className="font-mono text-xs text-blue-400 hover:underline"
                >
                  {run.run_id.slice(0, 8)}…
                </Link>
              </td>
              <td className="px-4 py-2 capitalize">{run.status}</td>
              <td className="px-4 py-2 text-green-400">{run.summary.passed}</td>
              <td className="px-4 py-2 text-red-400">{run.summary.failed}</td>
              <td className="px-4 py-2 text-[var(--muted)]">
                {run.started_at ? new Date(run.started_at).toLocaleString() : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
