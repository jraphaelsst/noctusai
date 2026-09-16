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

/** `certidao_resultados.resultado` — NULL means "not yet determined".
 *
 * `negativa_com_homonimos` (migration 116, widening migration 107's CHECK):
 * a negativa whose document itself says so ONLY WITH A CAVEAT — no record
 * under this exact identity, but other records under the same name/CPF
 * could not be ruled out. Materially different due-diligence information
 * from a clean `negativa`, never collapsed into it. See
 * `registry.RESULTADO_VALUES`'s own docstring (backend source of truth). */
export type ResultadoValor =
  | "negativa"
  | "positiva"
  | "positiva_com_efeito_de_negativa"
  | "nao_emitida"
  | "negativa_com_homonimos";

/** `certidao_resultados.resultado_origem` — who last wrote the structured
 * fields. NULL alongside a NULL `resultado` means neither has run yet. */
export type ResultadoOrigem = "api" | "ia" | "manual";

export const RESULTADO_VALOR_LABELS: Record<ResultadoValor, string> = {
  negativa: "Negativa",
  positiva: "Positiva",
  positiva_com_efeito_de_negativa: "Positiva c/ efeito de negativa",
  nao_emitida: "Não emitida",
  negativa_com_homonimos: "Negativa c/ homônimos",
};

/**
 * `negativa` (nothing found) is the outcome a clean deal wants, hence
 * `"default"`; `positiva` (something found) is the one that blocks a
 * signature, hence `"destructive"`. `positiva_com_efeito_de_negativa` and
 * `negativa_com_homonimos` both sit between the two — flagged, not
 * blocking, but worth a second look — hence `"secondary"` for either.
 */
export const RESULTADO_VALOR_VARIANT: Record<
  ResultadoValor,
  "default" | "secondary" | "outline" | "destructive"
> = {
  negativa: "default",
  positiva: "destructive",
  positiva_com_efeito_de_negativa: "secondary",
  nao_emitida: "outline",
  negativa_com_homonimos: "secondary",
};

/**
 * `certidao_consultas.situacao_cadastral` (migration 116) — the CNPJ/CPF's
 * registration status with the source registry. A fact about the document
 * being investigated, not about any one certidão, hence it lives on the
 * CONSULTA rather than a resultado row. Manual-only today (no API this
 * module calls returns it) — see `SituacaoCadastralPatchInput`.
 */
export type SituacaoCadastral = "ativa" | "baixada" | "inapta" | "suspensa" | "nula";

export const SITUACAO_CADASTRAL_LABELS: Record<SituacaoCadastral, string> = {
  ativa: "Ativa",
  baixada: "Baixada",
  inapta: "Inapta",
  suspensa: "Suspensa",
  nula: "Nula",
};

/**
 * `PATCH /api/certidoes/consultas/{consulta_id}/situacao-cadastral` body —
 * both fields optional, but the backend refuses an empty body with a 422
 * (unlike `ResultadoPatchInput`, there is no automated writer for this
 * field to lock out today, so an empty PATCH has nothing to confirm).
 */
export interface SituacaoCadastralPatchInput {
  situacao_cadastral?: SituacaoCadastral;
  data_situacao?: string; // YYYY-MM-DD
}

/**
 * The office's contract-relevance verdict for a CNPJ's registration status —
 * derived, never typed, from `situacao_cadastral` + `data_situacao` per the
 * office's own rule: "company certidões are required when the company is
 * ativa, inapta, or baixada < 5 years ago."
 */
export type SituacaoCadastralBadgeKind = "exigida" | "fora" | "desconhecida";

export interface SituacaoCadastralBadge {
  kind: SituacaoCadastralBadgeKind;
  label: string;
}

/**
 * pt-BR badge variant per verdict. `"exigida"` gets `"default"` — it is the
 * call to action, not an error. `"fora"` gets `"outline"` — informational,
 * nothing to do. `"desconhecida"` gets `"secondary"` — distinct from both,
 * because "we don't know yet" is neither "go" nor "clear".
 */
export const SITUACAO_CADASTRAL_BADGE_VARIANT: Record<
  SituacaoCadastralBadgeKind,
  "default" | "secondary" | "outline" | "destructive"
> = {
  exigida: "default",
  fora: "outline",
  desconhecida: "secondary",
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

/** Is `emitidaEm` (`YYYY-MM-DD`) already `days` days old or older — the
 * signing-window rule ("every certidão must be emitted < 30 days before
 * signing")? `>=` per the rule's own wording (exactly 30 days old already
 * counts). Same no-timezone-shift parsing as `isValidadeVencida`. */
export function isEmissaoAntiga(
  emitidaEm: string | null | undefined,
  days: number = 30,
): boolean {
  if (!emitidaEm) return false;
  const [y, m, d] = emitidaEm.split("-").map(Number);
  const emissao = new Date(y, m - 1, d);
  const limite = getTodayAtMidnight();
  limite.setDate(limite.getDate() - days);
  return emissao.getTime() <= limite.getTime();
}

/** The same calendar day `anos` years earlier (29/02 → 28/02). Mirrors the
 * backend's `contrato_gerador/derivacao.py::anos_antes` byte-for-byte in
 * intent — JS's `setFullYear` rolls a 29/02 target into 1/03 instead of
 * clamping, so the clamp is done by hand here. */
function anosAntes(referencia: Date, anos: number): Date {
  const ano = referencia.getFullYear() - anos;
  const mes = referencia.getMonth();
  const dia = referencia.getDate();
  const candidato = new Date(ano, mes, dia);
  if (candidato.getMonth() !== mes) {
    return new Date(ano, mes + 1, 0); // last day of `mes` in `ano`
  }
  return candidato;
}

/** True when `data` (`YYYY-MM-DD`) is LESS than `anos` years before today —
 * exactly `anos` years earlier is not "less than". Mirrors the backend's
 * `contrato_gerador/derivacao.py::ha_menos_de_anos` boundary exactly, so the
 * office's "< 5 years" rule reads the same on both sides of the wire. */
function haMenosDeAnos(data: string, anos: number): boolean {
  const [y, m, d] = data.split("-").map(Number);
  const dataObj = new Date(y, m - 1, d);
  return dataObj.getTime() > anosAntes(getTodayAtMidnight(), anos).getTime();
}

/**
 * The office's contract-relevance verdict for a CNPJ's registration status:
 *
 *   - `ativa` or `inapta` → always "exigida no contrato".
 *   - `baixada` less than 5 years ago → "exigida no contrato"; 5 years ago
 *     or older → "fora do contrato"; no `dataSituacao` to check the window
 *     against → "situação desconhecida" (the age genuinely cannot be told).
 *   - `suspensa` / `nula` → always "fora do contrato".
 *   - no `situacaoCadastral` at all → "situação desconhecida".
 */
export function situacaoCadastralBadge(
  situacaoCadastral: SituacaoCadastral | null | undefined,
  dataSituacao: string | null | undefined,
): SituacaoCadastralBadge {
  if (situacaoCadastral === "ativa" || situacaoCadastral === "inapta") {
    return { kind: "exigida", label: "Exigida no contrato" };
  }
  if (situacaoCadastral === "baixada") {
    if (!dataSituacao) {
      return { kind: "desconhecida", label: "Situação desconhecida" };
    }
    return haMenosDeAnos(dataSituacao, 5)
      ? { kind: "exigida", label: "Exigida no contrato" }
      : { kind: "fora", label: "Fora do contrato" };
  }
  if (situacaoCadastral === "suspensa" || situacaoCadastral === "nula") {
    return { kind: "fora", label: "Fora do contrato" };
  }
  return { kind: "desconhecida", label: "Situação desconhecida" };
}
