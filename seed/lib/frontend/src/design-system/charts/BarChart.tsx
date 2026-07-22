/**
 * BarChart — thin, typed recharts wrapper. `horizontal` renders ranked
 * horizontal bars (the Leads "barras top-10 corretores" ranking view — see
 * leads-module-PROJECT.md §6), which needs the category on the Y-axis and
 * value on the X-axis (recharts' `layout="vertical"` naming, which is the
 * opposite of what most callers expect — hidden behind the `horizontal` prop
 * so consumers never have to know recharts' inverted `layout` vocabulary).
 *
 *   <BarChart data={ranked} xKey="label" series={[{ key: "total", label: "Leads" }]} horizontal />
 */
import { Bar, BarChart as RBarChart, Legend, ResponsiveContainer } from "recharts";
import { cn } from "../../utils";
import { useChartTheme } from "./useChartTheme";
import type { BarChartProps as BarChartComponentProps, ChartDatum } from "./types";
import { categoryAxis, DEFAULT_VALUE_FORMATTER, sharedGrid, sharedTooltip, valueAxis } from "./_cartesian-shared";

export function BarChart<T extends ChartDatum = ChartDatum>({
  data,
  xKey,
  series,
  height = 280,
  valueFormatter = DEFAULT_VALUE_FORMATTER,
  xTickFormatter,
  stacked = false,
  horizontal = false,
  className,
}: BarChartComponentProps<T>) {
  const theme = useChartTheme();
  const labelByKey = Object.fromEntries(series.map((s): [string, string] => [s.key, s.label]));

  return (
    <div className={cn("w-full", className)} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RBarChart
          data={data}
          layout={horizontal ? "vertical" : "horizontal"}
          margin={{ top: 8, right: 16, left: horizontal ? 24 : 0, bottom: 0 }}
        >
          {sharedGrid(theme)}
          {horizontal ? (
            <>
              {/* layout="vertical" swaps recharts' axis semantics: X carries the
                  numeric value, Y carries the category — the ranked-bars shape. */}
              {valueAxis("x", theme, valueFormatter)}
              {categoryAxis("y", xKey, theme, xTickFormatter)}
            </>
          ) : (
            <>
              {categoryAxis("x", xKey, theme, xTickFormatter)}
              {valueAxis("y", theme, valueFormatter)}
            </>
          )}
          {sharedTooltip(theme, valueFormatter, labelByKey)}
          {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
          {series.map((s, i) => (
            <Bar
              key={s.key}
              dataKey={s.key}
              name={s.label}
              stackId={stacked ? "stack" : undefined}
              fill={theme.getSeriesColor(i, s.color)}
              radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]}
            />
          ))}
        </RBarChart>
      </ResponsiveContainer>
    </div>
  );
}
