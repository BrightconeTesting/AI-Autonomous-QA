export function notifyPhaseComplete(
  phase: "crawl" | "generate" | "execute",
  detail?: string
) {
  if (typeof window === "undefined" || !("Notification" in window)) return;
  if (Notification.permission !== "granted") return;

  const titles = {
    crawl: "Crawl complete",
    generate: "Tests generated",
    execute: "Execution finished",
  };

  new Notification(titles[phase], { body: detail, tag: `aqa-${phase}` });
}

export async function requestNotificationPermission(): Promise<boolean> {
  if (typeof window === "undefined" || !("Notification" in window)) return false;
  if (Notification.permission === "granted") return true;
  if (Notification.permission === "denied") return false;
  const result = await Notification.requestPermission();
  return result === "granted";
}

export function showToast(message: string) {
  if (typeof document === "undefined") return;
  const el = document.createElement("div");
  el.className =
    "fixed bottom-4 right-4 z-50 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm shadow-lg";
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}
