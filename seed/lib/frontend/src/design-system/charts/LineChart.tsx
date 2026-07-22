/**
 * LineChart — thin, typed recharts wrapper. See `types.ts` for the shared
 * `CartesianChartProps` shape and `_cartesian-shared.tsx` for the axis/grid/
 * tooltip boilerplate this shares with AreaChart/BarChart.
 *
 *   <LineChart data={points} xKey="label" series={[{ key: "total", label: "Leads" }]} />
 */
import { Line, LineChart as RLineChart, Legend, ResponsiveContainer } from "recharts";
import { cn } from "../../utils";
import { useChartTheme } from "./useChartTheme";
import type { LineChartProps as LineChartComponentProps, ChartDatum } from "./types";
import { DEFAULT_VALUE_FORMATTER, sharedGrid, sharedTooltip, sharedXAxis, sharedYAxis } from "./_cartesian-shared";

export function LineChart<T extends ChartDatum = ChartDatum>({
  data,
  xKey,
  series,
  height = 280,
  valueFormatter = DEFAULT_VALUE_FORMATTER,
  xTickFormatter,
  className,
}: LineChartComponentProps<T>) {
  const theme = useChartTheme();
  const labelByKey = Object.fromEntries(series.map((s): [string, string] => [s.key, s.label]));

  return (
    <div className={cn("w-full", className)} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RLineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          {sharedGrid(theme)}
          {sharedXAxis(xKey, theme, xTickFormatter)}
          {sharedYAxis(theme, valueFormatter)}
          {sharedTooltip(theme, valueFormatter, labelByKey)}
          {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
          {series.map((s, i) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.label}
              stroke={theme.getSeriesColor(i, s.color)}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
          ))}
        </RLineChart>
      </ResponsiveContainer>
    </div>
  );
}
