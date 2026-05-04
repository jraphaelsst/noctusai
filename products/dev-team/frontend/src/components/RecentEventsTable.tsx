/**
 * Recent events table — last 50 telemetry rows for one agent.
 *
 * The engine's `get_agent_metrics` does NOT currently return a
 * `recent_events` array (only aggregates + tool distribution). When the
 * field is absent we render the "no recent events" empty state. Tracked
 * in findings.md as a backend gap.
 */
import { CheckCircle, XCircle } from "lucide-react";
import type { RecentEvent } from "@/lib/types";

interface RecentEventsTableProps {
  events?: RecentEvent[];
}

function formatLatency(ms: number | null): string {
  if (ms === null || ms === undefined) return "-";
  return `${Math.round(ms)} ms`;
}

function formatCost(usd: number | null): string {
  if (usd === null || usd === undefined) return "-";
  return `$${usd.toFixed(4)}`;
}

export function RecentEventsTable({ events }: RecentEventsTableProps) {
  if (!events || events.length === 0) {
    return (
      <div
        data-testid="recent-events-empty"
        className="rounded-lg border border-border bg-card p-6 text-center text-sm text-muted-foreground"
      >
        No recent events for this scope.
      </div>
    );
  }
  return (
    <div
      data-testid="recent-events-table"
      className="rounded-lg border border-border bg-card overflow-x-auto"
    >
      <table className="min-w-full text-sm">
        <thead className="border-b border-border bg-muted/40">
          <tr>
            <th className="px-3 py-2 text-left font-medium">Time</th>
            <th className="px-3 py-2 text-left font-medium">Outcome</th>
            <th className="px-3 py-2 text-right font-medium">Latency</th>
            <th className="px-3 py-2 text-right font-medium">Cost</th>
            <th className="px-3 py-2 text-left font-medium">Task</th>
          </tr>
        </thead>
        <tbody>
          {events.map((evt, idx) => (
            <tr key={`${evt.ts}-${idx}`} className="border-b border-border last:border-0">
              <td className="px-3 py-2 whitespace-nowrap text-xs text-muted-foreground">
                {evt.ts}
              </td>
              <td className="px-3 py-2">
                {evt.outcome === "ok" ? (
                  <span className="inline-flex items-center gap-1 text-green-600">
                    <CheckCircle className="h-3 w-3" /> ok
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-destructive">
                    <XCircle className="h-3 w-3" /> {evt.outcome}
                  </span>
                )}
              </td>
              <td className="px-3 py-2 text-right text-xs">{formatLatency(evt.latency_ms)}</td>
              <td className="px-3 py-2 text-right text-xs">{formatCost(evt.total_cost_usd)}</td>
              <td
                className="px-3 py-2 max-w-md truncate text-xs text-muted-foreground"
                title={evt.task ?? ""}
              >
                {evt.task ?? "-"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
