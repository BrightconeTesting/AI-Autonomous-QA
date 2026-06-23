type Props = {
  condition:
    | "auth"
    | "no_pages"
    | "no_appmap"
    | "no_scenarios"
    | "workers"
    | "generate_first"
    | "approval_pending"
    | "approval_rejected"
    | null;
  appId?: string;
  onOpenAppMap?: () => void;
};

const MESSAGES: Record<
  NonNullable<Props["condition"]>,
  { title: string; detail: string; action?: { label: string; href?: string } }
> = {
  auth: {
    title: "Login failed",
    detail: "Check credentials and login selectors for this app.",
    action: { label: "Edit app", href: undefined },
  },
  no_pages: {
    title: "No pages discovered",
    detail: "The crawl finished without finding any pages.",
  },
  no_appmap: {
    title: "AppMap v2 required",
    detail: "Re-crawl with CIC enabled to generate tests.",
  },
  no_scenarios: {
    title: "No scenarios",
    detail: "No flows were found in the AppMap. Try adjusting crawl settings.",
  },
  workers: {
    title: "Workers offline",
    detail: "Celery or Redis may be unavailable. Start workers with pnpm dev:worker:celery.",
  },
  generate_first: {
    title: "Generate tests first",
    detail: "Complete the Generate Tests phase before running scenarios.",
  },
  approval_pending: {
    title: "AppMap needs approval",
    detail: "Review the AppMap and approve it before generating tests.",
  },
  approval_rejected: {
    title: "AppMap was rejected",
    detail: "Fix crawl settings and re-run discovery, or approve after manual review.",
  },
};

export function PhaseErrorPanel({ condition, onOpenAppMap }: Props) {
  if (!condition) return null;
  const msg = MESSAGES[condition];

  return (
    <div
      role="alert"
      className="rounded-lg border border-red-600/50 bg-red-500/10 px-4 py-3 text-sm"
    >
      <p className="font-medium text-red-300">{msg.title}</p>
      <p className="mt-1 text-[var(--muted)]">{msg.detail}</p>
      {condition === "approval_pending" && onOpenAppMap && (
        <button
          type="button"
          onClick={onOpenAppMap}
          className="mt-2 text-sm text-blue-400 underline hover:text-blue-300"
        >
          Open AppMap tab
        </button>
      )}
    </div>
  );
}
