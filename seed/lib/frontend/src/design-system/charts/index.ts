/**
 * Chart / KPI / filter organs — seed-canonical, fleet-wide.
 *
 * See leads-module-PROJECT.md §7/§8 for why these live here instead of a
 * 4th product-local copy (N=3 recurrence rule): social-wiring's inline
 * recharts, personal-finance's `charts/*ChartCard`, and erp-imobiliario's
 * `ui/chart.tsx` are the three pre-existing hand-rolled sets this formalizes.
 */
export { ChartCard } from "./ChartCard";
export type { ChartCardProps } from "./ChartCard";

export { LineChart } from "./LineChart";
export { AreaChart } from "./AreaChart";
export { BarChart } from "./BarChart";
export { DonutChart } from "./DonutChart";
export { Heatmap } from "./Heatmap";

export { StatTile } from "./StatTile";
export { StatTileRow } from "./StatTileRow";
export { FilterBar } from "./FilterBar";

export { useChartTheme } from "./useChartTheme";
export type { ChartTheme } from "./useChartTheme";

export {
  CHART_PALETTE_SIZE,
  CHART_COLOR_VAR_NAMES,
  CHART_PALETTE_FALLBACK,
  resolveSeriesColor,
  heatmapStep,
  buildSequentialScale,
} from "./palette";

export { formatCompactNumber, formatPercent, formatPercentDelta, PT_BR_MONTH_LABELS_SHORT } from "./formatters";

export type {
  ChartDatum,
  ChartSeries,
  CartesianChartProps,
  LineChartProps,
  AreaChartProps,
  BarChartProps,
  DonutChartProps,
  HeatmapProps,
  StatTileTrend,
  StatTileProps,
  StatTileRowProps,
  FilterChip,
  FilterBarProps,
} from "./types";
