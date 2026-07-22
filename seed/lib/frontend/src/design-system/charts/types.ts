/**
 * Shared types for the seed chart/KPI/filter organs.
 *
 * These mirror the union of what the three pre-existing hand-rolled sets
 * actually needed (social-wiring ViewsChart/VisaoGeralPanel/MetricCard,
 * personal-finance charts/*, erp-imobiliario ui/chart.tsx) plus what the
 * Leads analytics page (products/social-wiring/projects/leads-module-PROJECT.md
 * §5.3/§6) requires — the first real consumer.
 */
import type { ComponentType, ReactNode } from "react";

/** A generic row shape a chart plots against — recharts wants `Record<string, unknown>`. */
export type ChartDatum = Record<string, unknown>;

/**
 * One plotted series (a line / area / bar column). `color` is OPTIONAL —
 * most backends in this platform (see leads-module-PROJECT.md `lead_sources.cor`
 * / `lead_corretores.cor`) hand the frontend a per-entity hex color; when the
 * caller omits it, the series falls back to the theme's categorical palette
 * cycling by array index (see `palette.ts` / `useChartTheme`).
 */
export interface ChartSeries {
  /** dataKey — the field on each `data` row this series plots. */
  key: string;
  /** Human label — legend + tooltip. */
  label: string;
  /** Literal CSS color (hex/hsl/rgb). Omit to use the palette fallback. */
  color?: string;
}

/** Shared prop surface for the cartesian (x-axis) chart wrappers. */
export interface CartesianChartProps<T extends ChartDatum = ChartDatum> {
  data: T[];
  /** Field on each row used as the X-axis category (or timeseries bucket). */
  xKey: Extract<keyof T, string>;
  series: ChartSeries[];
  /** Chart body height in px. Default 280. */
  height?: number;
  /** Formats Y-axis ticks + tooltip values. Default: locale-aware compact number. */
  valueFormatter?: (value: number) => string;
  /** Formats X-axis tick labels (e.g. re-labeling a raw bucket key). Identity by default. */
  xTickFormatter?: (value: string) => string;
  className?: string;
}

export interface LineChartProps<T extends ChartDatum = ChartDatum> extends CartesianChartProps<T> {}

export interface AreaChartProps<T extends ChartDatum = ChartDatum> extends CartesianChartProps<T> {
  /** Stack series on top of each other instead of overlaying. Default false. */
  stacked?: boolean;
}

export interface BarChartProps<T extends ChartDatum = ChartDatum> extends CartesianChartProps<T> {
  stacked?: boolean;
  /** Ranked horizontal bars (dimension on the Y-axis) instead of vertical columns. */
  horizontal?: boolean;
}

/**
 * DonutChart plots ROWS as slices (one value per row), not columns like the
 * other three — so it does NOT share `xKey`/`series`. This matches every
 * existing consumer's actual data shape (`{label, total, cor}[]` — see
 * `DonutChartCard` in personal-finance and `DimensionBucket` in the Leads
 * contract) rather than forcing an artificial `series` array onto pie data.
 */
export interface DonutChartProps<T extends ChartDatum = ChartDatum> {
  data: T[];
  nameKey: Extract<keyof T, string>;
  valueKey: Extract<keyof T, string>;
  /** Per-row literal color field (e.g. `cor`). Falls back to the palette by index. */
  colorKey?: Extract<keyof T, string>;
  height?: number;
  valueFormatter?: (value: number) => string;
  /** 0 (pie) .. <1 (donut). Default 0.6. */
  innerRadiusRatio?: number;
  className?: string;
}

/** ano×mês heatmap cell matrix — matches `HeatmapOut` in the Leads API contract 1:1. */
export interface HeatmapProps {
  /** Years to render as rows, in the order given. */
  anos: number[];
  /** cells[String(ano)][mes-1]. `null` = no data (blank cell) ≠ `0` (lowest filled step). */
  cells: Record<string, (number | null)[]>;
  /** Max cell value across the whole matrix — anchors the color scale. */
  max: number;
  /** pt-BR short month labels by default (Jan..Dez). */
  monthLabels?: string[];
  valueFormatter?: (value: number) => string;
  onCellClick?: (ano: number, mes: number, value: number | null) => void;
  className?: string;
}

export type StatTileTrend = "up" | "down" | "flat";

export interface StatTileProps {
  icon?: ComponentType<{ className?: string }>;
  label: string;
  value: ReactNode;
  hint?: string;
  loading?: boolean;
  /**
   * Percent delta vs. the comparison window, already in percent units
   * (`23.4`, not `0.234` — matches `variacao_pct` in the Leads contract).
   * `null` renders as "—", NEVER "0%" — the caller must not coerce an
   * unresolvable comparison into a false zero.
   */
  delta?: number | null;
  /** Explicit direction. When omitted, derived from `delta`'s sign (0 => "flat"). */
  trend?: StatTileTrend;
  /** Default: `${sign}${delta.toFixed(1)}%`. */
  deltaFormatter?: (delta: number) => string;
  className?: string;
}

export interface StatTileRowProps {
  children: ReactNode;
  className?: string;
}

export interface FilterChip {
  key: string;
  label: string;
  onClear: () => void;
}

export interface FilterBarProps {
  /** Filter control slots (selects, date pickers, search input, ...). */
  children: ReactNode;
  /** Active-filter chips row, each individually clearable. */
  chips?: FilterChip[];
  /** "Limpar tudo" action — shown only when chips is non-empty and this is set. */
  onClearAll?: () => void;
  clearAllLabel?: string;
  /** Collapsed-by-default on narrow viewports (still expandable). Default false. */
  defaultCollapsed?: boolean;
  className?: string;
}
