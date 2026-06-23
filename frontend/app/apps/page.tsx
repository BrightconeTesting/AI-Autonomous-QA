import Link from "next/link";
import { AppList } from "@/components/AppList";
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
      {!apps && (
        <p className="text-[var(--muted)]">
          Could not load apps — is the API running on port 3001?
        </p>
      )}
      {apps && <AppList initialApps={apps.items} />}
    </div>
  );
}
