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

export interface ContratoAtosResponse {
  contrato_id: string;
  extracao_id: string | null;
  codigo: string | null;
  atos: ContratoAtoSelecionado[];
  /** Plain concatenation of the selected slices, in contract order — byte
   *  for byte `texto_extraido` when every act is selected in matrícula
   *  order. `""` when nothing is selected yet. */
  texto: string;
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

export interface DefinirContratoAtosInput {
  /** Required when `atoIds` is non-empty — omitted (or ignored) to clear. */
  extracaoId?: string | null;
  /** In CONTRACT order. `[]` clears the whole selection. */
  atoIds: string[];
}

export function useDefinirContratoAtos(contratoId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (input: DefinirContratoAtosInput): Promise<ContratoAtosResponse> => {
      const result = await api.put(`/api/matriculas/contratos/${contratoId}/atos`, {
        extracao_id: input.atoIds.length > 0 ? input.extracaoId : undefined,
        ato_ids: input.atoIds,
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
