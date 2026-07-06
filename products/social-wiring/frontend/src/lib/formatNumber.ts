/**
 * formatNumber — shared K/M-suffixed pt-BR number formatter.
 *
 * Absorbed here (DRY, N=2→3 recurrence) after `useDashboard.ts` and the
 * now-retired `InstagramInsights.tsx` each carried a near-identical copy
 * (the latter null-safe, the former not) — the Meta dashboard subtabs would
 * have been a 3rd, MUST-formalize instance. `useDashboard.ts` re-exports
 * this for back-compat so existing consumers (ViewsChart, VisaoGeralPanel)
 * don't need an import-path change.
 */
export function formatNumber(n: number | null | undefined): string {
  const v = n ?? 0;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return v.toLocaleString("pt-BR");
}
