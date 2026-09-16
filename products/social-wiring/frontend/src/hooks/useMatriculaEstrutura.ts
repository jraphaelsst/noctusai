/**
 * Matrícula structured acts — contract quoting + título/ônus source pointers.
 * `/api/matriculas/{extracoes,contratos}/...` (migration 109).
 *
 * 🔴 USER DECISION: THE PROPERTY DESCRIPTION IS THE LITERAL MATRÍCULA TEXT
 * --------------------------------------------------------------------------
 * Typos and all. The operator SELECTS which acts a contract quotes — never
 * edits their text. Every `texto` this file's hooks surface is rendered
 * verbatim by its consumers (`white-space: pre-wrap`); nothing here trims,
 * normalises or autocorrects a slice.
 *
 * Sibling of `useMatriculas.ts` (extraction upload/CRUD) rather than an
 * extension of it: that file owns the transcription lifecycle, this one owns
 * what a HUMAN does with a transcription once it exists — reading its acts,
 * pointing at título/ônus sources, and quoting a selection into a contract.
 * Three distinct resources (`atos`, `fontes`, contract `atos`), each with its
 * own query key family, would have made one file three unrelated sections.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@noctusai/seed/infra';

import { readableError } from '@/hooks/useMatriculas';

// ─── Types ──────────────────────────────────────────────────────────────────

export type MatriculaAtoKind = 'abertura' | 'R' | 'AV';

/** `{id, nome}` — same shape `useContratos.ts`'s `ContratoActor` and
 *  `useImovelDados.ts`'s `Ator` use for a resolved platform user. */
export interface MatriculaActor {
  id: string;
  nome: string | null;
}

/**
 * Per-field confidence (migration 115) — the seed extractor's own vocabulary
 * (`matricula_ato_detalhes.CONFIANCAS`). `alta` = the value sat next to its
 * own label; `baixa` = plausible but narrative/contested; `nenhuma` = nothing
 * usable, so the value is `null`. The UI highlights the last two: a low
 * confidence that LOOKS like a fact is exactly how a misread becomes one.
 */
export type AtoConfianca = 'alta' | 'baixa' | 'nenhuma';

/** `matricula_ato_detalhes.NATUREZAS_ATO`, same order (migration 115's CHECK
 *  mirrors it). Duplicated here because the API does not serve the vocabulary
 *  — a `natureza` the backend refuses must not be offerable. */
export const NATUREZAS_ATO = [
  'compra_e_venda',
  'doacao',
  'permuta',
  'partilha',
  'dacao',
  'arrematacao',
  'hipoteca',
  'alienacao_fiduciaria',
  'cancelamento',
  'penhora',
  'usufruto',
  'indisponibilidade',
  'construcao',
  'outro',
] as const;

export type AtoNatureza = (typeof NATUREZAS_ATO)[number];

export const NATUREZA_LABEL: Record<string, string> = {
  compra_e_venda: 'Compra e venda',
  doacao: 'Doação',
  permuta: 'Permuta',
  partilha: 'Partilha',
  dacao: 'Dação em pagamento',
  arrematacao: 'Arrematação',
  hipoteca: 'Hipoteca',
  alienacao_fiduciaria: 'Alienação fiduciária',
  cancelamento: 'Cancelamento',
  penhora: 'Penhora',
  usufruto: 'Usufruto',
  indisponibilidade: 'Indisponibilidade',
  construcao: 'Construção',
  outro: 'Outro',
};

/** A party to an act. `nome` is a literal substring of the matrícula;
 *  `cpf_cnpj` is formatted server-side when it is a valid document. */
export interface AtoParte {
  nome: string;
  cpf_cnpj: string | null;
}

/** The document the act registers (escritura, instrumento particular, formal
 *  de partilha…). `data` is an ISO date string. */
export interface AtoInstrumento {
  tipo: string | null;
  data: string | null;
  tabelionato: string | null;
  livro: string | null;
  folhas: string | null;
  cidade: string | null;
}

/** An earlier act this one cites (`R-3`, `AV-1`). */
export interface AtoReferido {
  kind: 'R' | 'AV';
  numero: number;
}

/**
 * What ONE act says (migration 115) — the typed reading of its literal text.
 *
 * 🔴 `origem` IS THE WHOLE POINT. `'sugestao'` is the extractor's reading and
 * nobody has agreed with it; `'confirmado'` means an operator did. A contract
 * clause built on an unconfirmed suggestion is a guess wearing a fact's
 * clothes, so the editor never hides which one it is showing.
 *
 * `valor` is a 2-place decimal STRING, never a float — same end-to-end money
 * rule as `types/negociacaoEstruturada.ts`.
 */
export interface MatriculaAtoDetalhes {
  id: string;
  ato_id: string;
  natureza: string | null;
  natureza_confianca: AtoConfianca;
  data_registro: string | null;
  data_registro_confianca: AtoConfianca;
  valor: string | null;
  valor_confianca: AtoConfianca;
  transmitentes: AtoParte[];
  transmitentes_confianca: AtoConfianca;
  adquirentes: AtoParte[];
  adquirentes_confianca: AtoConfianca;
  credor: string | null;
  credor_confianca: AtoConfianca;
  instrumento: AtoInstrumento | null;
  instrumento_confianca: AtoConfianca;
  atos_referidos: AtoReferido[];
  atos_referidos_confianca: AtoConfianca;
  origem: 'sugestao' | 'confirmado';
  confirmado_por: MatriculaActor | null;
  confirmado_em: string | null;
}

/**
 * `PUT /atos/{ato_id}/detalhes` body.
 *
 * 🔴 THREE DISTINCT MEANINGS, and they are not interchangeable:
 *   · key ABSENT  → keep the suggestion for that field;
 *   · key `null`  → CLEAR it (the extractor read something that is not there);
 *   · `{}` (no keys at all) → confirm every suggestion exactly as it stands.
 * So a patch must carry only the fields the operator actually changed —
 * never a full spread of the current values.
 */
export interface MatriculaAtoDetalhesPatch {
  natureza?: string | null;
  data_registro?: string | null;
  valor?: string | null;
  transmitentes?: AtoParte[] | null;
  adquirentes?: AtoParte[] | null;
  credor?: string | null;
  instrumento?: AtoInstrumento | null;
  atos_referidos?: AtoReferido[] | null;
}

export interface MatriculaAto {
  id: string;
  ordem: number;
  kind: MatriculaAtoKind;
  numero: number | null;
  char_inicio: number;
  char_fim: number;
  header_inicio: number | null;
  header_fim: number | null;
  rotulo: string;
  /** The literal matrícula text for this act. Render as-is. */
  texto: string;
  /** The act's typed reading (migration 115). `null` for the abertura, which
   *  is not an act, and for an extraction whose text was purged. */
  detalhes: MatriculaAtoDetalhes | null;
}

/** `PUT /atos/{id}/detalhes` response — the one act it confirmed. */
export interface ConfirmarDetalhesResponse {
  ato_id: string;
  extracao_id: string;
  kind: MatriculaAtoKind;
  numero: number | null;
  ato_ref: string | null;
  detalhes: MatriculaAtoDetalhes | null;
}

export interface MatriculaAtosResponse {
  extracao_id: string;
  status: string;
  codigo: string | null;
  total: number;
  /** `[]` unless `status === 'concluida'`. */
  atos: MatriculaAto[];
}

export interface MatriculaAtoRef {
  ato_id: string;
  ordem: number;
  kind: MatriculaAtoKind;
  numero: number | null;
  char_inicio: number;
  char_fim: number;
  rotulo: string;
  /** The term the heuristic matched on (e.g. "compra e venda", "hipoteca"). */
  termo: string;
}

export interface MatriculaOnusSugestao extends MatriculaAtoRef {
  tipo: string;
  /** Later cancellation acts that cite this one by number — shown so the
   *  operator sees WHY a candidate was left out, not just that it was. */
  cancelamento_citado_por: string[];
  sugerido: boolean;
}

export type MatriculaFonteOrigem = 'sugerido' | 'manual';

export interface MatriculaFonte {
  extracao_id: string;
  ato_id: string;
  char_inicio: number;
  char_fim: number;
  texto: string;
  origem: MatriculaFonteOrigem;
  confirmado_por: MatriculaActor | null;
  confirmado_em: string | null;
}

export interface MatriculaFonteOnusAto {
  ato_id: string;
  char_inicio: number;
  char_fim: number;
  texto: string;
}

export interface MatriculaFonteOnus {
  extracao_id: string;
  atos: MatriculaFonteOnusAto[];
  origem: MatriculaFonteOrigem;
  confirmado_por: MatriculaActor | null;
  confirmado_em: string | null;
}

export interface MatriculaFontesResponse {
  extracao_id: string;
  codigo: string | null;
  sugestoes: {
    titulo_aquisitivo: MatriculaAtoRef | null;
    onus: MatriculaOnusSugestao[];
  };
  titulo_aquisitivo: MatriculaFonte | null;
  onus: MatriculaFonteOnus | null;
}

export interface MatriculaFontesPatch {
  /** Absent = unchanged; `null` clears the título aquisitivo pointer. */
  titulo_aquisitivo_ato_id?: string | null;
  /** Absent = unchanged; `null`/`[]` clears the ônus pointer. */
  onus_ato_ids?: string[] | null;
}

export interface ContratoAtoSelecionado {
  ato_id: string;
  /** 1-based — contract order, not the matrícula's own `ordem`. */
  ordem: number;
  kind: MatriculaAtoKind;
  numero: number | null;
  char_inicio: number;
  char_fim: number;
  texto: string;
}

/**
 * One exchanged property's quote (migration 115) — same shape as the
 * object's, plus WHICH permuta ativo it belongs to. A deal that pays partly
 * in property describes each of those properties from its OWN matrícula, so
 * one quote per ativo is the contract's real shape, not a variant of one.
 */
export interface ContratoPermutaSelecionada {
  permuta_ativo_id: string;
  extracao_id: string | null;
  codigo: string | null;
  atos: ContratoAtoSelecionado[];
  texto: string;
  formatacao?: unknown[];
}

export interface ContratoAtosResponse {
  contrato_id: string;
  extracao_id: string | null;
  codigo: string | null;
  atos: ContratoAtoSelecionado[];
  /** Plain concatenation of the selected slices, in contract order — byte
   *  for byte `texto_extraido` when every act is selected in matrícula
   *  order. `""` when nothing is selected yet. */
  texto: string;
  /** `texto`'s own bold/underline ranges, re-based from the extraction's
   *  document-level ranges. Carried through; not consumed here. */
  formatacao?: unknown[];
  /** One entry per exchanged property quoted by this contract. `[]` when the
   *  deal has no permuta (the common case). */
  permutas: ContratoPermutaSelecionada[];
  selecionado_por: MatriculaActor | null;
  selecionado_em: string | null;
}

// ─── Keys ───────────────────────────────────────────────────────────────────

const ATOS_KEY = (extracaoId: string) => ['matricula-atos', extracaoId] as const;
const FONTES_KEY = (extracaoId: string) => ['matricula-fontes', extracaoId] as const;
const CONTRATO_ATOS_KEY = (contratoId: string) => ['contrato-atos', contratoId] as const;

// ─── Extraction acts + sources ─────────────────────────────────────────────

export function useMatriculaAtos(extracaoId?: string | null) {
  return useQuery({
    queryKey: ATOS_KEY(extracaoId || '__none__'),
    queryFn: async () => {
      const result = await api.get(`/api/matriculas/extracoes/${extracaoId}/atos`);
      return result.data as MatriculaAtosResponse;
    },
    enabled: !!extracaoId,
  });
}

export function useMatriculaFontes(extracaoId?: string | null) {
  return useQuery({
    queryKey: FONTES_KEY(extracaoId || '__none__'),
    queryFn: async () => {
      const result = await api.get(`/api/matriculas/extracoes/${extracaoId}/fontes`);
      return result.data as MatriculaFontesResponse;
    },
    enabled: !!extracaoId,
  });
}

/**
 * `PUT /extracoes/{id}/fontes` — the request itself IS the confirmation.
 * Seeds the fontes cache from the response (which already re-reads the
 * heuristic against the new pointer) rather than only invalidating, same
 * discipline as `useImovelDadosMutation`.
 */
export function useDefinirFontes(extracaoId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (patch: MatriculaFontesPatch): Promise<MatriculaFontesResponse> => {
      const result = await api.put(`/api/matriculas/extracoes/${extracaoId}/fontes`, patch);
      return result.data as MatriculaFontesResponse;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(FONTES_KEY(extracaoId), data);
      // A confirmed título/ônus pointer is also what the imóvel cartório card
      // reads (`GET /api/imoveis/{codigo}/dados`'s `titulo_aquisitivo_fonte`
      // / `onus_fonte`) — stale otherwise until the card's own refetch.
      queryClient.invalidateQueries({ queryKey: ['sw', 'imovel-dados'] });
    },
    onError: (error: Error) => {
      toast.error('Não foi possível salvar a fonte', { description: readableError(error) });
    },
  });
}

// ─── Contract quote ─────────────────────────────────────────────────────────

export function useContratoAtos(contratoId?: string | null) {
  return useQuery({
    queryKey: CONTRATO_ATOS_KEY(contratoId || '__none__'),
    queryFn: async () => {
      const result = await api.get(`/api/matriculas/contratos/${contratoId}/atos`);
      return result.data as ContratoAtosResponse;
    },
    enabled: !!contratoId,
  });
}

/** One permuta group on the way OUT — `ato_ids` must be non-empty (the
 *  backend's `min_length=1`); a group the operator emptied is simply dropped
 *  from the payload by the caller. */
export interface DefinirPermutaInput {
  permutaAtivoId: string;
  extracaoId: string;
  atoIds: string[];
}

export interface DefinirContratoAtosInput {
  /** Required when `atoIds` is non-empty — omitted (or ignored) to clear. */
  extracaoId?: string | null;
  /** In CONTRACT order. `[]` clears the whole selection. */
  atoIds: string[];
  /**
   * 🔴 THE PUT REPLACES THE WHOLE SELECTION — the object's acts AND every
   * permuta's. So this must carry every group that should SURVIVE the write,
   * not just the one being edited: omitting a group deletes its quote.
   */
  permutas?: DefinirPermutaInput[];
}

export function useDefinirContratoAtos(contratoId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (input: DefinirContratoAtosInput): Promise<ContratoAtosResponse> => {
      const result = await api.put(`/api/matriculas/contratos/${contratoId}/atos`, {
        extracao_id: input.atoIds.length > 0 ? input.extracaoId : undefined,
        ato_ids: input.atoIds,
        permutas: (input.permutas ?? []).map((p) => ({
          permuta_ativo_id: p.permutaAtivoId,
          extracao_id: p.extracaoId,
          ato_ids: p.atoIds,
        })),
      });
      return result.data as ContratoAtosResponse;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(CONTRATO_ATOS_KEY(contratoId), data);
    },
    onError: (error: Error) => {
      toast.error('Não foi possível salvar a seleção', { description: readableError(error) });
    },
  });
}

// ─── Act details (migration 115) ────────────────────────────────────────────

/**
 * `PUT /atos/{ato_id}/detalhes` — confirm one act's reading, editing any
 * subset. An empty patch confirms the suggestion as it stands.
 *
 * The response carries only the act it wrote, so the cached act LIST is
 * patched in place rather than refetched: re-reading the whole list here
 * would collapse every open editor on the page for one act's confirmation.
 * The imóvel-level reads DERIVED from these details (título phrase, ônus
 * creditor, previous owners) are invalidated instead — they are recomputed
 * server-side on every read, so they are stale the moment this lands.
 */
export function useConfirmarDetalhesAto(extracaoId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (input: {
      atoId: string;
      patch: MatriculaAtoDetalhesPatch;
    }): Promise<ConfirmarDetalhesResponse> => {
      const result = await api.put(
        `/api/matriculas/atos/${input.atoId}/detalhes`,
        input.patch,
      );
      return result.data as ConfirmarDetalhesResponse;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(
        ATOS_KEY(extracaoId),
        (atual: MatriculaAtosResponse | undefined) =>
          atual
            ? {
                ...atual,
                atos: atual.atos.map((ato) =>
                  ato.id === data.ato_id ? { ...ato, detalhes: data.detalhes } : ato,
                ),
              }
            : atual,
      );
      queryClient.invalidateQueries({ queryKey: ['sw', 'imovel-contrato'] });
    },
    onError: (error: Error) => {
      toast.error('Não foi possível confirmar os detalhes', {
        description: readableError(error),
      });
    },
  });
}
