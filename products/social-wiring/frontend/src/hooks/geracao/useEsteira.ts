/**
 * Esteira de Reels hooks over `/api/media-creation/esteira` and
 * `/api/media-creation/equipe` (esteira-contract.md §5.1/§5.2/§5.3, FE-0).
 *
 * Stage CRUD and the optimistic card move come from `esteiraPipeline`
 * (`@/lib/pipelines`); this file owns the board READ (the payload is
 * `{colunas, orfaos}`), post CRUD, headline/roteiro bind/unbind, the caption
 * generator and the equipe.
 *
 * Loading rule (lying-loading-state.md): `showSkeleton = isPending && !data`,
 * `isRefreshing = isFetching && !!data`, `placeholderData` on key changes —
 * never `isLoading`.
 *
 * Invalidation: any change to a post can change the `post` badge on the
 * Geração libraries (§5.3), so post mutations invalidate three families — the
 * board (`[ESTEIRA_PIPELINE_KEY]`), the post/equipe family (`ESTEIRA_KEY`) and
 * the Geração family (`GERACAO_KEY`).
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { jobPolling } from "@noctusai/lib";
import { boardOps, listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { emAndamento } from "@/components/geracao/labels";
import { ESTEIRA_KEY, ESTEIRA_PIPELINE_KEY } from "@/lib/esteiraKeys";
import type {
  LegendaGerada,
  MembroEquipe,
  PostCard,
  PostCreate,
  PostDetalhe,
  PostUpdate,
} from "@/types/esteira";
import { GERACAO_KEY } from "@/lib/geracaoKeys";

interface Envelope<T> {
  success?: boolean;
  data: T;
}
const unwrap = <T>(res: Envelope<T>): T => res.data;

export const ESTEIRA_BASE = "/api/media-creation/esteira";
export const EQUIPE_BASE = "/api/media-creation/equipe";
/** Poll cadence while a post has a headline batch (`lote_ativo`) or a linked roteiro still running. */
export const ESTEIRA_POLL_MS = 3000;

export const esteiraKeys = {
  all: ESTEIRA_KEY,
  board: (filtros: EsteiraFiltros) => [ESTEIRA_PIPELINE_KEY, filtros] as const,
  orfaos: [...ESTEIRA_KEY, "orfaos"] as const,
  post: (id: string | null) => [...ESTEIRA_KEY, "post", id] as const,
  equipe: (incluirInativos: boolean) => [...ESTEIRA_KEY, "equipe", incluirInativos] as const,
};

/** Board filters (§5.1 #2). `marca_id` of another org is a 404 server-side. */
export interface EsteiraFiltros {
  marca_id?: string;
  busca?: string;
  membro_id?: string;
  incluir_arquivados?: boolean;
  limite_por_etapa?: number;
}

/** One column as `GET /board` returns it (§5.1 #2). */
export interface EsteiraColuna {
  etapa: string;
  stage: unknown;
  cards: PostCard[];
  total: number;
  exibidos: number;
}
export interface EsteiraBoardPayload {
  colunas: EsteiraColuna[];
  orfaos: number;
}

function useInvalidateEsteira() {
  const qc = useQueryClient();
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: [ESTEIRA_PIPELINE_KEY] }),
      qc.invalidateQueries({ queryKey: ESTEIRA_KEY }),
      qc.invalidateQueries({ queryKey: GERACAO_KEY }),
    ]);
}


/** The board cache entry is the bare `colunas` array; stage-list entries share the prefix and carry no `cards` (boardOps skips them). */
const board = boardOps<PostCard>(() => 0);

/** Keys refreshed in the background after any post write (badge on the Geração libraries, §5.3). */
const POST_SETTLE = [[ESTEIRA_PIPELINE_KEY], ESTEIRA_KEY, GERACAO_KEY];

// ─── Board ──────────────────────────────────────────────────────────────────

/**
 * True while any card's linked roteiro is still being produced (`criando` /
 * `processando`). The roteiro worker writes the roteiro row, never the post, so
 * without this poll a card's roteiro chip stayed on "Criando" forever (2026-10-13).
 */
export function algumRoteiroDoBoardEmAndamento(colunas: Pick<EsteiraColuna, "cards">[] | undefined): boolean {
  return !!colunas?.some((c) => c.cards.some((card) => !!card.roteiro && emAndamento(card.roteiro.status)));
}

/** Strip empty filter values so `{busca: ""}` and `{}` share one cache entry. */
function limpar(f: EsteiraFiltros): EsteiraFiltros {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(f)) {
    if (v === undefined || v === null || v === "" || v === false) continue;
    out[k] = v;
  }
  return out as EsteiraFiltros;
}

/**
 * The board read. The cache entry under `[ESTEIRA_PIPELINE_KEY, filtros]` holds
 * the bare `colunas` array — exactly what `esteiraPipeline.useMoveCard`
 * splices optimistically; `orfaos` (posts whose stage is gone/inactive) is
 * kept beside it and read as `orfaos`.
 */
export function useEsteiraBoard(filtros: EsteiraFiltros = {}, options?: { enabled?: boolean }) {
  const qc = useQueryClient();
  const f = limpar(filtros);
  const query = useQuery({
    queryKey: esteiraKeys.board(f),
    enabled: options?.enabled ?? true,
    queryFn: async () => {
      const p = new URLSearchParams();
      for (const [k, v] of Object.entries(f)) p.set(k, String(v));
      const qs = p.toString();
      const d = unwrap(await api.get<Envelope<EsteiraBoardPayload>>(`${ESTEIRA_BASE}/board${qs ? `?${qs}` : ""}`));
      qc.setQueryData(esteiraKeys.orfaos, d.orfaos ?? 0);
      return d.colunas ?? [];
    },
    ...jobPolling((d: EsteiraColuna[] | undefined) => algumRoteiroDoBoardEmAndamento(d), ESTEIRA_POLL_MS),
    placeholderData: keepPreviousData,
  });
  const orfaos = useQuery({
    queryKey: esteiraKeys.orfaos,
    queryFn: () => Promise.resolve(0),
    enabled: false,
    initialData: 0,
  });
  return {
    ...query,
    colunas: query.data,
    orfaos: orfaos.data ?? 0,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

// ─── Posts ──────────────────────────────────────────────────────────────────

/** One post (§5.1 #4). Polls while a headline batch bound to it or its linked roteiro is running. */
export function usePost(id: string | null) {
  const query = useQuery({
    queryKey: esteiraKeys.post(id),
    enabled: !!id,
    queryFn: async () =>
      unwrap(await api.get<Envelope<PostDetalhe>>(`${ESTEIRA_BASE}/posts/${encodeURIComponent(id as string)}`)),
    ...jobPolling(
      (d: PostDetalhe | undefined) => !!d && (!!d.lote_ativo || (!!d.roteiro && emAndamento(d.roteiro.status))),
      ESTEIRA_POLL_MS,
    ),
    placeholderData: (prev) => (prev && prev.id === id ? prev : undefined),
  });
  return {
    ...query,
    showSkeleton: !!id && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export function useCriarPost() {
  const invalidate = useInvalidateEsteira();
  return useMutation({ // noc-allow: invalidate-only — the server picks the stage and position of a new post, so the board is regrouped server-side
    mutationFn: async (body: PostCreate) =>
      unwrap(await api.post<Envelope<PostDetalhe>>(`${ESTEIRA_BASE}/posts`, body)),
    onSuccess: invalidate,
  });
}

/** Commit a saved post into its detail and into the card on every cached board. */
function postTargets(id: string) {
  return [
    {
      queryKey: esteiraKeys.post(id),
      commit: (old: PostDetalhe | undefined, saved: PostDetalhe) => listOps.merge(old, saved),
    },
    {
      queryKey: [ESTEIRA_PIPELINE_KEY],
      match: "prefix" as const,
      commit: (old: EsteiraColuna[] | undefined, saved: PostDetalhe) =>
        board.patchCard(old, id, saved),
    },
  ];
}

export function useAtualizarPost() {
  return useCacheWriteMutation<PostDetalhe, { id: string; patch: PostUpdate }>({
    mutationFn: async (v) =>
      unwrap(
        await api.patch<Envelope<PostDetalhe>>(`${ESTEIRA_BASE}/posts/${encodeURIComponent(v.id)}`, v.patch),
      ),
    targets: (v) => postTargets(v.id),
    invalidate: POST_SETTLE,
  });
}

export function useExcluirPost() {
  return useCacheWriteMutation<string, string>({
    mutationFn: async (id) => {
      await api.delete(`${ESTEIRA_BASE}/posts/${encodeURIComponent(id)}`);
      return id;
    },
    targets: (id) => [
      {
        queryKey: [ESTEIRA_PIPELINE_KEY],
        match: "prefix",
        optimistic: (old: EsteiraColuna[] | undefined) => board.removeCard(old, id),
      },
    ],
    invalidate: POST_SETTLE,
  });
}

// ─── Headline / roteiro binding (§5.1 #8–#11) ───────────────────────────────

/** Bind an existing headline (`{headline_id}`) or create one from text (`{texto}`, ≤ 1 000). */
export type VincularHeadline = { headline_id: string } | { texto: string };

export function useVincularHeadline() {
  return useCacheWriteMutation<PostDetalhe, { postId: string; body: VincularHeadline }>({
    mutationFn: async (v) =>
      unwrap(
        await api.put<Envelope<PostDetalhe>>(
          `${ESTEIRA_BASE}/posts/${encodeURIComponent(v.postId)}/headline`,
          v.body,
        ),
      ),
    targets: (v) => postTargets(v.postId),
    invalidate: POST_SETTLE,
  });
}

/** Unbinding is predictable: the post's `headline` becomes null on the detail and on the card. */
function desvincularTargets(postId: string, campo: "headline" | "roteiro") {
  return [
    {
      queryKey: esteiraKeys.post(postId),
      optimistic: (old: PostDetalhe | undefined) => listOps.merge(old, { [campo]: null }),
    },
    {
      queryKey: [ESTEIRA_PIPELINE_KEY],
      match: "prefix" as const,
      optimistic: (old: EsteiraColuna[] | undefined) =>
        board.patchCard(old, postId, { [campo]: null }),
    },
  ];
}

export function useDesvincularHeadline() {
  return useCacheWriteMutation<string, string>({
    mutationFn: async (postId) => {
      await api.delete(`${ESTEIRA_BASE}/posts/${encodeURIComponent(postId)}/headline`);
      return postId;
    },
    targets: (postId) => desvincularTargets(postId, "headline"),
    invalidate: POST_SETTLE,
  });
}

export function useVincularRoteiro() {
  return useCacheWriteMutation<PostDetalhe, { postId: string; roteiroId: string }>({
    mutationFn: async (v) =>
      unwrap(
        await api.put<Envelope<PostDetalhe>>(`${ESTEIRA_BASE}/posts/${encodeURIComponent(v.postId)}/roteiro`, {
          roteiro_id: v.roteiroId,
        }),
      ),
    targets: (v) => postTargets(v.postId),
    invalidate: POST_SETTLE,
  });
}

export function useDesvincularRoteiro() {
  return useCacheWriteMutation<string, string>({
    mutationFn: async (postId) => {
      await api.delete(`${ESTEIRA_BASE}/posts/${encodeURIComponent(postId)}/roteiro`);
      return postId;
    },
    targets: (postId) => desvincularTargets(postId, "roteiro"),
    invalidate: POST_SETTLE,
  });
}

// ─── Legenda (§5.3) ─────────────────────────────────────────────────────────

/**
 * Generate caption + hashtags + first comment. The result is RETURNED, not
 * saved (the user edits, then PATCHes via `useAtualizarPost`), so this
 * invalidates nothing.
 */
export function useGerarLegenda() {
  return useMutation({ // noc-allow: invalidate-only — the generated caption is returned for editing, never stored, so there is no cached read
    mutationFn: async (postId: string) =>
      unwrap(
        await api.post<Envelope<LegendaGerada>>(`${ESTEIRA_BASE}/posts/${encodeURIComponent(postId)}/legenda/gerar`),
      ),
  });
}

// ─── Equipe (§5.2) ──────────────────────────────────────────────────────────

export function useEquipe(incluirInativos = false) {
  const query = useQuery({
    queryKey: esteiraKeys.equipe(incluirInativos),
    queryFn: async () => {
      const qs = incluirInativos ? "?incluir_inativos=true" : "";
      return unwrap(await api.get<Envelope<MembroEquipe[]>>(`${EQUIPE_BASE}${qs}`));
    },
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export type MembroCreate = { nome: string; funcao?: string; cor?: string; user_id?: string };
export type MembroUpdate = Partial<MembroCreate> & { ativo?: boolean };

/** A member shows on cards (`membros`), so the board is refreshed too. */
export function useCriarMembro() {
  return useCacheWriteMutation<MembroEquipe, MembroCreate>({
    mutationFn: async (body) => unwrap(await api.post<Envelope<MembroEquipe>>(EQUIPE_BASE, body)),
    targets: [
      {
        queryKey: [...ESTEIRA_KEY, "equipe"],
        match: "prefix",
        commit: (old, saved) => listOps.replace(old, saved.id, saved),
      },
    ],
    invalidate: POST_SETTLE,
  });
}

export function useAtualizarMembro() {
  return useCacheWriteMutation<MembroEquipe, { id: string; patch: MembroUpdate }>({
    mutationFn: async (v) =>
      unwrap(await api.patch<Envelope<MembroEquipe>>(`${EQUIPE_BASE}/${encodeURIComponent(v.id)}`, v.patch)),
    targets: (v) => [
      {
        queryKey: [...ESTEIRA_KEY, "equipe"],
        match: "prefix",
        commit: (old, saved) => listOps.patch(old, v.id, saved),
      },
    ],
    invalidate: POST_SETTLE,
  });
}

export function useExcluirMembro() {
  return useCacheWriteMutation<string, string>({
    mutationFn: async (id) => {
      await api.delete(`${EQUIPE_BASE}/${encodeURIComponent(id)}`);
      return id;
    },
    targets: (id) => [
      {
        queryKey: [...ESTEIRA_KEY, "equipe"],
        match: "prefix",
        optimistic: (old) => listOps.remove(old, id),
      },
    ],
    invalidate: POST_SETTLE,
  });
}
