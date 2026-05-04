/**
 * Time-series chart for per-agent metrics — recharts LineChart over the
 * four signals we track: cost, latency, events, success rate.
 *
 * Receives an array of `MetricPoint` already shaped by the page. Renders
 * a 2x2 grid of small charts (one per signal) — keeps the per-axis ranges
 * clear without overcrowding a single chart.
 */
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { MetricPoint } from "@/lib/types";

interface MetricsChartProps {
  data: MetricPoint[];
}

interface ChartCardProps {
  title: string;
  data: MetricPoint[];
  dataKey: keyof MetricPoint;
  color: string;
  formatY?: (v: number) => string;
}

function ChartCard({ title, data, dataKey, color, formatY }: ChartCardProps) {
  return (
    <div
      data-testid={`metrics-chart-${String(dataKey)}`}
      className="rounded-lg border border-border bg-card p-4"
    >
      <h4 className="text-sm font-medium text-foreground mb-3">{title}</h4>
      <div style={{ width: "100%", height: 180 }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <XAxis dataKey="date" tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} tickFormatter={formatY} />
            <Tooltip />
            <Line
              type="monotone"
              dataKey={dataKey}
              stroke={color}
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function MetricsChart({ data }: MetricsChartProps) {
  if (!data.length) {
    return (
      <div className="rounded-lg border border-border bg-card p-8 text-center text-sm text-muted-foreground">
        No time-series data yet for this scope.
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <ChartCard
        title="Cost (USD)"
        data={data}
        dataKey="cost"
        color="#22c55e"
        formatY={(v) => `$${v.toFixed(2)}`}
      />
      <ChartCard
        title="Latency (ms)"
        data={data}
        dataKey="latency"
        color="#3b82f6"
        formatY={(v) => `${Math.round(v)}`}
      />
      <ChartCard
        title="Events"
        data={data}
        dataKey="events"
        color="#a855f7"
      />
      <ChartCard
        title="Success rate"
        data={data}
        dataKey="successRate"
        color="#f97316"
        formatY={(v) => `${Math.round(v * 100)}%`}
      />
    </div>
  );
}
