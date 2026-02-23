import { Skeleton } from "@/components/ui/skeleton";

interface TableSkeletonProps {
  rows?: number;
  columns?: number;
}

/**
 * Skeleton loader for table views.
 *
 * @param rows - Number of rows to display (default: 5)
 * @param columns - Number of columns to display (default: 4)
 */
export function TableSkeleton({ rows = 5, columns = 4 }: TableSkeletonProps) {
  return (
    <div className="w-full space-y-3">
      {/* Header */}
      <div className="flex gap-4 p-4 bg-muted/50 rounded-t-lg">
        {Array.from({ length: columns }).map((_, i) => (
          <Skeleton key={`header-${i}`} className="h-4 flex-1" />
        ))}
      </div>

      {/* Rows */}
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div
          key={`row-${rowIndex}`}
          className="flex gap-4 p-4 border-b border-muted"
        >
          {Array.from({ length: columns }).map((_, colIndex) => (
            <Skeleton
              key={`cell-${rowIndex}-${colIndex}`}
              className="h-4 flex-1"
              style={{
                width: `${Math.random() * 40 + 60}%`,
              }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

/**
 * Skeleton for a table with header and action buttons.
 */
export function TableWithActionsKeleton() {
  return (
    <div className="space-y-4">
      {/* Actions bar */}
      <div className="flex justify-between items-center">
        <Skeleton className="h-10 w-64" /> {/* Search */}
        <div className="flex gap-2">
          <Skeleton className="h-10 w-24" /> {/* Filter */}
          <Skeleton className="h-10 w-32" /> {/* Add button */}
        </div>
      </div>

      {/* Table */}
      <TableSkeleton />

      {/* Pagination */}
      <div className="flex justify-between items-center pt-4">
        <Skeleton className="h-4 w-32" /> {/* Count */}
        <div className="flex gap-2">
          <Skeleton className="h-8 w-8" />
          <Skeleton className="h-8 w-8" />
          <Skeleton className="h-8 w-8" />
        </div>
      </div>
    </div>
  );
}
