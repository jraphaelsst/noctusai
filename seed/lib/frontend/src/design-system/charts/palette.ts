/**
 * Chart color palette — pure resolution logic (no DOM). The DOM-reading half
 * (getComputedStyle against the live CSS custom properties) lives in
 * `useChartTheme.ts`; this file is deliberately DOM-free so it is directly
 * unit-testable (see `reference_lib_frontend_vitest_render_harness_gap` —
 * pure logic is the safe fallback when render-heavy tests are shaky).
 *
 * The palette is CATEGORICAL (distinguishing *identity*, e.g. "which lead
 * source"), not sequential. 8 hues is the accepted ceiling for a categorical
 * palette a viewer can still tell apart at a glance — beyond that, distinct
 * series should be pre-aggregated into an "Outros" bucket (the Leads API's
 * `by-dimension` endpoint already does this: `limit=15` + a fold-in bucket).
 *
 * IMPORTANT: color is never the ONLY channel that carries meaning here —
 * every chart that uses this palette also renders a legend / tooltip label,
 * so a color-blind viewer always has the textual fallback.
 */
export const CHART_PALETTE_SIZE = 8;

/** CSS custom-property names for the categorical palette, in order. */
export const CHART_COLOR_VAR_NAMES = Array.from(
  { length: CHART_PALETTE_SIZE },
  (_, i) => `--chart-${i + 1}`,
);

/**
 * Fallback categorical colors used ONLY when running outside a DOM (e.g. a
 * unit test, or SSR) so a chart never renders with `undefined` colors. In a
 * real browser, `useChartTheme()` resolves the CSS custom properties instead
 * — these values are also the tokens.css defaults, kept in sync manually.
 */
export const CHART_PALETTE_FALLBACK: readonly string[] = [
  "hsl(220 70% 55%)",
  "hsl(160 60% 45%)",
  "hsl(35 85% 55%)",
  "hsl(280 60% 60%)",
  "hsl(10 75% 55%)",
  "hsl(195 70% 50%)",
  "hsl(320 55% 55%)",
  "hsl(95 45% 45%)",
];

/**
 * Resolve the color for series index `i`: explicit `override` wins (the
 * backend-supplied per-entity `cor` field), else cycle through `palette`
 * (wrapping if there are more series than palette entries — a caller with
 * >8 uncolored series should really be folding into "Outros" instead).
 */
export function resolveSeriesColor(
  index: number,
  override: string | null | undefined,
  palette: readonly string[] = CHART_PALETTE_FALLBACK,
): string {
  if (override) return override;
  if (palette.length === 0) return CHART_PALETTE_FALLBACK[index % CHART_PALETTE_FALLBACK.length];
  return palette[index % palette.length];
}

/**
 * Sequential single-hue scale for magnitude heatmaps (ano×mês grid). A
 * sequential scale — NOT the categorical palette above — is the correct
 * choice when color encodes an ORDERED quantity rather than identity.
 *
 * `value === null` is handled by the CALLER (render blank, no step) — this
 * function only classifies non-null values into one of `steps` buckets,
 * where step 0 is reserved for `value === 0` ("the lowest filled step",
 * never the same visual as a blank/null cell) and the highest step maps to
 * `max`. `max <= 0` degenerately maps every non-null value to step 0.
 */
export function heatmapStep(value: number, max: number, steps = 5): number {
  if (!Number.isFinite(value) || value <= 0) return 0;
  if (!Number.isFinite(max) || max <= 0) return 0;
  const clamped = Math.min(value, max);
  const ratio = clamped / max;
  // ceil so any value > 0 gets AT LEAST step 1 (distinct from the value===0 step 0),
  // and the exact max reaches the top step.
  const step = Math.ceil(ratio * (steps - 1));
  return Math.min(Math.max(step, 1), steps - 1);
}

/** Tailwind-independent, DOM-free CSS var reader with graceful fallback. */
export function readCssVar(
  varName: string,
  fallback: string,
  getComputedValue: (name: string) => string | undefined | null,
): string {
  const raw = getComputedValue(varName);
  return raw && raw.trim().length > 0 ? raw.trim() : fallback;
}

/** Wraps a raw `H S% L%` triple (tokens.css convention) in `hsl(...)` unless already wrapped. */
export function asCssColor(raw: string): string {
  const trimmed = raw.trim();
  if (trimmed.length === 0) return trimmed;
  return /^[a-z-]+\(/i.test(trimmed) || trimmed.startsWith("#") ? trimmed : `hsl(${trimmed})`;
}

/**
 * Builds a sequential single-hue lightness scale from a raw `H S% L%` triple
 * (tokens.css convention, e.g. the resolved `--primary` value) — the correct
 * chart type for an ORDERED magnitude (the Leads ano×mês heatmap), as
 * opposed to the categorical palette above. `steps[0]` is the lightest;
 * `steps[steps.length - 1]` is the base (darkest) color. Callers pair this
 * with `heatmapStep()`, which reserves index 0 for `value === 0` — a null
 * (no-data) cell is the caller's responsibility to render blank, never
 * indexed into this scale at all.
 */
export function buildSequentialScale(baseHslTriple: string, steps: number): string[] {
  const match = baseHslTriple.match(/^([\d.]+)\s+([\d.]+)%\s+([\d.]+)%$/);
  const [h, s, l] = match ? [Number(match[1]), Number(match[2]), Number(match[3])] : [220, 10, 40];
  const lightestL = Math.min(96, l + 45);
  return Array.from({ length: Math.max(1, steps) }, (_, i) => {
    const t = steps <= 1 ? 1 : i / (steps - 1);
    const lightness = lightestL + (l - lightestL) * t;
    return `hsl(${h} ${s}% ${lightness}%)`;
  });
}
