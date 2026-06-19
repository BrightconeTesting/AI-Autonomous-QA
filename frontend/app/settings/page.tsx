"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { requestNotificationPermission } from "@/lib/notifications";
import { DEFAULT_SETTINGS, loadSettings, saveSettings, type UserSettings } from "@/lib/settings";

export default function SettingsPage() {
  const [settings, setSettings] = useState<UserSettings>(DEFAULT_SETTINGS);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setSettings(loadSettings());
  }, []);

  function update<K extends keyof UserSettings>(key: K, value: UserSettings[K]) {
    setSettings((s) => ({ ...s, [key]: value }));
    setSaved(false);
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    saveSettings(settings);
    if (settings.browserNotifications) {
      await requestNotificationPermission();
    }
    setSaved(true);
  }

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <Link href="/" className="text-sm text-[var(--muted)] hover:underline">
        ← Dashboard
      </Link>
      <h1 className="text-2xl font-semibold">Settings</h1>
      <p className="text-sm text-[var(--muted)]">
        Preferences are stored in your browser. Video retention cleanup runs on the server when
        configured (Phase 4 backend job).
      </p>

      <form onSubmit={handleSave} className="space-y-6">
        <fieldset className="space-y-3 rounded-lg border border-[var(--border)] p-4">
          <legend className="px-1 text-sm font-medium">Notifications</legend>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={settings.browserNotifications}
              onChange={(e) => update("browserNotifications", e.target.checked)}
            />
            Browser notifications on phase complete
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={settings.notificationSound}
              onChange={(e) => update("notificationSound", e.target.checked)}
            />
            Notification sound (future)
          </label>
        </fieldset>

        <fieldset className="space-y-3 rounded-lg border border-[var(--border)] p-4">
          <legend className="px-1 text-sm font-medium">Pipeline automation</legend>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={settings.autoStartCrawl}
              onChange={(e) => update("autoStartCrawl", e.target.checked)}
            />
            Auto-start crawl after registering a new app
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={settings.autoGenerateAfterCrawl}
              onChange={(e) => update("autoGenerateAfterCrawl", e.target.checked)}
            />
            Auto-generate tests when crawl completes
          </label>
        </fieldset>

        <fieldset className="space-y-3 rounded-lg border border-[var(--border)] p-4">
          <legend className="px-1 text-sm font-medium">Artifact retention</legend>
          <label className="block text-sm">
            Video retention (days, 0 = never delete)
            <input
              type="number"
              min={0}
              max={365}
              value={settings.videoRetentionDays}
              onChange={(e) => update("videoRetentionDays", Number(e.target.value))}
              className="mt-1 w-full rounded border border-[var(--border)] bg-[var(--surface)] px-3 py-2"
            />
          </label>
        </fieldset>

        <button
          type="submit"
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500"
        >
          Save settings
        </button>
        {saved && <p className="text-sm text-green-400">Settings saved.</p>}
      </form>
    </div>
  );
}
