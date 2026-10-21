/**
 * `createPartiesHooks(api)` — TanStack Query hooks for the parties staff API (`/api/parties`).
 *
 * Transport: an already-authenticated seed `ApiClient` (the host's `createApiClient()`); `{data}` /
 * `{data, pagination}` envelopes are unwrapped here.
 *
 * 🔴 Loading contract (`KB § PATTERNS/frontend/lying-loading-state.md`): every read hook returns
 * `showSkeleton = isPending && !data` (first load only) and `isRefreshing = isFetching && !!data`
 * (indicator only, never an early return). Never `isLoading`, never a bare `isFetching` gate. The
 * list keeps `placeholderData` across key changes (page / filters / search). The by-id read does
 * NOT: it is personal data keyed by id, and showing the previous person under a new key would leak it.
 *
 * Errors are never swallowed: queries expose `error`, mutations reject with `ApiError` so the
 * caller renders it (409 `documento_duplicado`, 409 `parceiro_em_uso`, 422 `documento_invalido`...).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCacheWriteMutation } from '../cache-writes';
import { envelopeOps } from '../organ-kit/cacheOps';
import { ApiError, type ApiClient } from '../api';
import { apiErrorCode, errorMessage, keep, signals } from '../organ-kit/query';
import type {
  PartiesImportResult,
  PartiesPaginated,
  PartiesEnvelope,
  PartiesListParams,
  Party,
  PartyInput,
  PartyPatch,
  PartyRole,
} from './types';

/** The subset of the seed `ApiClient` the parties hooks need. */
export type PartiesApi = Pick<ApiClient, 'get' | 'post' | 'put' | 'patch' | 'delete' | 'upload' | 'download'>;

const BASE = '/api/parties';

/** Namespaced query keys (exported so hosts can invalidate precisely). */
export const partiesKeys = {
  all: ['parties'] as const,
  lists: ['parties', 'list'] as const,
  list: (params: PartiesListParams) => ['parties', 'list', params] as const,
  detail: (id: string) => ['parties', 'detail', id] as const,
};

export { apiErrorCode, errorMessage };


/** The query string of a list / export request (empty filters are not sent). `active` maps to `?active=true|false`. */
export function listQuery(params: PartiesListParams): Record<string, string | number | boolean> {
  const out: Record<string, string | number | boolean> = {};
  if (params.q?.trim()) out.q = params.q.trim();
  if (params.kind) out.kind = params.kind;
  if (params.role) out.role = params.role;
  if (params.active === 'active') out.active = true;
  if (params.active === 'archived') out.active = false;
  if (params.page) out.page = params.page;
  if (params.page_size) out.page_size = params.page_size;
  return out;
}

export function createPartiesHooks(api: PartiesApi) {
  const unwrap = async <T,>(p: Promise<PartiesEnvelope<T>>): Promise<T> => (await p).data;

  /**
   * The server's answer for ONE party goes into its detail and into every cached list page that already
   * shows it. Whether a NEW party belongs on a given filtered/paged list is the server's call, so a create
   * only seeds its detail and the settle refetch places it in the lists.
   */
  const savedTargets = (id: string) => [
    {
      queryKey: partiesKeys.lists,
      match: 'prefix' as const,
      commit: (old: any, saved: Party) => envelopeOps.patch(old, id, saved),
    },
    { queryKey: partiesKeys.detail(id), commit: (old: Party | undefined, saved: Party) => (old === undefined ? undefined : saved) },
  ];

  function useParties(params: PartiesListParams = {}) {
    const q = useQuery<PartiesPaginated<Party>>({
      queryKey: partiesKeys.list(params),
      queryFn: () => api.get(BASE, listQuery(params)),
      placeholderData: keep,
    });
    return signals(q);
  }

  function useParty(id: string | null | undefined) {
    // Personal data keyed by id: no placeholderData (would show a previous person's data).
    const q = useQuery<Party>({
      queryKey: partiesKeys.detail(id ?? ''),
      queryFn: () => unwrap(api.get(`${BASE}/${id}`)),
      enabled: !!id,
    });
    return signals(q);
  }

  function useCreateParty() {
    const qc = useQueryClient();
    return useCacheWriteMutation<Party, PartyInput>({
      mutationFn: (body) => unwrap<Party>(api.post(BASE, body)),
      // Placement in a filtered / paged list is the server's call: lists converge on the settle refetch.
      targets: [{ queryKey: partiesKeys.lists, match: 'prefix' }],
      // The new party's detail is known now — opening it needs no round trip.
      onSuccess: (saved) => {
        qc.setQueryData(partiesKeys.detail(saved.id), saved);
      },
    });
  }

  function useUpdateParty() {
    return useCacheWriteMutation<Party, { id: string } & PartyPatch>({
      mutationFn: ({ id, ...body }) => unwrap<Party>(api.patch(`${BASE}/${id}`, body)),
      targets: ({ id }) => savedTargets(id),
    });
  }

  function useSetRoles() {
    return useCacheWriteMutation<Party, { id: string; roles: PartyRole[] }>({
      mutationFn: ({ id, roles }) => unwrap<Party>(api.put(`${BASE}/${id}/roles`, { roles })),
      targets: ({ id }) => savedTargets(id),
    });
  }

  function useArchiveParty() {
    return useCacheWriteMutation<Party, { id: string; restore: boolean }>({
      mutationFn: ({ id, restore }) => unwrap<Party>(api.post(`${BASE}/${id}/${restore ? 'restore' : 'archive'}`, {})),
      // Archiving moves the party between the active / archived lists: the server's row lands in every
      // page that shows it, the settle refetch re-filters the lists.
      targets: ({ id }) => savedTargets(id),
    });
  }

  function useDeleteParty() {
    return useCacheWriteMutation<unknown, string>({
      mutationFn: (id) => api.delete(`${BASE}/${id}`),
      targets: (id) => [
        { queryKey: partiesKeys.lists, match: 'prefix', optimistic: (old: any) => envelopeOps.remove(old, id) },
        { queryKey: partiesKeys.detail(id) },
      ],
    });
  }

  /** `POST /import` (multipart). `dryRun` validates without writing. Resolves with the row-level report. */
  function useImportParties() {
    const qc = useQueryClient();
    return useMutation({ // noc-allow: invalidate-only — a bulk import returns a row-level report, not the created parties; the server decides which rows land in which filtered / paged list
      mutationFn: ({ file, dryRun }: { file: File; dryRun?: boolean }) => {
        const form = new FormData();
        form.append('file', file);
        form.append('dry_run', dryRun ? 'true' : 'false');
        return unwrap<PartiesImportResult>(api.upload(`${BASE}/import`, form));
      },
      onSuccess: (result) => (result.dry_run ? undefined : qc.invalidateQueries({ queryKey: partiesKeys.lists })),
    });
  }

  /** `GET /export.csv` with the same filters as the list. Resolves with the CSV `Blob`. */
  function useExportParties() {
    return useMutation({ // noc-allow: invalidate-only — a CSV download: it reads and writes nothing any cached query shows
      mutationFn: (params: PartiesListParams = {}) => {
        const { page: _page, page_size: _size, ...filters } = listQuery(params) as Record<string, string | number | boolean>;
        const qs = new URLSearchParams(Object.entries(filters).map(([k, v]) => [k, String(v)])).toString();
        return api.download(`${BASE}/export.csv${qs ? `?${qs}` : ''}`);
      },
    });
  }

  return {
    useParties,
    useParty,
    useCreateParty,
    useUpdateParty,
    useSetRoles,
    useArchiveParty,
    useDeleteParty,
    useImportParties,
    useExportParties,
  };
}

export type PartiesHooks = ReturnType<typeof createPartiesHooks>;
