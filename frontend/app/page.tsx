import Link from "next/link";
import { MetricsPanel } from "@/components/MetricsPanel";

export default function HomePage() {
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-semibold">Autonomous QA Dashboard</h1>
      <p className="text-[var(--muted)]">
        Register an application, crawl it, generate Cucumber scenarios, and run selected tests.
      </p>
      <MetricsPanel />
      <div className="flex gap-3">
        <Link
          href="/apps/new"
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500"
        >
          Register app
        </Link>
        <Link
          href="/apps"
          className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm hover:bg-[var(--surface)]"
        >
          View apps
        </Link>
      </div>
    </div>
  );
}
