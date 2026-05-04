/**
 * Agent Detail page — time-series charts + recent events + config form
 * for one specialist.
 *
 * MVP-shape time-series: the engine ships per-event rows but no per-day
 * roll-up endpoint yet. As a first cut we synthesize a single point from
 * the current rollup so the chart wiring is exercised end-to-end. When
 * the engine adds a `series` endpoint (or a `recent_events` array we can
 * bin client-side), the `series` builder below switches to the real source.
 */
import { useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Loader2, AlertCircle, ArrowLeft } from "lucide-react";
import { getAgentMetrics, getConfig } from "@/lib/api";
import { MetricsChart } from "@/components/MetricsChart";
import { RecentEventsTable } from "@/components/RecentEventsTable";
import { ConfigForm } from "@/components/ConfigForm";
import type { AgentMetrics, FullConfig, MetricPoint } from "@/lib/types";

function buildSeries(metrics: AgentMetrics | undefined): MetricPoint[] {
  if (!metrics) return [];
  if (metrics.recent_events && metrics.recent_events.length > 0) {
    // bin by date (YYYY-MM-DD); each bin = mean latency, sum cost,
    // count events, ratio of ok-events.
    const bins = new Map<string, { cost: number; latencySum: number; events: number; ok: number }>();
    for (const evt of metrics.recent_events) {
      const day = evt.ts.slice(0, 10);
      const bucket = bins.get(day) ?? { cost: 0, latencySum: 0, events: 0, ok: 0 };
      bucket.cost += evt.total_cost_usd ?? 0;
      bucket.latencySum += evt.latency_ms ?? 0;
      bucket.events += 1;
      if (evt.outcome === "ok") bucket.ok += 1;
      bins.set(day, bucket);
    }
    return Array.from(bins.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, b]) => ({
        date,
        cost: b.cost,
        latency: b.events ? b.latencySum / b.events : 0,
        events: b.events,
        successRate: b.events ? b.ok / b.events : 0,
      }));
  }
  // Fallback: single point representing the current scope rollup so the
  // chart still renders something meaningful while the engine doesn't ship
  // a series endpoint.
  if (!metrics.events) return [];
  return [
    {
      date: metrics.scope ?? "current",
      cost: metrics.total_cost_usd,
      latency: metrics.avg_latency_ms ?? 0,
      events: metrics.events,
      successRate: metrics.success_rate ?? 0,
    },
  ];
}

export default function AgentDetailPage() {
  const { name = "" } = useParams<{ name: string }>();

  const metricsQ = useQuery<AgentMetrics>({
    queryKey: ["dev-team", "agent", name, "metrics"],
    queryFn: () => getAgentMetrics(name),
    enabled: !!name,
  });

  const configQ = useQuery<FullConfig>({
    queryKey: ["dev-team", "config", "default"],
    queryFn: () => getConfig("default"),
  });

  const series = useMemo(() => buildSeries(metricsQ.data), [metricsQ.data]);
  const initialAgentCfg = configQ.data?.agents?.[name];

  return (
    <div className="space-y-6">
      <Link
        to="/"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" /> back to agents
      </Link>

      <div>
        <h1 className="text-2xl font-bold text-foreground">{name}</h1>
        <p className="text-sm text-muted-foreground">
          Time-series + recent events + per-agent config override.
        </p>
      </div>

      {metricsQ.isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      )}

      {metricsQ.isError && (
        <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive" role="alert">
          <AlertCircle className="h-5 w-5" />
          <div>
            <p className="font-semibold">Failed to load agent metrics</p>
            <p className="text-xs">
              {metricsQ.error instanceof Error ? metricsQ.error.message : String(metricsQ.error)}
            </p>
          </div>
        </div>
      )}

      {metricsQ.data && (
        <>
          <section data-testid="metrics-section" className="space-y-3">
            <h2 className="text-lg font-semibold text-foreground">Metrics</h2>
            <MetricsChart data={series} />
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-semibold text-foreground">Recent events</h2>
            <RecentEventsTable events={metricsQ.data.recent_events} />
          </section>
        </>
      )}

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-foreground">Configuration</h2>
        <ConfigForm
          agentName={name}
          initialModel={initialAgentCfg?.model as string | undefined}
          initialProvider={initialAgentCfg?.provider as string | undefined}
        />
      </section>
    </div>
  );
}
