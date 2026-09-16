/**
 * What a contract asks of an imóvel's matrícula and certidões — the operator
 * review surface for migrations 115 (título phrase, ônus creditor, previous
 * owners) and 118 (the imóvel CND group).
 *
 * 🔴 A SUGGESTION IS NEVER THE ANSWER. Every read here returns BOTH the
 * server's freshly-recomputed `sugestao` AND the operator's `confirmado`
 * wording, and they are allowed to differ — the contract uses the confirmed
 * one. That is why nothing in this file "helpfully" falls back from one to
 * the other: a clause built on an unreviewed reading is a guess nobody
 * agreed to, and collapsing the two would make that invisible.
 *
 * 🔴 TWO ENVELOPES, ON PURPOSE. The `/api/matriculas/...` routes answer
 * `{data: ...}` (`app/responses.success_response`) while `/api/imoveis/...`
 * answers the object directly — the same split `useMatriculaEstrutura.ts`
 * and `useImovelDados.ts` already live with. Unwrapping happens here, per
 * route, rather than in a shared helper that would have to guess which shape
 * it was handed.
 *
 * Separate file from `useImovelDados.ts` (the cartório fields + document
 * store): these reads are readings OF a matrícula, served by the matrículas
 * module, and they invalidate on act-detail confirmation — a different
 * lifecycle from the row a human types into the cartório card.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@noctusai/seed/infra";

import type { AtoConfianca, AtoParte, MatriculaActor } from "@/hooks/useMatriculaEstrutura";
import { readableError } from "@/hooks/useMatriculas";

// ─── Types ──────────────────────────────────────────────────────────────────

/**
 * Why a GET has no suggestion — the backend's own machine-readable reasons
 * (`titulo_service.MOTIVO_*`). Each one has a DIFFERENT fix, which is the
 * entire reason it is a code and not a blank field.
 */
export type MotivoSemSugestao =
  | "sem_titulo_confirmado"
  | "sem_onus_confirmado"
  | "sem_detalhes"
  | "sem_instrumento"
  | "sem_credor";

/**
 * What to tell the operator, and what to DO about it, per reason. Keyed by
 * the wire value so an unknown future reason falls through to a generic
 * sentence instead of rendering blank (same posture as `rotuloTipo`).
 */
export const MOTIVO_SEM_SUGESTAO_TEXTO: Record<string, string> = {
  sem_titulo_confirmado:
    "Nenhum ato foi confirmado como título aquisitivo desta matrícula. Confirme qual ato transferiu a propriedade em Matrículas → Fontes.",
  sem_onus_confirmado:
    "Nenhum ato de ônus foi confirmado nesta matrícula. Confirme os atos de ônus em Matrículas → Fontes.",
  sem_detalhes:
    "O ato do título aquisitivo ainda não foi lido. Abra a matrícula e confirme os detalhes do ato.",
  sem_instrumento:
    "O ato do título aquisitivo não informa o instrumento (escritura, livro, folhas). Complete o instrumento nos detalhes do ato para gerar a frase.",
  sem_credor:
    "Os atos de ônus confirmados não informam o credor. Preencha o credor nos detalhes do ato.",
};

export function motivoSemSugestaoTexto(motivo: string | null): string | null {
  if (!motivo) return null;
  return (
    MOTIVO_SEM_SUGESTAO_TEXTO[motivo] ??
    "Não há sugestão disponível para este campo — confirme o valor manualmente."
  );
}

/** The act a suggestion was read from — enough to link to it. */
export interface AtoReferencia {
  extracao_id: string;
  ato_id: string;
  kind: "abertura" | "R" | "AV";
  numero: number | null;
  ato_ref: string | null;
  detalhes_origem: "sugestao" | "confirmado" | null;
}

/** A confirmed free-text value + who agreed to it. */
export interface ConfirmacaoTexto {
  texto: string;
  confirmado_por: MatriculaActor | null;
  confirmado_em: string | null;
}

export interface TituloAquisitivoResponse {
  codigo: string;
  /** `null` until an ato is confirmed as the título source. */
  ato: AtoReferencia | null;
  /** The rendered phrase, recomputed on every read. `null` with a reason. */
  sugestao: string | null;
  motivo_sem_sugestao: MotivoSemSugestao | null;
  confirmado: ConfirmacaoTexto | null;
}

export interface OnusCredorAto {
  ato_id: string;
  kind: "abertura" | "R" | "AV";
  numero: number | null;
  ato_ref: string | null;
  natureza: string | null;
  credor: string | null;
  credor_confianca: AtoConfianca;
  detalhes_origem: "sugestao" | "confirmado" | null;
}

export interface ConfirmacaoCredor {
  credor: string;
  confirmado_por: MatriculaActor | null;
  confirmado_em: string | null;
}

export interface OnusCredorResponse {
  codigo: string;
  extracao_id: string | null;
  atos: OnusCredorAto[];
  /** Every distinct creditor found, joined by `; `. */
  sugestao: string | null;
  motivo_sem_sugestao: MotivoSemSugestao | null;
  confirmado: ConfirmacaoCredor | null;
}

export interface UltimaTransferencia {
  ato_id: string;
  ato_ref: string | null;
  /** ISO date, or `null` when the act's date could not be read. */
  data_registro: string | null;
  detalhes_origem: "sugestao" | "confirmado" | null;
}

export interface AntigosProprietariosResponse {
  codigo: string;
  extracao_id: string | null;
  ultima_transferencia: UltimaTransferencia | null;
  transmitentes: AtoParte[];
  /**
   * 🔴 OFFICE RULE: the sellers' certidões are required when the last
   * registered sale is LESS than five years old — AND when its date could not
   * be read at all (`data_desconhecida`), because an unreadable date must
   * lead to asking, never to silently waiving.
   */
  exige_certidoes: boolean;
  data_desconhecida: boolean;
}

export type CertidaoResultado =
  | "negativa"
  | "positiva"
  | "positiva_com_efeito_de_negativa";

export const RESULTADO_LABEL: Record<string, string> = {
  negativa: "Negativa",
  positiva: "Positiva",
  positiva_com_efeito_de_negativa: "Positiva com efeito de negativa",
};

/** One tipo's latest structured read (`GET /{codigo}/certidoes`). */
export interface ImovelCertidao {
  tipo: string;
  documento_id: string;
  numero: string | null;
  emitida_em: string | null;
  validade_ate: string | null;
  resultado: CertidaoResultado | null;
  inscricao_imobiliaria: string | null;
  /** True once an operator confirmed the read (`origem = 'manual'`). */
  confirmado: boolean;
}

/**
 * `PATCH .../documentos/{id}/extracao` body — the same three meanings as the
 * act-detail patch: absent = keep, `null` = clear, `{}` = confirm as-is.
 * The backend 400s any field this `tipo_documento` does not carry, so a
 * caller must send only the fields the tipo actually has
 * (`CAMPOS_ESTRUTURA_POR_TIPO`).
 */
export interface DocumentoExtracaoPatch {
  numero?: string | null;
  emitida_em?: string | null;
  validade_ate?: string | null;
  resultado?: CertidaoResultado | null;
  inscricao_imobiliaria?: string | null;
}

/**
 * Which structured fields each tipo carries — mirrors
 * `documentos_service.CAMPOS_ESTRUTURA_POR_TIPO`. Duplicated on purpose: the
 * API does not serve this map, and offering a field the backend refuses
 * turns a review screen into a 400 the operator cannot act on.
 */
export const CAMPOS_POR_TIPO: Record<string, readonly (keyof DocumentoExtracaoPatch)[]> = {
  cnd_iptu: ["numero", "emitida_em", "validade_ate", "resultado", "inscricao_imobiliaria"],
  cnd_condominio: ["emitida_em", "resultado"],
  guia_iptu: ["inscricao_imobiliaria"],
  matricula: ["emitida_em"],
};

// ─── Office rule: a certidão older than 30 days ─────────────────────────────

/**
 * 🔴 OFFICE RULE: a certidão must be LESS than 30 days old at signing. The
 * warning is a warning, never a refusal — the same posture the situação-de-
 * ônus fields take (`useImovelDados`): the policy of what to do about a stale
 * certidão is the user's, and a gate written before its policy gets worked
 * around.
 */
export const CERTIDAO_MAX_DIAS = 30;

/**
 * 🔴 OFFICE RULE: the previous owners' certidões are required while the last
 * registered sale is LESS than this many years old. Mirrors
 * `titulo_service.ANOS_CERTIDOES_ANTIGOS_PROPRIETARIOS` — the FE only STATES
 * the rule in words; `exige_certidoes` is computed server-side, so the two
 * can never disagree about a given imóvel.
 */
export const ANOS_CERTIDOES_ANTIGOS_PROPRIETARIOS = 5;

function diaUtc(d: Date): number {
  return Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
}

/**
 * Whole days between a certidão's printed emission date and today.
 *
 * 🔴 TWO DIFFERENT KINDS OF "DATE", RECONCILED DELIBERATELY. `emitida_em` is
 * a calendar date with NO time zone, so it is read at UTC midnight — parsing
 * it as local time would make it land on the previous day west of Greenwich,
 * a one-day error falling exactly on the 30-day boundary this feeds. "Today"
 * is the opposite case: it is an instant, and what the office counts is the
 * LOCAL calendar day it falls in, so its local y/m/d is what gets compared.
 * Every instant within one local day therefore yields the same answer.
 */
export function diasDesdeEmissao(
  emitidaEm: string | null | undefined,
  hoje: Date = new Date(),
): number | null {
  if (!emitidaEm) return null;
  const emitida = Date.parse(`${emitidaEm.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(emitida)) return null;
  return Math.floor((diaUtc(hoje) - emitida) / 86_400_000);
}

/** True when the certidão is 30+ days old — the office's signing threshold. */
export function certidaoDesatualizada(
  emitidaEm: string | null | undefined,
  hoje: Date = new Date(),
): boolean {
  const dias = diasDesdeEmissao(emitidaEm, hoje);
  return dias !== null && dias >= CERTIDAO_MAX_DIAS;
}

// ─── Query keys ─────────────────────────────────────────────────────────────

/** 🔴 The prefix `useConfirmarDetalhesAto` invalidates — every read in this
 *  family is DERIVED from act details, so confirming one act makes all of
 *  them stale at once. */
const FAMILY_KEY = (codigo: string) => ["sw", "imovel-contrato", codigo] as const;
const TITULO_KEY = (codigo: string) => [...FAMILY_KEY(codigo), "titulo"] as const;
const ONUS_KEY = (codigo: string) => [...FAMILY_KEY(codigo), "onus-credor"] as const;
const ANTIGOS_KEY = (codigo: string) =>
  [...FAMILY_KEY(codigo), "antigos-proprietarios"] as const;
const CERTIDOES_KEY = (codigo: string) => [...FAMILY_KEY(codigo), "certidoes"] as const;

const matriculasBase = (codigo: string) =>
  `/api/matriculas/imoveis/${encodeURIComponent(codigo)}`;
const imoveisBase = (codigo: string) => `/api/imoveis/${encodeURIComponent(codigo)}`;

// ─── Queries ────────────────────────────────────────────────────────────────

export function useTituloAquisitivo(codigo: string | null) {
  return useQuery({
    queryKey: TITULO_KEY(codigo ?? "__none__"),
    queryFn: async () => {
      const result = await api.get(`${matriculasBase(codigo as string)}/titulo-aquisitivo`);
      return result.data as TituloAquisitivoResponse;
    },
    enabled: !!codigo,
  });
}

export function useOnusCredor(codigo: string | null) {
  return useQuery({
    queryKey: ONUS_KEY(codigo ?? "__none__"),
    queryFn: async () => {
      const result = await api.get(`${matriculasBase(codigo as string)}/onus-credor`);
      return result.data as OnusCredorResponse;
    },
    enabled: !!codigo,
  });
}

export function useAntigosProprietarios(codigo: string | null) {
  return useQuery({
    queryKey: ANTIGOS_KEY(codigo ?? "__none__"),
    queryFn: async () => {
      const result = await api.get(
        `${matriculasBase(codigo as string)}/antigos-proprietarios`,
      );
      return result.data as AntigosProprietariosResponse;
    },
    enabled: !!codigo,
  });
}

export function useImovelCertidoes(codigo: string | null) {
  return useQuery({
    queryKey: CERTIDOES_KEY(codigo ?? "__none__"),
    queryFn: async () => {
      // `/api/imoveis/...` answers `{items, total}` directly — no `data`.
      const res = await api.get<{ items: ImovelCertidao[]; total: number }>(
        `${imoveisBase(codigo as string)}/certidoes`,
      );
      return res?.items ?? [];
    },
    enabled: !!codigo,
  });
}

// ─── Mutations ──────────────────────────────────────────────────────────────

/** `PUT .../titulo-aquisitivo` — `texto: null` clears the confirmation. */
export function useConfirmarTitulo(codigo: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (texto: string | null): Promise<TituloAquisitivoResponse> => {
      const result = await api.put(`${matriculasBase(codigo)}/titulo-aquisitivo`, {
        texto,
      });
      return result.data as TituloAquisitivoResponse;
    },
    // The PUT re-reads and returns the whole shape, so seed rather than
    // invalidate — the phrase on screen is the one the server just stored.
    onSuccess: (data) => qc.setQueryData(TITULO_KEY(codigo), data),
    onError: (error: Error) => {
      toast.error("Não foi possível salvar o título aquisitivo", {
        description: readableError(error),
      });
    },
  });
}

/** `PUT .../onus-credor` — `credor: null` clears the confirmation. */
export function useConfirmarOnusCredor(codigo: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (credor: string | null): Promise<OnusCredorResponse> => {
      const result = await api.put(`${matriculasBase(codigo)}/onus-credor`, { credor });
      return result.data as OnusCredorResponse;
    },
    onSuccess: (data) => qc.setQueryData(ONUS_KEY(codigo), data),
    onError: (error: Error) => {
      toast.error("Não foi possível salvar o credor do ônus", {
        description: readableError(error),
      });
    },
  });
}

/**
 * `PATCH .../documentos/{id}/extracao` — confirm or correct one document's
 * structured read. An empty patch is a valid confirmation.
 *
 * Invalidates the certidões group AND the `imovel-dados` family: the read
 * can suggest `prefeitura_cadastro_imobiliario` / `onus_certidao_em` into the
 * cartório card, and the document list carries the same fields.
 */
export function useConfirmarDocumentoExtracao(codigo: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { documentoId: string; patch: DocumentoExtracaoPatch }) =>
      api.patch(
        `${imoveisBase(codigo)}/documentos/${encodeURIComponent(input.documentoId)}/extracao`,
        input.patch,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CERTIDOES_KEY(codigo) });
      qc.invalidateQueries({ queryKey: ["sw", "imovel-dados", codigo] });
    },
    onError: (error: Error) => {
      toast.error("Não foi possível confirmar a certidão", {
        description: readableError(error),
      });
    },
  });
}
