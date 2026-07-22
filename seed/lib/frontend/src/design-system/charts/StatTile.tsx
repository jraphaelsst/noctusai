/**
 * StatTile — KPI tile. Promotes the shape of social-wiring's `MetricCard.tsx`
 * (icon, label, value, hint, loading) plus what the Leads "KPI row" needs
 * (§6 of leads-module-PROJECT.md): a `delta` vs. the comparison window and a
 * `trend` direction.
 *
 * `delta === null` renders "—", NEVER "0%" — an unresolvable comparison
 * (e.g. no data in the preceding window) is NOT the same fact as "no
 * change," and coercing it to `0%` would silently lie (see the Leads
 * contract's `variacao_pct: number | null`).
 *
 * Trend is conveyed by ICON + TEXT (an Arrow-up/down/flat glyph plus the
 * signed delta string), never by color alone — a color-blind viewer, or
 * anyone viewing a screenshot in grayscale, still gets the direction.
 */
import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import { cn } from "../../utils";
import { formatPercentDelta } from "./formatters";
import type { StatTileProps, StatTileTrend } from "./types";

function deriveTrend(delta: number): StatTileTrend {
  if (delta > 0) return "up";
  if (delta < 0) return "down";
  return "flat";
}

const TREND_ICON: Record<StatTileTrend, typeof ArrowUp> = {
  up: ArrowUp,
  down: ArrowDown,
  flat: Minus,
};

// Color is an ADDITIONAL (never sole) signal alongside the icon + signed text.
const TREND_CLASS: Record<StatTileTrend, string> = {
  up: "text-success",
  down: "text-destructive",
  flat: "text-muted-foreground",
};

export function StatTile({
  icon: Icon,
  label,
  value,
  hint,
  loading = false,
  delta,
  trend,
  deltaFormatter = formatPercentDelta,
  className,
}: StatTileProps) {
  const resolvedTrend = trend ?? (typeof delta === "number" ? deriveTrend(delta) : null);
  const TrendIcon = resolvedTrend ? TREND_ICON[resolvedTrend] : null;

  return (
    <div className={cn("overflow-hidden rounded-lg border border-border bg-card p-5", className)}>
      <div className="flex items-center gap-3">
        {Icon && (
          <div className="rounded-md bg-primary/10 p-2 text-primary">
            <Icon className="h-5 w-5" />
          </div>
        )}
        <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      </div>

      <div className="mt-3 text-3xl font-semibold tabular-nums text-card-foreground">
        {loading ? <span className="text-muted-foreground/50">—</span> : value}
      </div>

      <div className="mt-1 flex items-center gap-2 text-xs">
        {delta !== undefined && (
          <span
            className={cn(
              "inline-flex items-center gap-1 font-medium",
              resolvedTrend ? TREND_CLASS[resolvedTrend] : "text-muted-foreground",
            )}
          >
            {TrendIcon && <TrendIcon className="h-3 w-3" aria-hidden="true" />}
            {delta === null ? "—" : deltaFormatter(delta)}
          </span>
        )}
        {hint && <span className="text-muted-foreground">{hint}</span>}
      </div>
    </div>
  );
}
