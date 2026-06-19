import { Suspense } from "react";
import { AppHub } from "@/components/AppHub";

export default function AppDetailPage({ params }: { params: { id: string } }) {
  return (
    <Suspense fallback={<p className="text-[var(--muted)]">Loading app…</p>}>
      <AppHub appId={params.id} />
    </Suspense>
  );
}
