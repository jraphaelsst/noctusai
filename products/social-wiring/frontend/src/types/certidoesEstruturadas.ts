/**
 * Structured certidão fields — contract automation F1 (migration 107).
 *
 * `resultado` / `resultado_origem` and the rest of the new columns live on
 * `CertidaoResultado` itself (`@/hooks/useCertidoes`) — a resultado row is a
 * resultado row whether it is read via the per-consulta detail endpoint
 * (`GET /consultas/{id}`) or the per-parte endpoint this slice adds
 * (`GET /partes/{id}/resultados`), and a second, parallel interface would
 * let the two views' types drift the moment either backend read changes its
 * `select()`. This file therefore does NOT declare a resultado interface —
 * it holds the value vocabularies + pt-BR labels every consumer of those
 * fields renders off (`CertidoesPartePanel`, `pages/Certidoes.tsx`), the
 * PATCH input shape, and the two date-flag helpers. One-directional import:
 * this file never imports FROM `@/hooks/useCertidoes` (that file imports
 * FROM here instead), so there is no cycle between the two.
 *
 * Backend source of truth: `app/modules/certidoes/schemas.py::ResultadoPatch`
 * (the `Literal` for `resultado`) and migration 107's CHECK constraints —
 * both documented as needing to stay in sync with `registry.RESULTADO_VALUES`
 * BY HAND (no shared import is possible across Python/SQL/TypeScript).
 */
import { getTodayAtMidnight } from "@/lib/utils";

/** `certidao_resultados.resultado` — NULL means "not yet determined". */
export type ResultadoValor =
  | "negativa"
  | "positiva"
  | "positiva_com_efeito_de_negativa"
  | "nao_emitida";

/** `certidao_resultados.resultado_origem` — who last wrote the structured
 * fields. NULL alongside a NULL `resultado` means neither has run yet. */
export type ResultadoOrigem = "api" | "ia" | "manual";

export const RESULTADO_VALOR_LABELS: Record<ResultadoValor, string> = {
  negativa: "Negativa",
  positiva: "Positiva",
  positiva_com_efeito_de_negativa: "Positiva c/ efeito de negativa",
  nao_emitida: "Não emitida",
};

/**
 * `negativa` (nothing found) is the outcome a clean deal wants, hence
 * `"default"`; `positiva` (something found) is the one that blocks a
 * signature, hence `"destructive"`. `positiva_com_efeito_de_negativa` sits
 * between the two — flagged, not blocking — hence `"secondary"`.
 */
export const RESULTADO_VALOR_VARIANT: Record<
  ResultadoValor,
  "default" | "secondary" | "outline" | "destructive"
> = {
  negativa: "default",
  positiva: "destructive",
  positiva_com_efeito_de_negativa: "secondary",
  nao_emitida: "outline",
};

export const RESULTADO_ORIGEM_LABELS: Record<ResultadoOrigem, string> = {
  api: "API",
  ia: "IA (sugestão)",
  manual: "Confirmado manualmente",
};

/**
 * `PATCH /api/certidoes/resultados/{id}` body — every field optional; an
 * empty object `{}` is a valid "I reviewed the API/IA-suggested values and
 * they are correct" confirmation, not a no-op (see `schemas.ResultadoPatch`).
 *
 * 🔴 Every key here is `Optional[str]`-style OMISSION, not null-as-clear:
 * `undefined` is dropped by `JSON.stringify` before the request body is
 * built, which is what makes "send only what changed" work — but it also
 * means this shape cannot express "clear this field back to empty" (the
 * backend's `exclude_unset` treats an omitted key as "leave alone", not
 * "set to NULL"). `CertidoesPartePanel`'s edit form inherits that limit.
 */
export interface ResultadoPatchInput {
  numero?: string;
  emitida_em?: string; // YYYY-MM-DD
  validade_ate?: string; // YYYY-MM-DD
  resultado?: ResultadoValor;
}

/** Is `validadeAte` (a `YYYY-MM-DD` string) already in the past? Local-date
 * compare, matching `formatDate`'s own no-timezone-shift parsing — a
 * certidão printed "válida até 2026-09-14" should read as expired starting
 * the 15th in the viewer's OWN calendar day, not UTC's. */
export function isValidadeVencida(validadeAte: string | null | undefined): boolean {
  if (!validadeAte) return false;
  const [y, m, d] = validadeAte.split("-").map(Number);
  const validade = new Date(y, m - 1, d);
  return validade.getTime() < getTodayAtMidnight().getTime();
}

/** Is `validadeAte` within the next `days` days, and not already expired? */
export function isValidadeVencendo(
  validadeAte: string | null | undefined,
  days: number = 30,
): boolean {
  if (!validadeAte) return false;
  const [y, m, d] = validadeAte.split("-").map(Number);
  const validade = new Date(y, m - 1, d);
  const hoje = getTodayAtMidnight();
  const limite = new Date(hoje);
  limite.setDate(limite.getDate() + days);
  return validade.getTime() >= hoje.getTime() && validade.getTime() <= limite.getTime();
}
