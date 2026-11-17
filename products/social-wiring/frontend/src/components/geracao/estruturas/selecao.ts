/**
 * Pure rules of an Estrutura selection (contract §6.6/§6.7, DC7): at most 3, all of one `formato`.
 * The server enforces the same (422 `muitas_estruturas` / `formatos_misturados`); the client enforces them first
 * so the user never meets the refusal, and still renders it when it comes (`mensagemEstruturas`).
 */
import { dadoDoErro, codigoDoErro, mensagemEstruturas } from "@/components/geracao/biblioteca/estruturas/erros";
import type { EstruturaFormato, EstruturaResumo, PerfilCandidato } from "@/types/estruturas";

export const ESTRUTURAS_MAX = 3;

/** An Estrutura as the picker keeps it: the list row (enough for the chip and the format rule). */
export type EstruturaEscolhida = Pick<EstruturaResumo, "id" | "codigo" | "formula_headline" | "formato" | "perfil">;

export const paraEscolhida = (e: EstruturaResumo): EstruturaEscolhida => ({
  id: e.id,
  codigo: e.codigo,
  formula_headline: e.formula_headline,
  formato: e.formato,
  perfil: e.perfil,
});

/** The format the selection has locked in: the principal's (first) — null while empty or formato-less. */
export const formatoDaSelecao = (sel: readonly EstruturaEscolhida[]): EstruturaFormato | null => sel[0]?.formato ?? null;

export type MotivoBloqueio = "limite" | "formato" | null;

/** Why a candidate cannot be added to the selection (null = it can). Already-picked ones are handled by the caller. */
export function motivoDeBloqueio(sel: readonly EstruturaEscolhida[], cand: Pick<EstruturaResumo, "formato">, max = ESTRUTURAS_MAX): MotivoBloqueio {
  if (sel.length >= max) return "limite";
  const f = formatoDaSelecao(sel);
  if (f && cand.formato && cand.formato !== f) return "formato";
  return null;
}

export function alternarEstrutura(
  sel: readonly EstruturaEscolhida[],
  cand: EstruturaEscolhida,
  max = ESTRUTURAS_MAX,
): EstruturaEscolhida[] {
  if (sel.some((s) => s.id === cand.id)) return sel.filter((s) => s.id !== cand.id);
  return motivoDeBloqueio(sel, cand, max) ? [...sel] : [...sel, cand];
}

export const idsDaSelecao = (sel: readonly EstruturaEscolhida[]): string[] => sel.map((s) => s.id);

/** Candidates of a 422 `perfil_ambiguo` (flat `candidatos`), or [] for any other refusal. */
export function candidatosDoErro(e: unknown): PerfilCandidato[] {
  if (codigoDoErro(e) !== "perfil_ambiguo") return [];
  const c = dadoDoErro(e, "candidatos");
  return Array.isArray(c) ? (c as PerfilCandidato[]).filter((x) => x && typeof x.perfil_id === "string") : [];
}

/** Suggestions of a 422 `perfil_nao_encontrado_na_biblioteca`. */
export function sugestoesDoErro(e: unknown): PerfilCandidato[] {
  if (codigoDoErro(e) !== "perfil_nao_encontrado_na_biblioteca") return [];
  const c = dadoDoErro(e, "sugestoes");
  return Array.isArray(c) ? (c as PerfilCandidato[]).filter((x) => x && typeof x.perfil_id === "string") : [];
}

/** Toast/inline sentence for a refused generation: the catalogue's pt-BR text by `code`, else the server's own. */
export const mensagemDoForm = (e: unknown, fallback: string): string =>
  mensagemEstruturas(e, fallback).replace(/^\[\d+\]\s*/, "");
