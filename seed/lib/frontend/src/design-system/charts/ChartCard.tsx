/**
 * ChartCard — titled/subtitled card frame with the loading / empty / error
 * / success state-machine baked in. Formalizes the triad that was
 * copy-pasted verbatim across `VisaoGeralPanel.tsx` (social-wiring),
 * `AreaChartCard`/`BarChartCard`/etc. (personal-finance), and
 * `ui/chart.tsx` consumers (erp-imobiliario) — see leads-module-PROJECT.md §8.
 *
 * Slot-based: any chart body (LineChart, AreaChart, BarChart, DonutChart,
 * Heatmap, or something else entirely) is passed as `children` and only
 * renders in the success state.
 */
import type { ReactNode } from "react";
import { cn } from "../../utils";

export interface ChartCardProps {
  title: string;
  subtitle?: string;
  loading?: boolean;
  /** Presence (any truthy string) triggers the error state. */
  error?: string | null;
  /** Explicit empty flag — the caller knows its own "no data" condition best. */
  isEmpty?: boolean;
  emptyMessage?: string;
  /** Header-right slot — a subtab toggle, a "ver detalhes" link, etc. */
  actions?: ReactNode;
  /** Body min-height applied to every state so the card doesn't reflow between them. */
  minBodyHeight?: number;
  children: ReactNode;
  className?: string;
}

const DEFAULT_EMPTY_MESSAGE = "Sem dados para o período selecionado.";

export function ChartCard({
  title,
  subtitle,
  loading = false,
  error = null,
  isEmpty = false,
  emptyMessage = DEFAULT_EMPTY_MESSAGE,
  actions,
  minBodyHeight = 280,
  children,
  className,
}: ChartCardProps) {
  return (
    <div className={cn("rounded-lg border border-border bg-card p-4", className)}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold text-card-foreground">{title}</h3>
          {subtitle && <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>}
        </div>
        {actions && <div className="shrink-0">{actions}</div>}
      </div>

      <div style={{ minHeight: minBodyHeight }} className="flex flex-col">
        {loading ? (
          <div
            role="status"
            aria-label="Carregando"
            className="flex-1 animate-pulse rounded-md bg-muted"
            style={{ minHeight: minBodyHeight }}
          />
        ) : error ? (
          <div
            role="alert"
            className="flex flex-1 items-center justify-center rounded-md border border-dashed border-border px-4 text-center text-sm text-destructive"
            style={{ minHeight: minBodyHeight }}
          >
            {error}
          </div>
        ) : isEmpty ? (
          <div
            className="flex flex-1 items-center justify-center rounded-md border border-dashed border-border px-4 text-center text-sm text-muted-foreground"
            style={{ minHeight: minBodyHeight }}
          >
            {emptyMessage}
          </div>
        ) : (
          children
        )}
      </div>
    </div>
  );
}
