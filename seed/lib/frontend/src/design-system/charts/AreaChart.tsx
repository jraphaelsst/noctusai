/**
 * AreaChart — thin, typed recharts wrapper. `stacked` renders series on top
 * of each other (the Leads "evolução mensal, split by origem" view — see
 * leads-module-PROJECT.md §6) instead of overlapping fills.
 *
 *   <AreaChart data={points} xKey="label" series={sourceSeries} stacked />
 */
import { Area, AreaChart as RAreaChart, Legend, ResponsiveContainer } from "recharts";
import { cn } from "../../utils";
import { useChartTheme } from "./useChartTheme";
import type { AreaChartProps as AreaChartComponentProps, ChartDatum } from "./types";
import { DEFAULT_VALUE_FORMATTER, sharedGrid, sharedTooltip, sharedXAxis, sharedYAxis } from "./_cartesian-shared";

export function AreaChart<T extends ChartDatum = ChartDatum>({
  data,
  xKey,
  series,
  height = 280,
  valueFormatter = DEFAULT_VALUE_FORMATTER,
  xTickFormatter,
  stacked = false,
  className,
}: AreaChartComponentProps<T>) {
  const theme = useChartTheme();
  const labelByKey = Object.fromEntries(series.map((s): [string, string] => [s.key, s.label]));

  return (
    <div className={cn("w-full", className)} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RAreaChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          {sharedGrid(theme)}
          {sharedXAxis(xKey, theme, xTickFormatter)}
          {sharedYAxis(theme, valueFormatter)}
          {sharedTooltip(theme, valueFormatter, labelByKey)}
          {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
          {series.map((s, i) => {
            const color = theme.getSeriesColor(i, s.color);
            return (
              <Area
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stackId={stacked ? "stack" : undefined}
                stroke={color}
                fill={color}
                fillOpacity={0.18}
                strokeWidth={2}
              />
            );
          })}
        </RAreaChart>
      </ResponsiveContainer>
    </div>
  );
}
