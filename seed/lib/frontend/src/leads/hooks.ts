/**
 * `createLeadsHooks(api)` -- TanStack Query hooks for the leads API (`/api/leads`).
 *
 * 🔴 Loading contract (`KB § PATTERNS/frontend/lying-loading-state.md`): every read returns `showSkeleton =
 * isPending && !data` (first load only) and `isRefreshing` -- never `isLoading`, never a bare `isFetching` gate;
 * board / list keep `placeholderData` across filter changes so the screen never blanks while a new filter loads.
 *
 * 🔴 Writes (`KB § PATTERNS/frontend/mutation-cache-writes.md`): every mutation is a `useCacheWriteMutation` that
 * writes EVERY entry it touches -- the board (all cached filter variants), each cached list, the detail:
 *   - move: the card changes column on the drag (rolled back on a refusal), the server's row is committed;
 *   - update: the change is drawn at once and the server's canonical row (e.g. the E.164 phone) replaces it;
 *   - delete: the card leaves everywhere on the click;
 *   - create: the server assigns the id -> committed into the UNFILTERED board / list (whether it belongs in a
 *     filtered view is the server's call: those converge on the settle refetch).
 */
import { keepPreviousData, useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query';

import type { ApiClient } from '../api';
import { boardOps, useCacheWriteMutation } from '../cache-writes';
import { infiniteOps } from '../organ-kit/infinite-ops';
import { apiErrorCode, errorMessage, signals } from '../organ-kit/query';
import { filterQuery } from './format';
import type {
  Lead,
  LeadColumn,
  LeadFiltersState,
  LeadInput,
  LeadPatch,
  LeadsConfigData,
  LeadsEnvelope,
  LeadsPage,
} from './types';

/** The subset of the seed `ApiClient` the leads hooks need. */
export type LeadsApi = Pick<ApiClient, 'get' | 'post' | 'patch' | 'delete'>;

const BASE = '/api/leads';

export const leadsKeys = {
  all: ['leads'] as const,
  config: ['leads', 'config'] as const,
  boards: ['leads', 'board'] as const,
  board: (f: LeadFiltersState) => ['leads', 'board', f] as const,
  lists: ['leads', 'list'] as const,
  list: (f: LeadFiltersState) => ['leads', 'list', f] as const,
  detail: (id: string) => ['leads', 'detail', id] as const,
};

export { apiErrorCode, errorMessage };

const noValue = () => 0;
const board = boardOps<Lead>(noValue, (l) => l.id);
const isUnfiltered = (key: readonly unknown[]) => Object.keys((key[2] as object | undefined) ?? {}).length === 0;

/** The server's row of a lead goes where the lead already is: patch in place, or change column if its stage changed. */
export function placeInBoard<T>(old: T | undefined, saved: Lead): T | undefined {
  const cols = old as unknown as LeadColumn[] | undefined;
  if (!Array.isArray(cols)) return old;
  const holder = cols.find((c) => c.cards.some((x) => x.id === saved.id));
  if (!holder) return old;
  if (holder.etapa === saved.stage) return board.patchCard(old, saved.id, saved);
  return board.addCard(board.removeCard(old, saved.id), saved.stage, saved);
}

export function createLeadsHooks(api: LeadsApi) {
  const unwrap = async <T,>(p: Promise<LeadsEnvelope<T>>): Promise<T> => (await p).data;

  function useLeadsConfig() {
    // The funnel's stages / origins change rarely (they are product data): no refetch storms.
    const q = useQuery<LeadsConfigData>({
      queryKey: leadsKeys.config,
      queryFn: () => unwrap<LeadsConfigData>(api.get(`${BASE}/config`)),
      staleTime: 5 * 60_000,
    });
    return signals(q);
  }

  function useLeadsBoard(filters: LeadFiltersState = {}) {
    const q = useQuery<LeadColumn[]>({
      queryKey: leadsKeys.board(filters),
      queryFn: () => unwrap<LeadColumn[]>(api.get(`${BASE}/board`, filterQuery({ ...filters, stage: undefined }))),
      placeholderData: keepPreviousData,
    });
    return signals(q);
  }

  function useLeadsList(filters: LeadFiltersState = {}, pageSize = 50) {
    const q = useInfiniteQuery<LeadsPage, Error, { pages: LeadsPage[] }, readonly unknown[], string | null>({
      queryKey: leadsKeys.list(filters),
      initialPageParam: null,
      queryFn: ({ pageParam }) =>
        api.get<LeadsPage>(BASE, { ...filterQuery(filters), limit: pageSize, ...(pageParam ? { cursor: pageParam } : {}) }),
      getNextPageParam: (last) => last.next_cursor ?? undefined,
      placeholderData: keepPreviousData,
    });
    const leads = q.data?.pages.flatMap((p) => p.data) ?? [];
    return {
      ...signals(q as any),
      data: q.data ? leads : undefined,
      hasNextPage: q.hasNextPage,
      isFetchingNextPage: q.isFetchingNextPage,
      fetchNextPage: q.fetchNextPage,
    };
  }

  function useLead(id: string | null | undefined) {
    // Personal data keyed by id: no placeholderData (it would show the previous person under the new id).
    const q = useQuery<Lead>({
      queryKey: leadsKeys.detail(id ?? ''),
      queryFn: () => unwrap<Lead>(api.get(`${BASE}/${id}`)),
      enabled: !!id,
    });
    return signals(q);
  }

  function useCreateLead() {
    const qc = useQueryClient();
    return useCacheWriteMutation<Lead, LeadInput>({
      mutationFn: (body) => unwrap<Lead>(api.post(BASE, body)),
      targets: [
        { queryKey: leadsKeys.boards, match: 'prefix', predicate: isUnfiltered, commit: (old, saved) => board.addCard(old, saved.stage, saved) },
        { queryKey: leadsKeys.lists, match: 'prefix', predicate: isUnfiltered, commit: (old, saved) => infiniteOps.prepend(old, saved) },
      ],
      onSuccess: (saved) => {
        qc.setQueryData(leadsKeys.detail(saved.id), saved);
      },
    });
  }

  /** Fields whose edit is exactly what the user typed (the server may canonicalise `phone`; the commit fixes it). */
  function useUpdateLead() {
    return useCacheWriteMutation<Lead, { id: string } & LeadPatch>({
      mutationFn: ({ id, ...body }) => unwrap<Lead>(api.patch(`${BASE}/${id}`, body)),
      targets: ({ id, stage: _stage, ...changes }) => [
        {
          queryKey: leadsKeys.boards,
          match: 'prefix',
          optimistic: (old: unknown) => board.patchCard(old, id, changes),
          commit: (old: unknown, saved: Lead) => placeInBoard(old, saved),
        },
        {
          queryKey: leadsKeys.lists,
          match: 'prefix',
          optimistic: (old: unknown) => infiniteOps.patch(old, id, changes),
          commit: (old: unknown, saved: Lead) => infiniteOps.replace(old, id, saved),
        },
        {
          queryKey: leadsKeys.detail(id),
          optimistic: (old: Lead | undefined) => (old ? { ...old, ...changes } : old),
          commit: (old: Lead | undefined, saved: Lead) => (old === undefined ? undefined : saved),
        },
      ],
    });
  }

  function useDeleteLead() {
    return useCacheWriteMutation<unknown, string>({
      mutationFn: (id) => api.delete(`${BASE}/${id}`),
      targets: (id) => [
        { queryKey: leadsKeys.boards, match: 'prefix', optimistic: (old: unknown) => board.removeCard(old, id) },
        { queryKey: leadsKeys.lists, match: 'prefix', optimistic: (old: unknown) => infiniteOps.remove(old, id) },
        { queryKey: leadsKeys.detail(id) },
      ],
    });
  }

  /** `toIndex` is the destination index inside the stage's column (0 = top), as the kanban `onMove` reports it. */
  function useMoveLead() {
    return useCacheWriteMutation<Lead, { id: string; stage: string; toIndex?: number }>({
      mutationFn: ({ id, stage, toIndex }) => unwrap<Lead>(api.post(`${BASE}/${id}/move`, { stage, position: toIndex ?? 0 })),
      targets: ({ id, stage, toIndex }) => [
        {
          queryKey: leadsKeys.boards,
          match: 'prefix',
          // The card lands under the cursor now; its own `stage` follows so the NEXT drag starts from the right column.
          optimistic: (old: unknown) => board.patchCard(board.moveCard(old, id, stage, toIndex), id, { stage }),
          commit: (old: unknown, saved: Lead) => board.patchCard(old, saved.id, saved),
        },
        {
          queryKey: leadsKeys.lists,
          match: 'prefix',
          optimistic: (old: unknown) => infiniteOps.patch(old, id, { stage }),
          commit: (old: unknown, saved: Lead) => infiniteOps.replace(old, saved.id, saved),
        },
        {
          queryKey: leadsKeys.detail(id),
          optimistic: (old: Lead | undefined) => (old ? { ...old, stage } : old),
          commit: (old: Lead | undefined, saved: Lead) => (old === undefined ? undefined : saved),
        },
      ],
    });
  }

  return { useLeadsConfig, useLeadsBoard, useLeadsList, useLead, useCreateLead, useUpdateLead, useDeleteLead, useMoveLead };
}

export type LeadsHooks = ReturnType<typeof createLeadsHooks>;
