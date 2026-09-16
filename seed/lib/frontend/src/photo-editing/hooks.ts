/**
 * Edição de Fotos — TanStack Query hook factory.
 *
 * Wraps `/api/edicao-fotos/...` per
 * `projects/edicao-fotos/EDICAO-FOTOS-CONTRACT.md`. Same shape as `../llm.ts`:
 * `api` is injected so each product's own `createApiClient()` (already
 * authenticated + backend-configured) drives every call — this module owns
 * zero fetch/auth logic of its own.
 *
 * Seed-portable by design: no Social-Wiring coupling anywhere in this file.
 * The owner's phase-2 plan rebuilds the engine in a separate app using this
 * seed feature as the code reference — these hooks travel unchanged; only
 * the `api` client passed in at call time changes.
 *
 * Loading-state contract (CLAUDE.md §1 · `KB § PATTERNS/frontend/lying-loading-state.md`,
 * binding per contract §9): every read hook below returns `showSkeleton` /
 * `isRefreshing` ALREADY COMPUTED —
 *   `showSkeleton = isPending && !data`
 *   `isRefreshing = isFetching && !!data`
 * — so consumers never touch `.isLoading`. Computed HERE (the hook), not
 * per-consumer, so every page gets the correct gate for free. Batch/review
 * queries key on `loteId`; `placeholderData` keeps a key change from
 * unmounting a grid that already has content (contract §9, last line).
 *
 * Scope: this factory covers the routes the S9 seed organs
 * (`PhotoReviewGrid` / `BeforeAfterCompare` / `ReferencePairCard`) consume —
 * capabilities, review + decisions, and the reference pool. The remaining
 * contract surface (lotes CRUD/upload/vista/zip, guias, regras, modelos,
 * curadores, painel) belongs to the SW module waves (W3-W9) that wire the
 * real backend; they extend this same factory rather than forking a new one.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ApiClient } from '../api';

// ---------------------------------------------------------------------------
// Types — mirror EDICAO-FOTOS-CONTRACT.md response/request shapes
// ---------------------------------------------------------------------------

/**
 * Contract §2 `GET /capacidades`. Server-computed; drives every FE gate.
 * NEVER derive any of these from SSO metadata — see `./permissions.ts`.
 */
export interface Capacidades {
  pode_criar_lote: boolean;
  pode_ver_veredito: boolean;
  pode_gerir_pool: boolean;
  pode_aprovar_regras: boolean;
  pode_ativar_guia: boolean;
  dashboard: 'org' | 'platform' | null;
  modelo_configurado: boolean;
  economico_disponivel: boolean;
  economico_bloqueado_motivo: string | null;
  tipos_edicao_ativos: string[];
  limites: { fotos_por_lote: number; bytes_por_foto: number };
}

/** Contract §3 — photo state machine; every transition writes `fotos_eventos`. */
export type EstadoFoto =
  | 'recebida'
  | 'normalizando'
  | 'pronta'
  | 'editando'
  | 'em_lote_openai'
  | 'editada'
  | 'avaliando'
  | 'aguardando_decisao'
  | 'aprovada'
  | 'rejeitada'
  | 'falhou';

export type DecisaoTipo = 'aprovar' | 'rejeitar';

/**
 * Contract §1 — the AI verdict. Hidden from corretores by TABLE SEPARATION
 * server-side (`fotos_avaliacoes` is its own table so RLS withholds the
 * whole row), not by field omission — a response shape that merely omits
 * this field would be a leak waiting for a refactor. `undefined` on
 * `FotoRevisao.avaliacao` means "not visible to this role", never "not yet
 * evaluated" (an unevaluated photo simply hasn't reached `aguardando_decisao`).
 */
export interface AvaliacaoIA {
  veredito: DecisaoTipo;
  /** 0-10 (contract §2 "My technical calls"). */
  score: number;
  motivo: string;
}

/**
 * One photo row from `GET /revisao/{lote_id}` (contract §4). `avaliacao` is
 * present ONLY when the caller's `capacidades.pode_ver_veredito` is true.
 */
export interface FotoRevisao {
  id: string;
  url_antes: string;
  url_depois: string | null;
  comodo?: string | null;
  estado: EstadoFoto;
  /** Present when `estado === 'falhou'` — technical failure, not a quality rejection (contract §3). */
  falha_motivo?: string | null;
  decisao: DecisaoTipo | null;
  /** Required by the backend when `decisao === 'rejeitar'` (422 otherwise — contract §4). */
  comentario: string | null;
  avaliacao?: AvaliacaoIA | null;
}

export interface DecisaoBody {
  decisao: DecisaoTipo;
  /** Required when `decisao === 'rejeitar'`; null otherwise. */
  comentario: string | null;
}

/** Contract §5 — reference pool pair (platform scope, not `org_id`-scoped). */
export interface ReferenciaPar {
  id: string;
  antes_url: string;
  depois_url: string;
  comodo: string;
  tipos_edicao: string[];
  nota: string | null;
  /** Set once archived — archived pairs are kept for history and excluded from the pair-limit count (contract §5). */
  arquivada_em?: string | null;
}

export interface NovaReferenciaBody {
  antes_url: string;
  depois_url: string;
  comodo: string;
  tipos_edicao: string[];
  nota?: string | null;
}

// ---------------------------------------------------------------------------
// Hook factory — takes an api client, returns bound hooks
// ---------------------------------------------------------------------------

export function createEdicaoFotosHooks(api: ApiClient) {
  /** `GET /capacidades` — drives every FE gate for this feature. */
  function useCapacidades() {
    const query = useQuery<Capacidades>({
      queryKey: ['edicao-fotos', 'capacidades'],
      queryFn: () => api.get('/api/edicao-fotos/capacidades'),
      staleTime: 60 * 1000,
    });
    return {
      capacidades: query.data,
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  /**
   * `GET /revisao/{lote_id}` — photos for review. Keyed on `loteId`, with
   * `placeholderData` so switching batches never unmounts the grid mid-fetch
   * (contract §9, binding).
   */
  function useRevisao(loteId: string | null | undefined) {
    const query = useQuery<FotoRevisao[]>({
      queryKey: ['edicao-fotos', 'revisao', loteId],
      queryFn: () => api.get(`/api/edicao-fotos/revisao/${loteId}`),
      enabled: !!loteId,
      placeholderData: (prev) => prev,
    });
    return {
      fotos: query.data ?? [],
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  /**
   * `POST /revisao/{lote_id}/fotos/{foto_id}/decisao` — decisions are always
   * changeable, including after the zip has been downloaded (contract §4).
   */
  function useDecidirFoto(loteId: string | null | undefined) {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: ({ fotoId, body }: { fotoId: string; body: DecisaoBody }) =>
        api.post(`/api/edicao-fotos/revisao/${loteId}/fotos/${fotoId}/decisao`, body),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['edicao-fotos', 'revisao', loteId] });
      },
    });
  }

  /**
   * `POST /lotes/{id}/fotos/{foto_id}/retentar` — manual retry of a
   * `falhou` photo (technical failure, contract §3).
   */
  function useRetentarFoto(loteId: string | null | undefined) {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (fotoId: string) =>
        api.post(`/api/edicao-fotos/lotes/${loteId}/fotos/${fotoId}/retentar`, {}),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['edicao-fotos', 'revisao', loteId] });
      },
    });
  }

  /** `GET /referencias` — platform-scope reference pool (contract §5). */
  function useReferencias() {
    const query = useQuery<ReferenciaPar[]>({
      queryKey: ['edicao-fotos', 'referencias'],
      queryFn: () => api.get('/api/edicao-fotos/referencias'),
      staleTime: 30 * 1000,
    });
    return {
      referencias: query.data ?? [],
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  /** `POST /referencias` — 409 `pool_cheio` when the pair limit is reached (contract §5). */
  function useCriarReferencia() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (body: NovaReferenciaBody) => api.post('/api/edicao-fotos/referencias', body),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['edicao-fotos', 'referencias'] });
      },
    });
  }

  /** `DELETE /referencias/{id}` — archive, never a hard delete (contract §5). */
  function useArquivarReferencia() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (id: string) => api.delete(`/api/edicao-fotos/referencias/${id}`),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['edicao-fotos', 'referencias'] });
      },
    });
  }

  return {
    useCapacidades,
    useRevisao,
    useDecidirFoto,
    useRetentarFoto,
    useReferencias,
    useCriarReferencia,
    useArquivarReferencia,
  };
}

export type EdicaoFotosHooks = ReturnType<typeof createEdicaoFotosHooks>;
