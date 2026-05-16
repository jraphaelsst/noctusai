/**
 * MetricCard — single KPI tile for the dashboard's top row.
 *
 * Phase 4 ships the static-number variant. Trend (delta vs prior period)
 * is deferred until a daily-snapshot table exists; would otherwise need
 * a separate analytics API contract.
 */
import type { LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface MetricCardProps {
  icon: LucideIcon;
  label: string;
  value: string;
  hint?: string;
  loading?: boolean;
  className?: string;
}

export function MetricCard({
  icon: Icon,
  label,
  value,
  hint,
  loading,
  className,
}: MetricCardProps) {
  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardContent className="p-5">
        <div className="flex items-center gap-3">
          <div className="rounded-md bg-primary/10 p-2 text-primary">
            <Icon className="h-5 w-5" />
          </div>
          <div className="text-xs uppercase tracking-wide text-muted-foreground">
            {label}
          </div>
        </div>
        <div className="mt-3 text-3xl font-semibold tabular-nums">
          {loading ? <span className="text-muted-foreground/50">—</span> : value}
        </div>
        {hint && (
          <div className="mt-1 text-xs text-muted-foreground">{hint}</div>
        )}
      </CardContent>
    </Card>
  );
}
