import { Skeleton } from "@/components/ui/skeleton";

/**
 * Skeleton loader for the dashboard page.
 * Mimics the layout of the actual dashboard with KPI cards and charts.
 */
export function DashboardSkeleton() {
  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Page title */}
      <Skeleton className="h-8 w-48" />

      {/* KPI Cards */}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="p-6 rounded-lg border bg-card">
            <div className="flex justify-between items-start">
              <div className="space-y-2">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-8 w-16" />
              </div>
              <Skeleton className="h-10 w-10 rounded-full" />
            </div>
            <Skeleton className="h-3 w-32 mt-4" />
          </div>
        ))}
      </div>

      {/* Charts section */}
      <div className="grid gap-6 grid-cols-1 lg:grid-cols-2">
        {/* Main chart */}
        <div className="p-6 rounded-lg border bg-card">
          <Skeleton className="h-6 w-40 mb-4" />
          <Skeleton className="h-64 w-full" />
        </div>

        {/* Secondary chart */}
        <div className="p-6 rounded-lg border bg-card">
          <Skeleton className="h-6 w-40 mb-4" />
          <Skeleton className="h-64 w-full" />
        </div>
      </div>

      {/* Recent activity table */}
      <div className="p-6 rounded-lg border bg-card">
        <Skeleton className="h-6 w-48 mb-4" />
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex items-center gap-4">
              <Skeleton className="h-10 w-10 rounded-full" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-3 w-1/2" />
              </div>
              <Skeleton className="h-4 w-16" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * Skeleton for a simple card grid (used in listing pages).
 */
export function CardGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="p-6 rounded-lg border bg-card space-y-4">
          <div className="flex justify-between">
            <Skeleton className="h-6 w-32" />
            <Skeleton className="h-6 w-16 rounded-full" />
          </div>
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
          </div>
          <div className="flex gap-2 pt-2">
            <Skeleton className="h-8 w-20" />
            <Skeleton className="h-8 w-20" />
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * Skeleton for a form page.
 */
export function FormSkeleton() {
  return (
    <div className="max-w-2xl mx-auto p-6 space-y-6">
      <Skeleton className="h-8 w-48" /> {/* Title */}
      <div className="space-y-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="space-y-2">
            <Skeleton className="h-4 w-24" /> {/* Label */}
            <Skeleton className="h-10 w-full" /> {/* Input */}
          </div>
        ))}
      </div>
      <div className="flex gap-2 pt-4">
        <Skeleton className="h-10 w-24" />
        <Skeleton className="h-10 w-24" />
      </div>
    </div>
  );
}
