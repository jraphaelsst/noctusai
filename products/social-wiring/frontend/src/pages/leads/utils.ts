/**
 * Leads module — small pure helpers shared across the "by dimension" drill-in
 * pages (Origens / Corretores / Empreendimentos). Extracted once these three
 * pages independently needed the same "outros" guard + attribution-subtitle
 * shape (the N=3 recurrence threshold, §1 of CLAUDE.md's DRY rule).
 */

/**
 * `_reference_by_dimension` (analytics_service.py) folds every bucket past
 * `limit` into one synthetic remainder row with the LITERAL key `"outros"`
 * (never a real id/slug/value). It is an AGGREGATE, not a filterable
 * dimension value:
 *   - `origem_id` / `corretor_id` are typed UUID params → `?origem_id=outros`
 *     422s every endpoint that shares `get_lead_filters`.
 *   - `empreendimento` / `regiao` are untyped strings → `outros` is accepted
 *     as a literal value and silently filters everything to zero (reads as
 *     "no data" instead of an error).
 * Drill-in rows for this bucket must render non-interactive everywhere.
 */
export const OUTROS_BUCKET_KEY = "outros";

export function isOutrosBucket(key: string): boolean {
  return key === OUTROS_BUCKET_KEY;
}

/** Plain pt-BR thousands-separated integer — NEVER abbreviated (K/M); used
 * where exact counts matter ("12.098 de 12.177"), unlike `formatCompactNumber`. */
export function formatExactCount(value: number): string {
  return value.toLocaleString("pt-BR");
}

/**
 * A "by dimension" total (origem/corretor) only counts rows that resolve to
 * that dimension — rows with no `origem_id` / `corretor_id` are excluded by
 * design (`_split_key_label_cor` returns `None` for them). That total can
 * read lower than the grand total shown elsewhere (e.g. `LeadsSummary.total`),
 * which silently misleads a viewer into thinking a donut/ranking covers every
 * lead. Surface the gap explicitly instead of leaving it implicit.
 */
/**
 * Every mutation error is an `Error("[422] <decoded message>")` thrown by the
 * seed api client (`extractErrorMessage` in `seed/lib/frontend/src/api.ts`
 * already decodes FastAPI/Pydantic details into that string). Every toast
 * in this module used to discard it and show a generic "Erro ao X." —
 * undiagnosable for a non-technical user and the reason #3/#4's 422s were
 * invisible until this audit (leads-p0-frontend-ux finding #10). Strip the
 * `[status] ` prefix and append the rest; fall back to the generic string
 * alone when the error carries no message.
 */
export function describeError(err: unknown, fallback: string): string {
  const message = err instanceof Error ? err.message : "";
  const decoded = message.replace(/^\[\d+\]\s*/, "").trim();
  return decoded ? `${fallback} ${decoded}` : fallback;
}

export function attributionSubtitle(params: {
  dimTotal: number | null | undefined;
  grandTotal: number | null | undefined;
  dimensionLabel: string;
  missingLabel: string;
}): string | null {
  const { dimTotal, grandTotal, dimensionLabel, missingLabel } = params;
  if (dimTotal == null || grandTotal == null) return null;
  const missing = grandTotal - dimTotal;
  const base = `${formatExactCount(dimTotal)} de ${formatExactCount(grandTotal)} leads ${dimensionLabel}`;
  return missing > 0 ? `${base} (${formatExactCount(missing)} ${missingLabel}).` : `${base}.`;
}
