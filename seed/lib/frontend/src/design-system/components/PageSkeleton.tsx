import { cn } from "../../utils";

/** Lightweight skeleton block — animate-pulse placeholder matching shadcn/ui Skeleton. */
function Skel({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} />;
}

/**
 * Full-page loading skeleton used as Suspense fallback and auth-init placeholder.
 *
 * Renders a dashboard-shaped placeholder: title bar + 4-card grid + content area.
 * Self-contained — does not depend on any product-local UI components.
 */
export function PageSkeleton() {
  return (
    <div className="container mx-auto p-6 space-y-4">
      <Skel className="h-12 w-64" />
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        <Skel className="h-32" />
        <Skel className="h-32" />
        <Skel className="h-32" />
        <Skel className="h-32" />
      </div>
      <Skel className="h-96" />
    </div>
  );
}
