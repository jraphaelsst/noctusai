/**
 * useChartTheme — resolves the chart color palette + axis/grid/tooltip
 * colors from the live CSS custom properties (tokens.css), so a chart
 * follows light/dark theme without any consumer hardcoding
 * `hsl(var(--primary))`-style strings — recharts `stroke`/`fill` props need
 * a literal resolved color string, not a CSS variable reference, so
 * something has to do this resolution; this hook is that single place.
 *
 * Re-resolves whenever `document.documentElement`'s `class` attribute
 * changes (the seed's `useTheme()` hook toggles the `dark` class there) via
 * a MutationObserver, so a live theme toggle updates chart colors without
 * a page reload.
 */
import { useEffect, useMemo, useState } from "react";
import {
  asCssColor,
  buildSequentialScale,
  CHART_COLOR_VAR_NAMES,
  CHART_PALETTE_FALLBACK,
  readCssVar,
  resolveSeriesColor,
} from "./palette";

export interface ChartTheme {
  /** Resolved categorical palette (8 colors), theme-aware. */
  palette: readonly string[];
  /** `resolveSeriesColor` pre-bound to the resolved palette. */
  getSeriesColor: (index: number, override?: string | null) => string;
  /** Axis line / tick / grid color (muted-foreground based). */
  axisColor: string;
  gridColor: string;
  /** Tooltip surface. */
  tooltipBackground: string;
  tooltipBorder: string;
  tooltipForeground: string;
  /** Sequential single-hue scale (magnitude — heatmaps), lightest first. */
  sequentialScale: (steps: number) => string[];
}

function readComputed(el: HTMLElement, name: string): string | undefined {
  if (typeof window === "undefined" || typeof getComputedStyle !== "function") return undefined;
  return getComputedStyle(el).getPropertyValue(name);
}

function resolveTheme(): ChartTheme {
  const root = typeof document !== "undefined" ? document.documentElement : null;
  const get = (name: string, fallback: string) =>
    root ? asCssColor(readCssVar(name, fallback, (n) => readComputed(root, n))) : asCssColor(fallback);

  const palette = CHART_COLOR_VAR_NAMES.map((varName, i) =>
    get(varName, CHART_PALETTE_FALLBACK[i % CHART_PALETTE_FALLBACK.length]),
  );

  const rawPrimary = root ? readCssVar("--primary", "220 10% 40%", (n) => readComputed(root, n)) : "220 10% 40%";

  return {
    palette,
    getSeriesColor: (index, override) => resolveSeriesColor(index, override, palette),
    axisColor: get("--muted-foreground", "0 0% 50%"),
    gridColor: get("--border", "0 0% 88%"),
    tooltipBackground: get("--background", "0 0% 97%"),
    tooltipBorder: get("--border", "0 0% 88%"),
    tooltipForeground: get("--foreground", "0 0% 10%"),
    sequentialScale: (steps: number) => buildSequentialScale(rawPrimary, steps),
  };
}

export function useChartTheme(): ChartTheme {
  const [tick, setTick] = useState(0);
  // `tick` is an explicit dependency so a `dark` class toggle (observed below)
  // forces re-resolution against the new computed styles.
  const theme = useMemo(() => resolveTheme(), [tick]);

  useEffect(() => {
    if (typeof document === "undefined" || typeof MutationObserver === "undefined") return;
    const observer = new MutationObserver(() => setTick((n) => n + 1));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  return theme;
}
