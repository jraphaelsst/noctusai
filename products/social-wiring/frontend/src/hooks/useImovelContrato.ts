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
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";

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
  | "sem_credor"
  | "matricula_removida";

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
  matricula_removida:
    "A matrícula do título aquisitivo confirmado foi removida — escolha outra.",
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

export type TituloFato =
  | "data"
  | "registro"
  | "tipo"
  | "livro"
  | "folhas"
  | "tabelionato"
  | "cidade"
  | "natureza";

/** One título fact where the confirmed text and the matrícula act disagree. */
export interface TituloDivergencia {
  fato: TituloFato;
  /** What the confirmed text says. */
  atual: string | null;
  /** What the matrícula act says. */
  sugerido: string | null;
}

export const TITULO_FATO_LABEL: Record<TituloFato, string> = {
  data: "Data",
  registro: "Registro",
  tipo: "Tipo do instrumento",
  livro: "Livro",
  folhas: "Folhas",
  tabelionato: "Tabelionato",
  cidade: "Cidade",
  natureza: "Natureza",
};

export interface TituloAquisitivoResponse {
  codigo: string;
  /** `null` until an ato is confirmed as the título source. */
  ato: AtoReferencia | null;
  /** The rendered phrase, recomputed on every read. `null` with a reason. */
  sugestao: string | null;
  motivo_sem_sugestao: MotivoSemSugestao | null;
  /** The backend's own pendência sentence (set for `matricula_removida`);
   *  absent/null otherwise and on older backends. */
  mensagem_pendencia?: string | null;
  confirmado: ConfirmacaoTexto | null;
  /** Per-fact disagreements; absent on older backends. */
  divergencias?: TituloDivergencia[];
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

/** [Q9] `titulo_service.NATUREZAS_ULTIMA_TRANSFERENCIA` — every transmissão
 *  of propriedade counts as "the imóvel changed hands" (owner 2026-10-22: a
 *  doação is the last transfer too; its antigos proprietários are the
 *  doadores). */
export type NaturezaUltimaTransferencia =
  | "compra_e_venda"
  | "doacao"
  | "permuta"
  | "partilha"
  | "dacao"
  | "arrematacao"
  | "adjudicacao"
  | "integralizacao";

export const NATUREZA_ULTIMA_TRANSFERENCIA_LABEL: Record<NaturezaUltimaTransferencia, string> = {
  compra_e_venda: "Compra e venda",
  doacao: "Doação",
  permuta: "Permuta",
  partilha: "Partilha / herança",
  dacao: "Dação em pagamento",
  arrematacao: "Arrematação",
  adjudicacao: "Adjudicação",
  integralizacao: "Integralização de capital",
};

export interface UltimaTransferencia {
  /** `null` for a manual override (migration 152) — there is no act. */
  ato_id: string | null;
  ato_ref: string | null;
  natureza: string | null;
  /** ISO date, or `null` when the act's date could not be read. */
  data_registro: string | null;
  detalhes_origem: "sugestao" | "confirmado" | "manual" | null;
}

/** `GET/PUT .../endereco-registro` (migration 139/147) — the operator's
 *  confirmed short address the posse clauses print. 🔴 NO `sugestao` field
 *  here, unlike título/ônus: this value is NEVER a recomputed guess. */
export interface EnderecoRegistroResponse {
  codigo: string;
  confirmado: ConfirmacaoTexto | null;
}

/** `GET/PUT .../descricao-imovel` (migration 306) — the IMÓVEL: description
 *  the contract's OBJETO clause quotes. `derivado` is the matrícula abertura's
 *  own block; `confirmado` is what an operator typed, which WINS in the
 *  contract and is never replaced by a later transcription. */
export interface DescricaoImovelResponse {
  codigo: string;
  derivado: string | null;
  confirmado: ConfirmacaoTexto | null;
  efetivo: string | null;
  origem: "manual" | "matricula" | null;
}

/** The RAW manual-override state (migration 152) — reported even when a
 *  derivation from the matrícula's acts is the EFFECTIVE source, so the
 *  property page's form can show/edit it either way. `null` = never set. */
export interface UltimaTransferenciaManual {
  data_registro: string | null;
  natureza: string | null;
  sem_registro: boolean;
  /** Migration 306 — who sold, typed (names only). */
  transmitentes?: string[];
  confirmado_por: MatriculaActor | null;
  confirmado_em: string | null;
}

export interface AntigosProprietariosResponse {
  codigo: string;
  extracao_id: string | null;
  ultima_transferencia: UltimaTransferencia | null;
  transmitentes: AtoParte[];
  /**
   * 🔴 OFFICE RULE: the sellers' certidões are required when the last
   * registered transfer is LESS than five years old — AND when its date
   * could not be read at all (`data_desconhecida`), because an unreadable
   * date must lead to asking, never to silently waiving.
   */
  exige_certidoes: boolean;
  data_desconhecida: boolean;
  /** [migration 152] A human confirmed there is NO registered transfer at
   *  all ("não consta transferência registrada") — an ANSWER, resolving
   *  `exige_certidoes` to `false` instead of leaving it unknown. */
  sem_registro: boolean;
  /** Where `ultima_transferencia` came from, or why `sem_registro` fired:
   *  the confirmed título act, a scan of the extraction's other acts, or
   *  the manual override. `null` when nothing resolved it at all. */
  origem: "titulo_confirmado" | "extracao" | "manual" | null;
  /** Migration 306 — who answered `transmitentes`: the act, or names an
   *  operator typed (which win). `null` when nobody is known. */
  transmitentes_origem?: "matricula" | "manual" | null;
  manual: UltimaTransferenciaManual | null;
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
  /** `null` for a certidão typed with no file (migration 306). */
  documento_id: string | null;
  numero: string | null;
  emitida_em: string | null;
  validade_ate: string | null;
  resultado: CertidaoResultado | null;
  inscricao_imobiliaria: string | null;
  /** True once an operator confirmed the read (`origem = 'manual'`). */
  confirmado: boolean;
  /** Migration 306 — typed with no file (`documento_id` is then `null`). */
  sem_arquivo?: boolean;
  manual_id?: string | null;
}

/** `GET /{codigo}/certidoes` envelope (`/api/imoveis/...` — no `data`). */
export interface ImovelCertidoesResponse {
  items: ImovelCertidao[];
  total: number;
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
const ENDERECO_REGISTRO_KEY = (codigo: string) =>
  [...FAMILY_KEY(codigo), "endereco-registro"] as const;
const ONUS_KEY = (codigo: string) => [...FAMILY_KEY(codigo), "onus-credor"] as const;
const ANTIGOS_KEY = (codigo: string) =>
  [...FAMILY_KEY(codigo), "antigos-proprietarios"] as const;
const CERTIDOES_KEY = (codigo: string) => [...FAMILY_KEY(codigo), "certidoes"] as const;
const DESCRICAO_KEY = (codigo: string) =>
  [...FAMILY_KEY(codigo), "descricao-imovel"] as const;

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

export function useEnderecoRegistro(codigo: string | null) {
  return useQuery({
    queryKey: ENDERECO_REGISTRO_KEY(codigo ?? "__none__"),
    queryFn: async () => {
      const result = await api.get(`${matriculasBase(codigo as string)}/endereco-registro`);
      return result.data as EnderecoRegistroResponse;
    },
    enabled: !!codigo,
  });
}

export function useDescricaoImovel(codigo: string | null) {
  return useQuery({
    queryKey: DESCRICAO_KEY(codigo ?? "__none__"),
    queryFn: async () => {
      const result = await api.get(`${matriculasBase(codigo as string)}/descricao-imovel`);
      return result.data as DescricaoImovelResponse;
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
      const res = await api.get<ImovelCertidoesResponse>(
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

/** `PUT .../endereco-registro` — `texto: null` clears the confirmation. */
export function useConfirmarEnderecoRegistro(codigo: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (texto: string | null): Promise<EnderecoRegistroResponse> => {
      const result = await api.put(`${matriculasBase(codigo)}/endereco-registro`, {
        texto,
      });
      return result.data as EnderecoRegistroResponse;
    },
    onSuccess: (data) => qc.setQueryData(ENDERECO_REGISTRO_KEY(codigo), data),
    onError: (error: Error) => {
      toast.error("Não foi possível salvar o endereço do registro", {
        description: readableError(error),
      });
    },
  });
}

/** `PUT .../descricao-imovel` (migration 306) — `texto: null` clears the
 *  typed override (the matrícula's own block answers again). The PUT
 *  re-reads and returns the whole shape, which is committed to the cache. */
export function useConfirmarDescricaoImovel(codigo: string) {
  return useCacheWriteMutation<DescricaoImovelResponse, string | null>({
    mutationFn: async (texto) => {
      const result = await api.put(`${matriculasBase(codigo)}/descricao-imovel`, { texto });
      return result.data as DescricaoImovelResponse;
    },
    targets: [{ queryKey: DESCRICAO_KEY(codigo), commit: (_old, data) => data }],
    onError: (error: Error) => {
      toast.error("Não foi possível salvar a descrição do imóvel", {
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
 * `PUT .../ultima-transferencia` (migration 152) — the manual fallback for
 * [Q9]'s previous-owner rule, always available next to "Antigos
 * proprietários": a typed date (+ optional nature), or `semRegistro: true`
 * alone ("não consta transferência registrada"). Mutually exclusive — the
 * backend refuses both set.
 */
export function useConfirmarUltimaTransferenciaManual(codigo: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      data: string | null;
      natureza: NaturezaUltimaTransferencia | null;
      semRegistro: boolean;
      /** Migration 306 — who sold, typed. The PUT is a full replace. */
      transmitentes?: string[];
    }): Promise<AntigosProprietariosResponse> => {
      const result = await api.put(`${matriculasBase(codigo)}/ultima-transferencia`, {
        data: input.data,
        natureza: input.natureza,
        sem_registro: input.semRegistro,
        transmitentes: input.transmitentes ?? [],
      });
      return result.data as AntigosProprietariosResponse;
    },
    // The PUT re-reads and returns the whole shape (same as `antigos-
    // proprietarios`), so seed rather than invalidate.
    onSuccess: (data) => qc.setQueryData(ANTIGOS_KEY(codigo), data),
    onError: (error: Error) => {
      toast.error("Não foi possível salvar a última transferência", {
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
  return useMutation({ // noc-allow: invalidate-only — the PATCH answer is untyped and the confirmed read fans out across certidões and imovel-dados (suggested cadastro/ônus fields), not one cached row
    // `codigo` = the document's OWN código (a linked imóvel lists the manual
    // record's certidões; the route is per-imóvel).
    mutationFn: (input: {
      documentoId: string;
      patch: DocumentoExtracaoPatch;
      codigo?: string | null;
    }) =>
      api.patch(
        `${imoveisBase(input.codigo || codigo)}/documentos/${encodeURIComponent(input.documentoId)}/extracao`,
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

/**
 * `PUT .../certidoes/{tipo}/manual` (migration 306) — type a certidão's
 * fields with NO file. A FULL replace of the typed record (send every field
 * the tipo carries; `null` = empty). The server answers the refreshed
 * certidões read, which is committed to the cache — the typed values are on
 * screen after one round trip.
 */
export function useSalvarCertidaoManual(codigo: string) {
  return useCacheWriteMutation<
    ImovelCertidoesResponse,
    { tipo: string; valores: DocumentoExtracaoPatch }
  >({
    mutationFn: ({ tipo, valores }) =>
      api.put<ImovelCertidoesResponse>(
        `${imoveisBase(codigo)}/certidoes/${encodeURIComponent(tipo)}/manual`,
        valores,
      ),
    targets: [{ queryKey: CERTIDOES_KEY(codigo), commit: (_old, res) => res?.items ?? [] }],
    onError: (error: Error) => {
      toast.error("Não foi possível salvar a certidão", {
        description: readableError(error),
      });
    },
  });
}

/** `DELETE .../certidoes/{tipo}/manual` — drop the typed record; the newest
 *  uploaded document of that tipo (if any) answers again. */
export function useRemoverCertidaoManual(codigo: string) {
  return useCacheWriteMutation<ImovelCertidoesResponse, { tipo: string }>({
    mutationFn: ({ tipo }) =>
      api.delete<ImovelCertidoesResponse>(
        `${imoveisBase(codigo)}/certidoes/${encodeURIComponent(tipo)}/manual`,
      ),
    targets: [
      {
        queryKey: CERTIDOES_KEY(codigo),
        optimistic: (old: ImovelCertidao[] | undefined, { tipo }) =>
          old?.filter((c) => !(c.tipo === tipo && c.sem_arquivo)),
        commit: (_old, res) => res?.items ?? [],
      },
    ],
    onError: (error: Error) => {
      toast.error("Não foi possível remover a certidão informada", {
        description: readableError(error),
      });
    },
  });
}
