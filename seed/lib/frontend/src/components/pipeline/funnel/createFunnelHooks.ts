/**
 * `createFunnelHooks(descriptor, api)` — the data layer of the funnel organ.
 *
 * COMPOSES, never re-implements:
 *  - `createPipelineHooks` (board query, stages CRUD) — its `useMoveCard` is REPLACED by the funnel's
 *    (`pipeline.useMoveCard`), so a drag, the "Mover para…" menu and the "Etapa" select share ONE
 *    mutation with ONE cache contract;
 *  - `createCardHubHooks` (timeline, notas, lembretes, anexos …) when the product links a hub.
 *
 * CACHE CONTRACT (`KB § PATTERNS/frontend/mutation-cache-writes.md`, skill noc-cache-writes) — a write
 * lands in EVERY entry that shows the card, never invalidate-only:
 *   board entries  `[queryKey, filtros]`   → optimistic move/patch/remove + commit of the SERVER card
 *   card detail    `[queryKey-card, id]`   → optimistic patch + commit of the SERVER card
 *   settle         refetches the board (column totals are the server's call)
 * A status change (lose/archive/reopen) is applied per VIEW: a board filtered `status=aberto` loses the
 * card, a `status=perdido` board gains it — that decision is `showsStatus`, one function.
 *
 * REFUSALS ARE NEVER SILENT: every mutation either hands the error to the caller's `onError` (which
 * REPLACES the default) or toasts the server's own message (+ the missing requirements of a gate).
 */
import { keepPreviousData, useInfiniteQuery, useQuery, type QueryKey } from '@tanstack/react-query';
import { toast } from 'sonner';

import { boardOps, useCacheWriteMutation } from '../../../cache-writes';
import {
  createCardHubHooks,
  flattenTimeline,
  type CardHubApi,
  type CardHubDescriptor,
} from '../../card-hub/createCardHubHooks';
import type { TimelineEntry, TimelinePage } from '../../card-hub/types';
import { createPipelineHooks, type MoveVariables, type PipelineHooks } from '../createPipelineHooks';
import type { PipelineApi, PipelineColumn } from '../types';
import { parseFunnelError } from './funnelError';
import type { FunnelCard, FunnelMeta, FunnelStatus } from './types';

export interface FunnelDescriptor {
  /** React Query key root. Unique per funnel. */
  queryKey: string;
  /** The funnel's API prefix `P`, e.g. `/api/funil`. */
  prefix: string;
  /** Noun for toasts: "negócio". */
  entityLabel: string;
  /** Link the card-hub (timeline / notas / lembretes …). Omit for a funnel with no hub. */
  hub?: { descriptor: CardHubDescriptor; api: CardHubApi };
}

export interface LoseVariables {
  cardId: string;
  motivo_codigo: string;
  motivo_texto?: string;
}

export interface ActionVariables {
  cardId: string;
  codigo: string;
  inputs?: Record<string, unknown>;
}

export interface ActionResult<TCard> {
  card: TCard | null;
  efeitos: unknown;
}

type MutationErrorHandler<V> = (error: Error, vars: V) => void;

function unwrap<T>(result: unknown, fallback: T): T {
  if (result == null) return fallback;
  if (typeof result === 'object' && Object.prototype.hasOwnProperty.call(result, 'data')) {
    return ((result as { data?: T }).data ?? fallback) as T;
  }
  return result as T;
}

/** A card answer may be the bare DTO or `{card, efeitos}`. */
function asCard<TCard extends FunnelCard>(result: unknown): TCard | null {
  const body = unwrap<unknown>(result, null);
  if (!body || typeof body !== 'object') return null;
  const inner = (body as { card?: unknown }).card;
  if (inner && typeof inner === 'object') return inner as TCard;
  return typeof (body as { id?: unknown }).id === 'string' ? (body as TCard) : null;
}

/** Does the board entry under `queryKey` list cards of `status`? (`status` filter absent = open cards.) */
export function showsStatus(queryKey: QueryKey | undefined, status: FunnelStatus): boolean {
  const filtros = (queryKey?.[1] ?? {}) as { status?: string };
  const view = filtros.status ?? 'aberto';
  return view === 'todos' || view === status;
}

/** Merge an edit into a card: DTO keys stay top-level, anything else is a `campos` key. */
export function mergeChanges<TCard extends FunnelCard>(card: TCard, changes: Record<string, unknown>): TCard {
  const next: Record<string, unknown> = Object.fromEntries(Object.entries(card));
  const campos: Record<string, unknown> = { ...card.campos };
  for (const [key, value] of Object.entries(changes)) {
    if (key !== 'campos' && key in card) next[key] = value;
    else campos[key] = value;
  }
  return { ...next, campos } as TCard;
}

export function createFunnelHooks<TCard extends FunnelCard = FunnelCard>(
  descriptor: FunnelDescriptor,
  api: PipelineApi,
) {
  const { queryKey, prefix, entityLabel } = descriptor;
  const metaKey = [`${queryKey}-meta`] as const;
  const cardKey = `${queryKey}-card`;
  const keys = {
    board: [queryKey] as const,
    meta: metaKey,
    card: (id: string) => [cardKey, id] as const,
    movimentos: (id: string) => [`${queryKey}-movimentos`, id] as const,
  };

  const idOf = (c: TCard) => c.id;
  const ops = boardOps<TCard>((c) => c.valor, idOf);
  const cardPath = (id: string) => `${prefix}/cards/${encodeURIComponent(id)}`;

  const base = createPipelineHooks<TCard>(
    {
      queryKey,
      boardEndpoint: `${prefix}/board`,
      moveEndpoint: `${prefix}/cards`,
      getCardId: idOf,
      getCardValue: (c) => c.valor,
      entityLabel,
    },
    api,
  );

  const hub = descriptor.hub ? createCardHubHooks(descriptor.hub.descriptor, descriptor.hub.api) : null;

  // ─── Cache-write targets (shared by every card mutation) ─────────────────

  /** Put the SERVER's card into one board entry, honouring the entry's status view. */
  function applyServerCard(old: PipelineColumn<TCard>[] | undefined, card: TCard, key?: QueryKey) {
    if (!Array.isArray(old)) return old;
    const holder = old.find((col) => col.cards.some((c) => c.id === card.id));
    if (!showsStatus(key, card.status)) return holder ? ops.removeCard(old, card.id) : old;
    if (!holder) return ops.addCard(old, card.etapa_id, card);
    if (holder.etapa !== card.etapa_id) {
      const removed = ops.removeCard(old, card.id);
      return ops.addCard(removed, card.etapa_id, card);
    }
    return ops.patchCard(old, card.id, card);
  }

  function targetsFor<V>(
    cardId: string,
    optimistic?: {
      board?: (old: PipelineColumn<TCard>[] | undefined, key?: QueryKey) => PipelineColumn<TCard>[] | undefined;
      card?: (old: TCard) => TCard;
    },
  ) {
    return [
      {
        queryKey: [queryKey] as QueryKey,
        match: 'prefix' as const,
        optimistic: optimistic?.board
          ? (old: PipelineColumn<TCard>[] | undefined, _v: V, _c: unknown, key?: QueryKey) => optimistic.board!(old, key)
          : undefined,
        commit: (old: PipelineColumn<TCard>[] | undefined, result: TCard | null, _v: V, _c: unknown, key?: QueryKey) =>
          result ? applyServerCard(old, result, key) : old,
      },
      {
        queryKey: keys.card(cardId) as QueryKey,
        optimistic: optimistic?.card
          ? (old: TCard | undefined) => (old ? optimistic.card!(old) : undefined)
          : undefined,
        commit: (old: TCard | undefined, result: TCard | null) => result ?? old,
      },
    ];
  }

  /** Default refusal handling: the server's own words, plus what a gate still needs. */
  function toastRefusal(error: Error, title: string) {
    const r = parseFunnelError(error);
    toast.error(title, {
      description:
        r.pendencias.length > 0
          ? `${r.mensagem} Falta: ${r.pendencias.map((p) => p.label).join(', ')}.`
          : r.mensagem,
    });
  }

  // ─── Reads ───────────────────────────────────────────────────────────────

  function useMeta() {
    return useQuery({
      queryKey: keys.meta,
      queryFn: async () => unwrap<FunnelMeta | null>(await api.get(`${prefix}/meta`), null),
      staleTime: 5 * 60 * 1000,
      placeholderData: keepPreviousData,
    });
  }

  function useCard(id: string | null) {
    return useQuery({
      queryKey: keys.card(id ?? '__none__'),
      queryFn: async () => unwrap<TCard | null>(await api.get(cardPath(id as string)), null),
      enabled: !!id,
    });
  }

  /** The card's stage-move history; cursor-paginated. Items are hub-timeline entries (`kind: 'movimento'`). */
  function useMovimentos(id: string | null) {
    return useInfiniteQuery({
      queryKey: keys.movimentos(id ?? '__none__'),
      queryFn: async ({ pageParam }: { pageParam: string | null }) => {
        const res = await api.get<TimelinePage>(
          `${cardPath(id as string)}/movimentos`,
          pageParam ? { cursor: pageParam } : undefined,
        );
        return unwrap<TimelinePage>(res, { items: [], total: 0, next_cursor: null });
      },
      initialPageParam: null as string | null,
      getNextPageParam: (last) => last.next_cursor,
      enabled: !!id,
    });
  }

  // ─── Writes ──────────────────────────────────────────────────────────────

  /**
   * Move a card (drag, "Mover para…", "Etapa" select). Optimistic; a refusal rolls the card back
   * (snap-back) and goes to `options.onError`, which REPLACES the default toast.
   */
  function useMoveCard(options?: { onError?: MutationErrorHandler<MoveVariables> }) {
    return useCacheWriteMutation<TCard | null, MoveVariables>({
      mutationFn: async (vars) =>
        asCard<TCard>(
          await api.post(`${cardPath(vars.cardId)}/mover-etapa`, {
            para_etapa_id: vars.toStageId,
            novo_indice: vars.toIndex,
            motivo: vars.motivo,
            extra: vars.extra,
          }),
        ),
      targets: (vars) =>
        targetsFor<MoveVariables>(vars.cardId, {
          board: (old) => ops.moveCard(old, vars.cardId, vars.toStageId, vars.toIndex),
          card: (c) => ({ ...c, etapa_id: vars.toStageId }),
        }),
      onError: (error, vars) =>
        options?.onError ? options.onError(error, vars) : toastRefusal(error, `Erro ao mover ${entityLabel}`),
    });
  }

  /** The board hooks the organ hands to `PipelineBoard`: base pipeline + the funnel's move. */
  const pipeline: PipelineHooks<TCard> = { ...base, useMoveCard };

  /** Edit fields (`PATCH P/cards/{id}`) — only keys the server lists in `campos_editaveis`. */
  function useUpdateCard(options?: { onError?: MutationErrorHandler<{ cardId: string }> }) {
    return useCacheWriteMutation<TCard | null, { cardId: string; changes: Record<string, unknown> }>({
      mutationFn: async (vars) => asCard<TCard>(await api.patch(cardPath(vars.cardId), vars.changes)),
      targets: (vars) =>
        targetsFor(vars.cardId, {
          board: (old) => {
            const card = old?.flatMap((c) => c.cards).find((c) => c.id === vars.cardId);
            return card ? ops.patchCard(old, vars.cardId, mergeChanges(card, vars.changes)) : old;
          },
          card: (c) => mergeChanges(c, vars.changes),
        }),
      onError: (error, vars) =>
        options?.onError ? options.onError(error, vars) : toastRefusal(error, `Erro ao salvar ${entityLabel}`),
    });
  }

  function useCreateCard() {
    return useCacheWriteMutation<TCard | null, Record<string, unknown>>({
      mutationFn: async (body) => asCard<TCard>(await api.post(`${prefix}/cards`, body)),
      // The server assigns id, position and stage: commit its card (no stand-in).
      targets: [
        {
          queryKey: [queryKey],
          match: 'prefix',
          commit: (old: PipelineColumn<TCard>[] | undefined, card: TCard | null, _v, _c, key) =>
            card ? applyServerCard(old, card, key) : old,
        },
      ],
      onError: (error) => toastRefusal(error, `Erro ao criar ${entityLabel}`),
    });
  }

  /** Mark lost with a coded reason (+ text when the reason asks for it). A 422 stays on the mutation for the dialog. */
  function useLose(options?: { onError?: MutationErrorHandler<LoseVariables> }) {
    return useCacheWriteMutation<TCard | null, LoseVariables>({
      mutationFn: async ({ cardId, ...body }) => asCard<TCard>(await api.post(`${cardPath(cardId)}/perder`, body)),
      targets: (vars) =>
        targetsFor<LoseVariables>(vars.cardId, {
          board: (old, key) =>
            showsStatus(key, 'perdido')
              ? ops.patchCard(old, vars.cardId, { status: 'perdido', motivo_perda_codigo: vars.motivo_codigo })
              : ops.removeCard(old, vars.cardId),
          card: (c) => ({
            ...c,
            status: 'perdido' as const,
            motivo_perda_codigo: vars.motivo_codigo,
            motivo_perda: vars.motivo_texto ?? c.motivo_perda,
          }),
        }),
      onError: (error, vars) => {
        if (options?.onError) return options.onError(error, vars);
        // motivo_* refusals are rendered inline by LostReasonDialog; everything else is a toast.
        if (!parseFunnelError(error).code?.startsWith('motivo_')) toastRefusal(error, `Erro ao perder ${entityLabel}`);
      },
    });
  }

  function useStatusChange(path: 'reabrir' | 'arquivar', status: FunnelStatus, verb: string) {
    return function useStatusMutation(options?: { onError?: MutationErrorHandler<{ cardId: string }> }) {
      return useCacheWriteMutation<TCard | null, { cardId: string }>({
        mutationFn: async ({ cardId }) => asCard<TCard>(await api.post(`${cardPath(cardId)}/${path}`, {})),
        targets: (vars) =>
          targetsFor<{ cardId: string }>(vars.cardId, {
            board: (old, key) =>
              showsStatus(key, status)
                ? ops.patchCard(old, vars.cardId, { status })
                : ops.removeCard(old, vars.cardId),
            card: (c) => ({ ...c, status }),
          }),
        onError: (error, vars) =>
          options?.onError ? options.onError(error, vars) : toastRefusal(error, `Erro ao ${verb} ${entityLabel}`),
      });
    };
  }
  const useReopen = useStatusChange('reabrir', 'aberto', 'reabrir');
  const useArchive = useStatusChange('arquivar', 'arquivado', 'arquivar');

  /** Run a product action (`POST P/cards/{id}/acoes/{codigo}`); the answer's card is committed everywhere. */
  function useAction(options?: { onError?: MutationErrorHandler<ActionVariables> }) {
    return useCacheWriteMutation<ActionResult<TCard>, ActionVariables>({
      mutationFn: async ({ cardId, codigo, inputs }) => {
        const res = await api.post(`${cardPath(cardId)}/acoes/${encodeURIComponent(codigo)}`, inputs ?? {});
        const body = unwrap<{ efeitos?: unknown } | null>(res, null);
        return { card: asCard<TCard>(res), efeitos: body?.efeitos ?? null };
      },
      targets: (vars) => [
        {
          queryKey: [queryKey] as QueryKey,
          match: 'prefix' as const,
          commit: (old: PipelineColumn<TCard>[] | undefined, res: ActionResult<TCard>, _v: ActionVariables, _c: unknown, key?: QueryKey) =>
            res.card ? applyServerCard(old, res.card, key) : old,
        },
        {
          queryKey: keys.card(vars.cardId) as QueryKey,
          commit: (old: TCard | undefined, res: ActionResult<TCard>) => res.card ?? old,
        },
      ],
      onError: (error, vars) =>
        options?.onError ? options.onError(error, vars) : toastRefusal(error, 'Não foi possível executar a ação'),
    });
  }

  // ─── Activity pane (hub timeline + comments, else the stage-move history) ─

  const emptyTimeline: TimelinePage = { items: [], total: 0, next_cursor: null };
  /** Stand-in with the hub's hook shape, so `useActivity` calls the same hooks every render. */
  const useNoHubTimeline = (_hubId: string | null) =>
    useInfiniteQuery({
      queryKey: [`${queryKey}-no-hub`],
      queryFn: async () => emptyTimeline,
      initialPageParam: null as string | null,
      getNextPageParam: () => null,
      enabled: false,
    });
  const useHubTimeline = hub ? (id: string | null) => hub.useTimeline(id) : useNoHubTimeline;
  const useHubComment = hub ? (id: string) => hub.useNotaMutations(id).create : (_id: string) => null;

  /** The right-hand pane: hub timeline + composer when the card links a hub, else the move history. */
  function useActivity(cardId: string | null, hubId: string | null): {
    entries: TimelineEntry[];
    loading: boolean;
    error: string | null;
    hasMore: boolean;
    loadingMore: boolean;
    onLoadMore: () => void;
    composer: { onPost: (corpo: string) => void; posting: boolean } | null;
  } {
    const linked = !!hub && !!hubId;
    const hubTl = useHubTimeline(linked ? hubId : null);
    const mov = useMovimentos(linked ? null : cardId);
    const comment = useHubComment(hubId ?? '');
    const q = linked ? hubTl : mov;
    return {
      entries: flattenTimeline(q.data?.pages),
      loading: q.isPending && !q.data && q.fetchStatus !== 'idle',
      error: q.error ? parseFunnelError(q.error).mensagem : null,
      hasMore: !!q.hasNextPage,
      loadingMore: q.isFetchingNextPage,
      onLoadMore: () => void q.fetchNextPage(),
      composer:
        linked && comment
          ? {
              onPost: (corpo) =>
                comment.mutate(
                  { corpo },
                  {
                    onError: (e) =>
                      toast.error('Não foi possível publicar o comentário', {
                        description: parseFunnelError(e).mensagem,
                      }),
                  },
                ),
              posting: comment.isPending,
            }
          : null,
    };
  }

  return {
    descriptor,
    api,
    keys,
    hub,
    useActivity,
    /** Pass this to `PipelineBoard`. */
    pipeline,
    useMeta,
    useBoard: base.useBoard,
    useCard,
    useMovimentos,
    useMoveCard,
    useUpdateCard,
    useCreateCard,
    useLose,
    useReopen,
    useArchive,
    useAction,
  };
}

export type FunnelHooks<TCard extends FunnelCard = FunnelCard> = ReturnType<typeof createFunnelHooks<TCard>>;
