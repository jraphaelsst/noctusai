import type { ReactNode } from 'react';
import { Skeleton } from '@noctusai/seed/components/ui/skeleton';

interface SummaryValueProps {
  /**
   * True while the underlying query has NEVER resolved for this value —
   * i.e. `query.isPending && !query.data`. NEVER pass `query.isLoading`
   * here: `isLoading` goes false the instant a background refetch starts,
   * which does not help (this component already treats a still-fetching
   * value with existing data as "arrived" — see the header comment below).
   */
  notArrived: boolean;
  children: ReactNode;
  className?: string;
}

/**
 * Summary-card VALUE gate — the third mode of the lying-loading-state bug
 * class (KB § PATTERNS/frontend/lying-loading-state.md).
 *
 * Mode A tells the lie with an empty state ("Sem dados"). Mode B tells it
 * with a skeleton unmounted over real data. This third mode tells it with a
 * ZERO: a `resumo?.total_pago || 0` (or `?? 0`) style fallback renders as a
 * real, legitimate-looking answer the instant a summary card mounts, before
 * its query has ever resolved — worse than either other mode, because a
 * zero reads as data, not as a state.
 *
 * `notArrived` MUST be computed as `query.isPending && !query.data` at the
 * call site — never `query.isLoading` — so a genuine server-returned zero
 * (`data.field === 0`) still renders as `0` once `data` exists, and a
 * background refetch on top of existing data never re-arms the skeleton.
 *
 * Usage:
 * ```tsx
 * const resumoQuery = useComissaoResumo();
 * const resumoNotArrived = resumoQuery.isPending && !resumoQuery.data;
 * // ...
 * <div className="text-2xl font-bold">
 *   <SummaryValue notArrived={resumoNotArrived}>
 *     {formatCurrency(resumoQuery.data?.totais.total_pago ?? 0)}
 *   </SummaryValue>
 * </div>
 * ```
 */
export function SummaryValue({ notArrived, children, className }: SummaryValueProps) {
  if (notArrived) {
    return <Skeleton className={className ?? 'h-8 w-20'} />;
  }
  return <>{children}</>;
}
