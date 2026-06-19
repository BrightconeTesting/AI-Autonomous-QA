import Link from "next/link";
import { apiClient } from "@/lib/api";

export default async function AppsPage() {
  let apps: Awaited<ReturnType<typeof apiClient.listApps>> | null = null;
  try {
    apps = await apiClient.listApps();
  } catch {
    apps = null;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Applications</h1>
        <Link href="/apps/new" className="rounded-lg bg-blue-600 px-3 py-2 text-sm text-white">
          New app
        </Link>
      </div>
      {!apps && <p className="text-[var(--muted)]">Could not load apps — is the API running on port 3001?</p>}
      <ul className="divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
        {(apps?.items || []).map((app) => (
          <li key={app.app_id}>
            <Link href={`/apps/${app.app_id}`} className="block px-4 py-3 hover:bg-[var(--surface)]">
              <div className="font-medium">{app.name}</div>
              <div className="text-sm text-[var(--muted)]">{app.base_url}</div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
