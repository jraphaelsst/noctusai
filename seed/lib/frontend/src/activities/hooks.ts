/**
 * `createActivitiesHooks(api)` — TanStack Query hooks for the activities API (`/api/activities`).
 *
 * 🔴 Loading contract (`KB § PATTERNS/frontend/lying-loading-state.md`): every read hook returns
 * `showSkeleton = isPending && !data` (first load only) and `isRefreshing = isFetching && !!data` (indicator only).
 * Never `isLoading`. A list whose key changes inside one scope (the caller's own tasks, another filter) keeps
 * `placeholderData: keep`; the entity-keyed list does NOT (another card's tasks must never show under this one).
 *
 * 🔴 Writes (`KB § PATTERNS/frontend/mutation-cache-writes.md`, skill `noc-cache-writes`): every mutation draws its change
 * into every cached list where the row already is (optimistic where the outcome is certain), writes the SERVER's row on the
 * answer, and settles in the background. A completed task is drawn done on the click; the "open" list drops it on the settle
 * refetch (so it can still be undone). Mutations reject with `ApiError`; `activitiesErrorMessage` maps the stable codes.
 */
import { useQuery } from '@tanstack/react-query';
import { pageOps, useCacheWriteMutation, type CacheWriteTarget } from '../cache-writes';
import { ApiError, type ApiClient } from '../api';
import { errorMessage, keep, signals } from '../organ-kit/query';
import { defaultActivitiesT, type ActivitiesTranslate } from './i18n';
import type {
  Activity,
  ActivitiesEnvelope,
  ActivitiesPage,
  ActivityEvent,
  ActivityInput,
  ActivityListParams,
  ActivityOutcome,
  ActivityType,
} from './types';

export type ActivitiesApi = Pick<ApiClient, 'get' | 'post' | 'patch'>;

const BASE = '/api/activities';

/** Namespaced query keys (exported so hosts can invalidate precisely). */
export const activitiesKeys = {
  all: ['activities'] as const,
  list: ['activities', 'list'] as const,
  mine: ['activities', 'mine'] as const,
  types: ['activities', 'types'] as const,
  events: ['activities', 'events'] as const,
};

export { errorMessage };

/** pt-BR copy for the stable backend error codes; falls back to the server message. */
export function activitiesErrorMessage(err: unknown, t: ActivitiesTranslate = defaultActivitiesT): string {
  if (err instanceof ApiError && err.code) {
    const mapped = t(`error.${err.code}`);
    if (mapped !== `error.${err.code}`) return mapped;
  }
  return errorMessage(err);
}

const nowIso = () => new Date().toISOString();

/** Server order of the OPEN list: due date ascending, no due date last, then newest first. */
const byDueThenNewest = (a: Activity, b: Activity): number => {
  if (a.due_at && b.due_at) return a.due_at < b.due_at ? -1 : a.due_at > b.due_at ? 1 : 0;
  if (a.due_at) return -1;
  if (b.due_at) return 1;
  return a.created_at < b.created_at ? 1 : -1;
};

type ListKey = readonly unknown[];
const paramsOf = (key: ListKey | undefined): ActivityListParams => ((key?.[2] as ActivityListParams | null | undefined) ?? {});

export function createActivitiesHooks(api: ActivitiesApi) {
  const unwrap = async <T,>(p: Promise<ActivitiesEnvelope<T>>): Promise<T> => (await p).data;

  /** Entity-keyed list (a card's tab). No placeholder across entities. */
  function useActivities(params: ActivityListParams | null) {
    const q = useQuery<ActivitiesPage<Activity>>({
      queryKey: [...activitiesKeys.list, params],
      queryFn: () => api.get(BASE, params ?? {}),
      enabled: !!params,
    });
    return signals(q);
  }

  /** The caller's own activities (`/mine`). Filter changes keep the previous rows on screen. */
  function useMyActivities(params: Omit<ActivityListParams, 'assignee_id'> = {}) {
    const q = useQuery<ActivitiesPage<Activity>>({
      queryKey: [...activitiesKeys.mine, params],
      queryFn: () => api.get(`${BASE}/mine`, params),
      placeholderData: keep,
    });
    return signals(q);
  }

  function useActivityTypes(params: { active?: boolean } = { active: true }) {
    const q = useQuery<ActivityType[]>({
      queryKey: [...activitiesKeys.types, params],
      queryFn: () => unwrap(api.get(`${BASE}/types`, params)),
      placeholderData: keep,
    });
    return signals(q);
  }

  /** The immutable history of ONE activity (id-keyed: no placeholder across activities). */
  function useActivityEvents(activityId: string | null) {
    const q = useQuery<ActivityEvent[]>({
      queryKey: [...activitiesKeys.events, activityId],
      queryFn: () => unwrap(api.get(`${BASE}/${activityId}/events`)),
      enabled: !!activityId,
    });
    return signals(q);
  }

  /** Every cached list (entity-keyed AND mine) that already shows row `id`: draw `changes` now, write the server row after. */
  function rowTargets(id: string, changes?: Partial<Activity>): CacheWriteTarget<Activity, unknown>[] {
    const target = (queryKey: readonly unknown[]): CacheWriteTarget<Activity, unknown> => ({
      queryKey,
      match: 'prefix',
      optimistic: changes ? (old: unknown) => pageOps.patch(old, id, changes) : undefined,
      commit: (old: unknown, saved: Activity) => pageOps.replace(old, id, saved),
    });
    return [target(activitiesKeys.list), target(activitiesKeys.mine), { queryKey: [...activitiesKeys.events, id] }];
  }

  function useActivityMutations() {
    const useVerb = <V extends { id: string }>(path: (v: V) => string, body: (v: V) => unknown, changes: (v: V) => Partial<Activity>) =>
      useCacheWriteMutation<Activity, V>({
        mutationFn: (v) => unwrap<Activity>(api.post(path(v), body(v))),
        targets: (v) => rowTargets(v.id, changes(v)) as CacheWriteTarget<Activity, V>[],
      });

    return {
      /**
       * A new activity is drawn into the cached lists of ITS card (and not into another card's) once the server answers;
       * where it sits is the list's own order (newest first for "all", due date for "open"). The caller's `mine` list converges
       * on the background settle (whether it is theirs is the server's call).
       */
      create: useCacheWriteMutation<Activity, ActivityInput>({
        mutationFn: (b) => unwrap<Activity>(api.post(BASE, b)),
        targets: (vars) => [
          {
            queryKey: activitiesKeys.list,
            match: 'prefix',
            predicate: (key) => {
              const p = paramsOf(key);
              return p.entity_id === vars.entity_id && (p.entity_kind ?? vars.entity_kind) === vars.entity_kind && p.status !== 'done' && p.status !== 'cancelled';
            },
            commit: (old: unknown, saved: Activity, _v, _c, key) =>
              (paramsOf(key).status ?? 'open') === 'open' ? pageOps.insertSorted(old, saved, byDueThenNewest) : pageOps.prependNewest(old, saved),
          },
        ],
        invalidate: [activitiesKeys.mine],
      }),
      complete: useVerb<{ id: string; outcome?: ActivityOutcome }>(
        (v) => `${BASE}/${v.id}/complete`,
        (v) => ({ outcome: v.outcome ?? 'realizada' }),
        (v) => ({ done_at: nowIso(), outcome: v.outcome ?? 'realizada', overdue: false }),
      ),
      reopen: useVerb<{ id: string }>((v) => `${BASE}/${v.id}/reopen`, () => ({}), () => ({ done_at: null, done_by: null, outcome: null })),
      cancel: useVerb<{ id: string }>((v) => `${BASE}/${v.id}/cancel`, () => ({}), () => ({ cancelled_at: nowIso(), overdue: false })),
      reassign: useVerb<{ id: string; assignee_id: string | null }>(
        (v) => `${BASE}/${v.id}/reassign`,
        (v) => ({ assignee_id: v.assignee_id }),
        (v) => ({ assignee_id: v.assignee_id }),
      ),
      reschedule: useVerb<{ id: string; due_at: string | null }>(
        (v) => `${BASE}/${v.id}/reschedule`,
        (v) => ({ due_at: v.due_at }),
        (v) => ({ due_at: v.due_at }),
      ),
      edit: useCacheWriteMutation<Activity, { id: string; title?: string; notes?: string | null }>({
        mutationFn: ({ id, ...b }) => unwrap<Activity>(api.patch(`${BASE}/${id}`, b)),
        targets: ({ id, ...changes }) => rowTargets(id, changes as Partial<Activity>) as CacheWriteTarget<Activity, { id: string }>[],
      }),
    };
  }

  return { useActivities, useMyActivities, useActivityTypes, useActivityEvents, useActivityMutations };
}

export type ActivitiesHooks = ReturnType<typeof createActivitiesHooks>;
