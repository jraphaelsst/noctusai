/**
 * TableSkeleton re-exported from the shared design system — canonical organ.
 * (No local consumer at time of migration; kept for backward compatibility.)
 */
export { TableSkeleton } from "@noctusai/lib/design-system";

function Bar({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse bg-muted rounded ${className}`} />;
}

export function KPICardSkeleton() {
  return (
    <div className="rounded-lg border bg-card p-4 space-y-2">
      <div className="flex items-center justify-between">
        <Bar className="h-4 w-24" />
        <Bar className="h-4 w-4" />
      </div>
      <Bar className="h-8 w-32" />
      <Bar className="h-3 w-16" />
    </div>
  );
}

export function CardSkeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="rounded-lg border bg-card p-4 space-y-3">
      <Bar className="h-5 w-32" />
      {Array.from({ length: lines }).map((_, i) => (
        <Bar key={i} className="h-4 w-full" />
      ))}
    </div>
  );
}

export function ListSkeleton({ items = 3 }: { items?: number }) {
  return (
    <div className="rounded-lg border bg-card p-4 space-y-3">
      <Bar className="h-5 w-32" />
      {Array.from({ length: items }).map((_, i) => (
        <div key={i} className="flex items-center justify-between py-2 border-b last:border-b-0">
          <div className="flex items-center gap-3">
            <Bar className="h-8 w-8 rounded-full" />
            <div className="space-y-1">
              <Bar className="h-4 w-28" />
              <Bar className="h-3 w-20" />
            </div>
          </div>
          <Bar className="h-4 w-16" />
        </div>
      ))}
    </div>
  );
}

export function ChartSkeleton() {
  return (
    <div className="rounded-lg border bg-card p-4 space-y-3">
      <Bar className="h-5 w-32" />
      <Bar className="h-48 w-full rounded-lg" />
    </div>
  );
}
