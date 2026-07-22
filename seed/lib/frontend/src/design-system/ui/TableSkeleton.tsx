/**
 * TableSkeleton — canonical loading placeholder for tabular data.
 *
 * Direct replacement for the hand-rolled `{isLoading && <div>Carregando...</div>}`
 * shape found across the Leads subtabs (`Corretores.tsx`, `Empreendimentos.tsx`,
 * `Origens.tsx`, `Importacao.tsx` — see leads-module-PROJECT.md). Renders a
 * header row + N body rows of pulsing cells, shaped like the real table so
 * there's no layout jump when data replaces it.
 *
 * Only ONE cell announces `role="status"` (accessibility — see `Skeleton`);
 * every other cell is `aria-hidden`, decorative.
 */
import { Skeleton } from "./Skeleton";
import { cn } from "../../utils";

export interface TableSkeletonProps {
  /** Number of placeholder body rows. Default 5. */
  rows?: number;
  /** Number of columns (header cells + per-row cells). Default 4. */
  columns?: number;
  /** Render the pulsing header row too. Default true. */
  showHeader?: boolean;
  className?: string;
}

export function TableSkeleton({ rows = 5, columns = 4, showHeader = true, className }: TableSkeletonProps) {
  const rowIndexes = Array.from({ length: rows }, (_, i) => i);
  const columnIndexes = Array.from({ length: columns }, (_, i) => i);

  return (
    <div className={cn("w-full overflow-x-auto", className)}>
      <table className="w-full text-sm">
        {showHeader && (
          <thead>
            <tr className="border-b bg-muted/50">
              {columnIndexes.map((c) => (
                <th key={c} className="px-4 py-2">
                  <Skeleton height={12} className="w-16" announce={false} />
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {rowIndexes.map((r) => (
            <tr key={r} className="border-b last:border-0">
              {columnIndexes.map((c) => (
                <td key={c} className="px-4 py-3">
                  {/* Exactly one cell in the whole placeholder announces to assistive tech. */}
                  <Skeleton height={16} className="w-full" announce={r === 0 && c === 0} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
