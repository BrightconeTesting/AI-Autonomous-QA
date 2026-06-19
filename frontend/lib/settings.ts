export type UserSettings = {
  browserNotifications: boolean;
  notificationSound: boolean;
  videoRetentionDays: number;
  autoStartCrawl: boolean;
  autoGenerateAfterCrawl: boolean;
};

export const DEFAULT_SETTINGS: UserSettings = {
  browserNotifications: false,
  notificationSound: false,
  videoRetentionDays: 30,
  autoStartCrawl: false,
  autoGenerateAfterCrawl: false,
};

const STORAGE_KEY = "aqa-dashboard-settings";

export function loadSettings(): UserSettings {
  if (typeof window === "undefined") return DEFAULT_SETTINGS;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function saveSettings(settings: UserSettings): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}
