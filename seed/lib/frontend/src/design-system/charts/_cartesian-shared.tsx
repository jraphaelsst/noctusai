/**
 * Internal helpers shared by LineChart / AreaChart / BarChart — NOT exported
 * from `index.ts`. Keeps axis/grid/tooltip styling in exactly one place
 * instead of copy-pasted three times (the exact recurrence this slice exists
 * to end — see leads-module-PROJECT.md §8).
 */
import { CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
import type { ChartTheme } from "./useChartTheme";
import { formatCompactNumber } from "./formatters";

export function sharedGrid(theme: ChartTheme) {
  return <CartesianGrid strokeDasharray="3 3" stroke={theme.gridColor} />;
}

/**
 * The CATEGORY axis (the x-values / dimension labels). `orientation` picks
 * which recharts axis component renders it — BarChart's `horizontal` mode
 * needs the category on the Y-axis (recharts' `layout="vertical"` swaps
 * which physical axis is numeric vs. categorical; LineChart/AreaChart always
 * use the default "x" orientation).
 */
export function categoryAxis(
  orientation: "x" | "y",
  dataKey: string,
  theme: ChartTheme,
  tickFormatter?: (value: string) => string,
) {
  const shared = {
    dataKey,
    type: "category" as const,
    fontSize: 11,
    stroke: theme.axisColor,
    tickLine: false,
    axisLine: { stroke: theme.gridColor },
    tickFormatter,
  };
  return orientation === "x" ? <XAxis {...shared} /> : <YAxis {...shared} width={96} />;
}

/** The VALUE (numeric) axis. */
export function valueAxis(
  orientation: "x" | "y",
  theme: ChartTheme,
  valueFormatter: (value: number) => string,
) {
  const shared = {
    type: "number" as const,
    fontSize: 11,
    stroke: theme.axisColor,
    tickLine: false,
    axisLine: { stroke: theme.gridColor },
    tickFormatter: (v: number) => valueFormatter(v),
  };
  return orientation === "x" ? <XAxis {...shared} /> : <YAxis {...shared} />;
}

/** Convenience: LineChart/AreaChart's fixed shape — category on X, value on Y. */
export function sharedXAxis(xKey: string, theme: ChartTheme, xTickFormatter?: (value: string) => string) {
  return categoryAxis("x", xKey, theme, xTickFormatter);
}
export function sharedYAxis(theme: ChartTheme, valueFormatter: (value: number) => string) {
  return valueAxis("y", theme, valueFormatter);
}

export function sharedTooltip(
  theme: ChartTheme,
  valueFormatter: (value: number) => string,
  labelByKey: Record<string, string>,
) {
  return (
    <Tooltip
      formatter={(value: number, name: string) => [valueFormatter(value), labelByKey[name] ?? name]}
      contentStyle={{
        background: theme.tooltipBackground,
        border: `1px solid ${theme.tooltipBorder}`,
        borderRadius: 6,
        fontSize: 12,
      }}
      labelStyle={{ color: theme.tooltipForeground }}
    />
  );
}

export const DEFAULT_VALUE_FORMATTER = formatCompactNumber as (value: number) => string;
