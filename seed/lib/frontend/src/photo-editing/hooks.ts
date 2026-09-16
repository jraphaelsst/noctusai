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
 * Scope: originally just the S9 seed organs' routes (capacidades, review +
 * decisions, reference pool). W10a (SW frontend, `pages/edicao-fotos/`)
 * extended this SAME factory with lotes CRUD/upload/vista/submeter/zip and
 * configurações/modelos — per `CLAUDE.md` §1 "products consume canonical
 * organs" this is the required shape (extend, never fork). W6 extended it
 * again with the reference-pool upload (multipart), guias de estilo and the
 * platform settings the pool limit lives in. Regras, curadores and painel
 * remain out of scope — they belong to later admin slices (plan §7 W10c-e)
 * and extend this factory in turn when built.
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
  /** Short-lived signed URL (the pool bucket is private). */
  antes_url: string;
  /** Short-lived signed URL (the pool bucket is private). */
  depois_url: string;
  comodo: string;
  tipos_edicao: string[];
  nota: string | null;
  /** Set once archived — archived pairs are kept for history and excluded from the pair-limit count (contract §5). */
  arquivada_em?: string | null;
  criado_em?: string | null;
  criado_por?: string | null;
}

/**
 * `POST /referencias` — multipart: the two image FILES plus the tags
 * (contract §5). Sent via `api.upload`, never `api.post` (FormData through
 * `post` silently becomes `{}` — see `../api.ts`).
 */
export interface NovaReferenciaBody {
  antes: File;
  depois: File;
  /** One of `ReferenciasPage.opcoes.comodos` (fixed list). */
  comodo: string;
  /** Subset of `ReferenciasPage.opcoes.tipos_edicao`. */
  tipos_edicao: string[];
  nota?: string | null;
}

/** Pool occupancy — the limit is counted in PAIRS; `limite_pares: null` = unlimited (contract §5). */
export interface PoolReferencias {
  pares_ativos: number;
  limite_pares: number | null;
  /** `true` ⇒ uploads are refused with 409 `pool_cheio` until a pair is archived or the limit raised. */
  cheio: boolean;
}

/** `GET /referencias` — paginated pairs + pool occupancy + the fixed upload vocabularies. */
export interface ReferenciasPage {
  items: ReferenciaPar[];
  page: number;
  page_size: number;
  total: number;
  pool: PoolReferencias;
  opcoes: { comodos: string[]; tipos_edicao: string[] };
}

/** Contract §6 — style-guide version lifecycle. */
export type GuiaStatus = 'rascunho' | 'ativa' | 'substituida';

/** How a version came to be: AI builder, hand-written, or a restore (clone of an older version). */
export type GuiaOrigem = 'ia' | 'manual' | 'restaurada';

/** One company style-guide version (contract §6). Versions are immutable. */
export interface GuiaEstiloVersao {
  id: string;
  versao: number;
  status: GuiaStatus;
  texto: string;
  sha256: string;
  gerado_de_versao: number | null;
  origem: GuiaOrigem;
  criado_por: string | null;
  criado_em: string | null;
  ativado_por: string | null;
  ativado_em: string | null;
}

/** `GET /guias` — versions newest first + the active version number (null = none active ⇒ batches cannot be submitted). */
export interface GuiasPage {
  items: GuiaEstiloVersao[];
  page: number;
  page_size: number;
  total: number;
  versao_ativa: number | null;
}

/** `POST /guias` — a manually written DRAFT (activation is a separate call). */
export interface NovoGuiaBody {
  texto: string;
}

/** `POST /guias/regenerar` → 202: the AI rebuild was queued; the draft shows up in `GET /guias` once it runs. */
export interface RegenerarGuiaResposta {
  job_id: string;
  status: string;
}

/** `GET|PUT /configuracoes/plataforma` (contract §8) — platform admin only. */
export interface PlataformaConfiguracoes {
  velocidade_default: LoteVelocidade;
  notificacoes_globais_ativas: boolean;
  /** Decimal as string (USD per GB-month); null = not configured. */
  preco_storage_gb_mes_usd: string | null;
  /** Reference-pool limit in pairs; null (or 0 on write) = unlimited. */
  limite_pares_referencia: number | null;
}

/** Contract §3 — speed mode (Urgente = sync; Econômico = Batch API, 50% off, ≤24h). */
export type LoteVelocidade = 'urgente' | 'economico';

/** Optional link to a Vista/CRM imóvel carried on a batch (contract §3 `POST /lotes` body). */
export interface LoteImovelRef {
  org_id: string;
  codigo: string;
}

/**
 * Aggregate batch status for the list view. NOT literally typed by the
 * contract (§3 lists routes, not the list-row shape) — inferred from the
 * per-photo state machine. 🔴 FLAG: the backend (built in parallel) may
 * compute + return a differently-named/shaped field — if `GET /lotes` ships
 * something else, update this type + `Lotes.tsx`'s badge mapping together.
 */
export type EstadoLoteAgregado = 'rascunho' | 'processando' | 'aguardando_revisao' | 'concluido' | 'com_falhas';

/** One row from `GET /lotes` (contract §3) — batch list. */
export interface LoteResumo {
  id: string;
  nome: string;
  criado_em: string;
  imovel: LoteImovelRef | null;
  velocidade: LoteVelocidade;
  estado_agregado: EstadoLoteAgregado;
  total_fotos: number;
  fotos_decididas: number;
}

/** Paginated envelope — contract §0 convention (`?page=&page_size=` → `{items,page,page_size,total}`). */
export interface LotesPage {
  items: LoteResumo[];
  page: number;
  page_size: number;
  total: number;
}

/** `POST /lotes` body (contract §3) — metadata only; photos follow via upload or Vista pull. */
export interface NovoLoteBody {
  nome: string;
  imovel: LoteImovelRef | null;
}

/** `POST /lotes` response — minimal id so the caller can chain upload/vista/submeter. */
export interface LoteCriado {
  id: string;
  nome: string;
}

/**
 * `POST /lotes/{id}/vista` body (contract §10, C5 resolved) — `codigo` only;
 * `org_id` is resolved server-side from the session, never sent by the FE.
 */
export interface VistaLoteBody {
  codigo: string;
}

/** `GET /lotes/{id}` (contract §3) — batch header + per-photo state, reusing `FotoRevisao`. */
export interface LoteDetalhe {
  id: string;
  nome: string;
  velocidade: LoteVelocidade;
  imovel: LoteImovelRef | null;
  criado_em: string;
  fotos: FotoRevisao[];
}

/** `GET|PUT /configuracoes` (contract §8) — org edit types, image model, speed override. */
export interface OrgConfiguracoes {
  tipos_edicao_ativos: string[];
  modelo_editor_imagem: string | null;
  velocidade_padrao: LoteVelocidade;
}

/** `GET /modelos` (contract §8) — the image-model catalog; drives Configuracoes' picker + the Econômico lock. */
export interface ModeloCatalogoItem {
  id: string;
  nome: string;
  versao: string;
  tag_performance: 'performance' | 'economico' | null;
  suporta_batch: boolean;
  nota_recomendacao: string | null;
  metricas: {
    taxa_aprovacao: number | null;
    score_medio_ia: number | null;
    custo_por_foto_aprovada: number | null;
  } | null;
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

  /**
   * `GET /referencias` — platform-scope reference pool (contract §5), paged,
   * with pool occupancy + the fixed upload vocabularies. Keyed on the page
   * and the archived toggle, with `placeholderData` so flipping either never
   * unmounts a grid that already has content.
   */
  function useReferencias(
    params: { page?: number; pageSize?: number; incluirArquivadas?: boolean } = {},
  ) {
    const { page = 1, pageSize = 50, incluirArquivadas = false } = params;
    const query = useQuery<ReferenciasPage>({
      queryKey: ['edicao-fotos', 'referencias', page, pageSize, incluirArquivadas],
      queryFn: () =>
        api.get('/api/edicao-fotos/referencias', {
          page,
          page_size: pageSize,
          incluir_arquivadas: incluirArquivadas,
        }),
      staleTime: 30 * 1000,
      placeholderData: (prev) => prev,
    });
    return {
      referencias: query.data?.items ?? [],
      total: query.data?.total ?? 0,
      pool: query.data?.pool,
      opcoes: query.data?.opcoes,
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  /**
   * `POST /referencias` — multipart pair upload; 409 `pool_cheio` when the
   * pair limit is reached (contract §5). Fields: `antes`, `depois` (files),
   * `comodo`, `tipos_edicao` (repeated), `nota`.
   */
  function useCriarReferencia() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (body: NovaReferenciaBody) => {
        const form = new FormData();
        form.append('antes', body.antes);
        form.append('depois', body.depois);
        form.append('comodo', body.comodo);
        body.tipos_edicao.forEach((tipo) => form.append('tipos_edicao', tipo));
        if (body.nota) form.append('nota', body.nota);
        return api.upload<ReferenciaPar>('/api/edicao-fotos/referencias', form);
      },
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['edicao-fotos', 'referencias'] });
      },
    });
  }

  /** `DELETE /referencias/{id}` — archive, never a hard delete (contract §5). */
  function useArquivarReferencia() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (id: string) => api.delete<ReferenciaPar>(`/api/edicao-fotos/referencias/${id}`),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['edicao-fotos', 'referencias'] });
      },
    });
  }

  // ---------------------------------------------------------------------
  // Guias de estilo (contract §6), W6
  // ---------------------------------------------------------------------

  /** `GET /guias` — every version, newest first; `placeholderData` across page changes. */
  function useGuias(params: { page?: number; pageSize?: number } = {}) {
    const { page = 1, pageSize = 20 } = params;
    const query = useQuery<GuiasPage>({
      queryKey: ['edicao-fotos', 'guias', page, pageSize],
      queryFn: () => api.get('/api/edicao-fotos/guias', { page, page_size: pageSize }),
      placeholderData: (prev) => prev,
    });
    return {
      guias: query.data?.items ?? [],
      total: query.data?.total ?? 0,
      versaoAtiva: query.data?.versao_ativa ?? null,
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  function invalidateGuias(queryClient: ReturnType<typeof useQueryClient>) {
    queryClient.invalidateQueries({ queryKey: ['edicao-fotos', 'guias'] });
  }

  /** `POST /guias` — a manually written DRAFT (the no-AI path, contract §6). */
  function useCriarGuia() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (body: NovoGuiaBody) =>
        api.post<GuiaEstiloVersao>('/api/edicao-fotos/guias', body),
      onSuccess: () => invalidateGuias(queryClient),
    });
  }

  /** `POST /guias/{versao}/ativar` — this version becomes the one new batches snapshot. */
  function useAtivarGuia() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (versao: number) =>
        api.post<GuiaEstiloVersao>(`/api/edicao-fotos/guias/${versao}/ativar`, {}),
      onSuccess: () => invalidateGuias(queryClient),
    });
  }

  /** `POST /guias/{versao}/restaurar` — clones the version as a NEW draft (versions are immutable). */
  function useRestaurarGuia() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (versao: number) =>
        api.post<GuiaEstiloVersao>(`/api/edicao-fotos/guias/${versao}/restaurar`, {}),
      onSuccess: () => invalidateGuias(queryClient),
    });
  }

  /**
   * `POST /guias/regenerar` — queue the AI rebuild from the pool (202). The
   * draft appears only after the worker runs it; 409 `pool_vazio` on an
   * empty pool.
   */
  function useRegenerarGuia() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: () =>
        api.post<RegenerarGuiaResposta>('/api/edicao-fotos/guias/regenerar', {}),
      onSuccess: () => invalidateGuias(queryClient),
    });
  }

  // ---------------------------------------------------------------------
  // Configurações da plataforma (contract §8) — platform admin only
  // ---------------------------------------------------------------------

  /** `GET /configuracoes/plataforma`. Pass `enabled: false` for callers that cannot read it (curators get 403). */
  function useConfiguracoesPlataforma(options: { enabled?: boolean } = {}) {
    const { enabled = true } = options;
    const query = useQuery<PlataformaConfiguracoes>({
      queryKey: ['edicao-fotos', 'configuracoes-plataforma'],
      queryFn: () => api.get('/api/edicao-fotos/configuracoes/plataforma'),
      enabled,
    });
    return {
      configuracoes: query.data,
      showSkeleton: enabled && query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  /**
   * `PUT /configuracoes/plataforma` — send the WHOLE object (read, change,
   * write): omitted fields fall back to server defaults, except
   * `limite_pares_referencia`, which is left untouched when absent.
   */
  function useAtualizarConfiguracoesPlataforma() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (body: PlataformaConfiguracoes) =>
        api.put<PlataformaConfiguracoes>('/api/edicao-fotos/configuracoes/plataforma', body),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['edicao-fotos', 'configuracoes-plataforma'] });
        queryClient.invalidateQueries({ queryKey: ['edicao-fotos', 'referencias'] });
      },
    });
  }

  // ---------------------------------------------------------------------
  // Lotes — list/create/upload/vista/submeter/zip (contract §3), W10a
  // ---------------------------------------------------------------------

  /** `GET /lotes` — batch list (contract §3). Paginated per contract §0. */
  function useLotes(params: { page?: number; pageSize?: number } = {}) {
    const { page = 1, pageSize = 50 } = params;
    const query = useQuery<LotesPage>({
      queryKey: ['edicao-fotos', 'lotes', page, pageSize],
      queryFn: () => api.get('/api/edicao-fotos/lotes', { page, page_size: pageSize }),
      placeholderData: (prev) => prev,
    });
    return {
      lotes: query.data?.items ?? [],
      total: query.data?.total ?? 0,
      page: query.data?.page ?? page,
      pageSize: query.data?.page_size ?? pageSize,
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  /** `GET /lotes/{id}` — batch header + per-photo state (contract §3). */
  function useLote(loteId: string | null | undefined) {
    const query = useQuery<LoteDetalhe>({
      queryKey: ['edicao-fotos', 'lote', loteId],
      queryFn: () => api.get(`/api/edicao-fotos/lotes/${loteId}`),
      enabled: !!loteId,
      placeholderData: (prev) => prev,
    });
    return {
      lote: query.data,
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  /** `POST /lotes` — create batch metadata (contract §3). Photos follow via `useUploadFotos`/`useLoteVista`. */
  function useCriarLote() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (body: NovoLoteBody) => api.post<LoteCriado>('/api/edicao-fotos/lotes', body),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['edicao-fotos', 'lotes'] });
      },
    });
  }

  /**
   * `POST /lotes/{id}/fotos` — multipart upload (contract §3). Takes
   * `loteId` as a MUTATION VARIABLE (not a hook-instantiation parameter,
   * unlike `useRevisao`/`useDecidirFoto`) — the id is typically only known
   * mid-flow, right after `useCriarLote()` resolves (the "create batch, then
   * feed it photos" sequence `NovoLote.tsx` drives), so a hook-time
   * parameter would close over a stale `undefined`. Field name `fotos`
   * (repeated) — 🔴 FLAG: not specified by the contract; mirrors the
   * FastAPI `List[UploadFile] = File(...)` convention every other seed
   * multi-file upload uses (e.g. igig's `usePautas.ts`). Confirm against the
   * real router once W3 lands.
   */
  function useUploadFotos() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: ({ loteId, files }: { loteId: string; files: File[] }) => {
        const form = new FormData();
        files.forEach((file) => form.append('fotos', file));
        return api.upload(`/api/edicao-fotos/lotes/${loteId}/fotos`, form);
      },
      onSuccess: (_data, { loteId }) => {
        queryClient.invalidateQueries({ queryKey: ['edicao-fotos', 'lote', loteId] });
        queryClient.invalidateQueries({ queryKey: ['edicao-fotos', 'lotes'] });
      },
    });
  }

  /**
   * `POST /lotes/{id}/vista` — pull photos from a Vista imóvel by `codigo`
   * (contract §3, §10 C5). `loteId` is a mutation variable — same
   * just-created-mid-flow reasoning as `useUploadFotos`.
   */
  function useLoteVista() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: ({ loteId, body }: { loteId: string; body: VistaLoteBody }) =>
        api.post(`/api/edicao-fotos/lotes/${loteId}/vista`, body),
      onSuccess: (_data, { loteId }) => {
        queryClient.invalidateQueries({ queryKey: ['edicao-fotos', 'lote', loteId] });
        queryClient.invalidateQueries({ queryKey: ['edicao-fotos', 'lotes'] });
      },
    });
  }

  /**
   * `POST /lotes/{id}/submeter` — snapshot the effective guide + enqueue
   * jobs (contract §3). `loteId` is a mutation variable — same reasoning.
   */
  function useSubmeterLote() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (loteId: string) => api.post(`/api/edicao-fotos/lotes/${loteId}/submeter`, {}),
      onSuccess: (_data, loteId) => {
        queryClient.invalidateQueries({ queryKey: ['edicao-fotos', 'lote', loteId] });
        queryClient.invalidateQueries({ queryKey: ['edicao-fotos', 'lotes'] });
      },
    });
  }

  /**
   * `GET /lotes/{id}/zip` — binary download, **409 until every photo is
   * decided** (contract §3). Goes through `api.download()` (the `ApiClient`
   * binary-GET primitive — see `../api.ts`) rather than a raw `fetch`, so it
   * gets the SAME auth header + 401-retry path as every JSON call, and a
   * 409 surfaces as a normal `ApiError` with `.status === 409` the caller
   * can branch on (e.g. "ainda há fotos sem decisão"). Triggers the browser
   * download itself (`URL.createObjectURL` + a synthetic `<a download>`
   * click) — no Social-Wiring-specific helper involved, keeping this organ
   * portable.
   */
  function useBaixarZip() {
    return useMutation({
      mutationFn: async ({ loteId, nomeArquivo }: { loteId: string; nomeArquivo: string }) => {
        const blob = await api.download(`/api/edicao-fotos/lotes/${loteId}/zip`);
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = nomeArquivo;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(blobUrl);
      },
    });
  }

  // ---------------------------------------------------------------------
  // Configurações + catálogo de modelos (contract §8), W10a
  // ---------------------------------------------------------------------

  /** `GET /configuracoes` — org edit types, image model, speed override (contract §8). */
  function useConfiguracoes() {
    const query = useQuery<OrgConfiguracoes>({
      queryKey: ['edicao-fotos', 'configuracoes'],
      queryFn: () => api.get('/api/edicao-fotos/configuracoes'),
    });
    return {
      configuracoes: query.data,
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  /** `PUT /configuracoes` — agency admin / platform admin only server-side (contract §1, §8). */
  function useAtualizarConfiguracoes() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (body: OrgConfiguracoes) => api.put('/api/edicao-fotos/configuracoes', body),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['edicao-fotos', 'configuracoes'] });
        queryClient.invalidateQueries({ queryKey: ['edicao-fotos', 'capacidades'] });
      },
    });
  }

  /** `GET /modelos` — image-model catalog (contract §8); drives the Configuracoes picker. */
  function useModelos() {
    const query = useQuery<ModeloCatalogoItem[]>({
      queryKey: ['edicao-fotos', 'modelos'],
      queryFn: () => api.get('/api/edicao-fotos/modelos'),
      staleTime: 60 * 1000,
    });
    return {
      modelos: query.data ?? [],
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
      error: query.error,
      refetch: query.refetch,
    };
  }

  return {
    useCapacidades,
    useRevisao,
    useDecidirFoto,
    useRetentarFoto,
    useReferencias,
    useCriarReferencia,
    useArquivarReferencia,
    useGuias,
    useCriarGuia,
    useAtivarGuia,
    useRestaurarGuia,
    useRegenerarGuia,
    useConfiguracoesPlataforma,
    useAtualizarConfiguracoesPlataforma,
    useLotes,
    useLote,
    useCriarLote,
    useUploadFotos,
    useLoteVista,
    useSubmeterLote,
    useBaixarZip,
    useConfiguracoes,
    useAtualizarConfiguracoes,
    useModelos,
  };
}

export type EdicaoFotosHooks = ReturnType<typeof createEdicaoFotosHooks>;
