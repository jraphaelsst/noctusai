/**
 * ViewsChart — recharts line chart of cumulative views across cached videos.
 *
 * Phase 4 renders a snapshot view: one point per video, ordered by
 * published_at ASC, value = cumulative view_count. Daily-history would
 * need a snapshots table (deferred — N=1 product, daily-rollup project
 * file when a 2nd product needs analytics).
 *
 * Uses a thin recharts wrapper so the component stays portable if we
 * swap charting libraries; the hook gives us already-shaped data.
 */
import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TopVideo } from "@/hooks/useDashboard";
import { formatNumber } from "@/hooks/useDashboard";

interface ViewsChartProps {
  videos: TopVideo[];
}

export function ViewsChart({ videos }: ViewsChartProps) {
  const data = useMemo(() => {
    // Sort ascending by published_at, then build a cumulative-view series.
    const sorted = [...videos]
      .filter((v) => v.published_at)
      .sort((a, b) => {
        const aDate = a.published_at ? new Date(a.published_at).getTime() : 0;
        const bDate = b.published_at ? new Date(b.published_at).getTime() : 0;
        return aDate - bDate;
      });
    let cumulative = 0;
    return sorted.map((v) => {
      cumulative += v.view_count;
      return {
        x: v.published_at
          ? new Date(v.published_at).toLocaleDateString("pt-BR", {
              month: "short",
              year: "2-digit",
            })
          : "",
        cumulative,
        per: v.view_count,
        title: v.title ?? v.youtube_video_id,
      };
    });
  }, [videos]);

  if (data.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground">
        Nenhum video no cache. Sincronize na pagina de Videos.
      </div>
    );
  }

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
          <XAxis dataKey="x" fontSize={11} stroke="currentColor" opacity={0.6} />
          <YAxis
            tickFormatter={formatNumber}
            fontSize={11}
            stroke="currentColor"
            opacity={0.6}
          />
          <Tooltip
            formatter={(value: number, _name, payload) => [
              formatNumber(value),
              payload?.payload?.title ?? "Visualizacoes",
            ]}
            labelStyle={{ color: "var(--foreground)" }}
            contentStyle={{
              background: "var(--background)",
              border: "1px solid var(--border)",
              borderRadius: 6,
            }}
          />
          <Line
            type="monotone"
            dataKey="cumulative"
            stroke="hsl(var(--primary, 220 90% 56%))"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
