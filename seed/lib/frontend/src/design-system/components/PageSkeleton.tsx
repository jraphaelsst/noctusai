import { Skeleton } from "../ui/Skeleton";

/**
 * Full-page loading skeleton used as Suspense fallback and auth-init placeholder.
 *
 * Renders a dashboard-shaped placeholder: title bar + 4-card grid + content area.
 * Self-contained — does not depend on any product-local UI components.
 *
 * Composed from the canonical `Skeleton` primitive (formalized in the
 * seed-skeleton-organs slice — this was the definition site of the internal
 * `Skel` helper this replaces). Only the title bar announces `role="status"`;
 * the remaining blocks are decorative repeats of the SAME loading region, so
 * assistive tech hears exactly one "Carregando" for the whole page.
 */
export function PageSkeleton() {
  return (
    <div className="container mx-auto p-6 space-y-4">
      <Skeleton className="h-12 w-64" />
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        <Skeleton className="h-32" announce={false} />
        <Skeleton className="h-32" announce={false} />
        <Skeleton className="h-32" announce={false} />
        <Skeleton className="h-32" announce={false} />
      </div>
      <Skeleton className="h-96" announce={false} />
    </div>
  );
}
