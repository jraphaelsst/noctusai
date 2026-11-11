/**
 * `createAssignmentHooks(api)` — TanStack Query hooks for the assignment API (`/api/assignment`).
 *
 * 🔴 Loading contract (`KB § PATTERNS/frontend/lying-loading-state.md`): every read hook returns
 * `showSkeleton = isPending && !data` (first load only) and `isRefreshing = isFetching && !!data` (indicator only).
 * Never `isLoading`, never a bare `isFetching` gate.
 *
 * Writes follow `cache-writes` (`KB § PATTERNS/frontend/mutation-cache-writes.md`): the server answers every team write with the
 * whole `Team`, so that answer is written into the cached team list the moment it arrives (an edit is drawn on the click and rolled
 * back on a refusal); what the server derives (open counts in the workload, the events feed) refreshes in the background. A refusal
 * rejects with `ApiError`; `assignmentErrorMessage` maps the stable codes to pt-BR.
 */
import { useQuery } from '@tanstack/react-query';
import { listOps, useCacheWriteMutation } from '../cache-writes';
import { ApiError, type ApiClient } from '../api';
import { errorMessage, keep, signals } from '../organ-kit/query';
import { defaultAssignmentT, type AssignmentTranslate } from './i18n';
import type {
  AssignmentAssignInput,
  AssignmentAssignResult,
  AssignmentEnvelope,
  AssignmentEvent,
  AssignmentRule,
  AssignmentSettings,
  AssignmentEventsParams,
  AssignmentMemberInput,
  AssignmentMemberPatch,
  AssignmentReassignInput,
  AssignmentReleaseInput,
  AssignmentReleaseResult,
  AssignmentRuleInput,
  AssignmentSettingsPatch,
  SubjectAssignment,
  AssignmentTeam,
  AssignmentTeamInput,
  AssignmentTeamMember,
  AssignmentTeamPatch,
  AssignmentWorkloadRow,
} from './types';

export type AssignmentApi = Pick<ApiClient, 'get' | 'post' | 'put' | 'patch' | 'delete'>;

const BASE = '/api/assignment';

/** Namespaced query keys (exported so hosts can invalidate precisely). */
export const assignmentKeys = {
  all: ['assignment'] as const,
  settings: ['assignment', 'settings'] as const,
  teams: ['assignment', 'teams'] as const,
  rules: ['assignment', 'rules'] as const,
  workload: ['assignment', 'workload'] as const,
  events: ['assignment', 'events'] as const,
  subject: (kind: string, id: string) => ['assignment', 'subject', kind, id] as const,
};

export { errorMessage };

/** pt-BR copy for the stable backend error codes; falls back to the server message. */
export function assignmentErrorMessage(err: unknown, t: AssignmentTranslate = defaultAssignmentT): string {
  if (err instanceof ApiError && err.code) {
    const mapped = t(`error.${err.code}`);
    if (mapped !== `error.${err.code}`) return mapped;
  }
  return errorMessage(err);
}

/** The server sorts teams by lower-cased name: the cache keeps the same order, never a second sort in a component. */
export const compareAssignmentTeams = (a: AssignmentTeam, b: AssignmentTeam): number => a.name.toLowerCase().localeCompare(b.name.toLowerCase()) || a.id.localeCompare(b.id);

const compareRules = (a: AssignmentRule, b: AssignmentRule): number => a.kind.localeCompare(b.kind) || a.match_value.localeCompare(b.match_value);

function mapMembers(team: AssignmentTeam, fn: (members: AssignmentTeamMember[]) => AssignmentTeamMember[]): AssignmentTeam {
  return { ...team, members: fn(team.members) };
}

export function createAssignmentHooks(api: AssignmentApi) {
  const unwrap = async <T,>(p: Promise<AssignmentEnvelope<T>>): Promise<T> => (await p).data;

  function useSettings() {
    const q = useQuery<AssignmentSettings>({ queryKey: assignmentKeys.settings, queryFn: () => unwrap(api.get(`${BASE}/settings`)), placeholderData: keep });
    return signals(q);
  }
  function useTeams() {
    const q = useQuery<AssignmentTeam[]>({ queryKey: assignmentKeys.teams, queryFn: () => unwrap(api.get(`${BASE}/teams`)), placeholderData: keep });
    return signals(q);
  }
  function useRules() {
    const q = useQuery<AssignmentRule[]>({ queryKey: assignmentKeys.rules, queryFn: () => unwrap(api.get(`${BASE}/rules`)), placeholderData: keep });
    return signals(q);
  }
  /** Every org member with their open count and availability (also the member picker of a team). */
  function useWorkload() {
    const q = useQuery<AssignmentWorkloadRow[]>({ queryKey: assignmentKeys.workload, queryFn: () => unwrap(api.get(`${BASE}/workload`)), placeholderData: keep });
    return signals(q);
  }
  function useEvents(params: AssignmentEventsParams = {}) {
    const q = useQuery<AssignmentEvent[]>({
      queryKey: [...assignmentKeys.events, params],
      queryFn: () => unwrap(api.get(`${BASE}/events`, params)),
      placeholderData: keep,
    });
    return signals(q);
  }
  /** The current owner of ONE subject. 404 (no owner yet) is an answer, not a failure: `data` is null. */
  function useSubjectAssignment(kind: string | null, id: string | null) {
    const q = useQuery<SubjectAssignment | null>({
      queryKey: assignmentKeys.subject(kind ?? '', id ?? ''),
      queryFn: async () => {
        try {
          return await unwrap<SubjectAssignment>(api.get(`${BASE}/assignments/${kind}/${id}`));
        } catch (e) {
          if (e instanceof ApiError && e.status === 404) return null;
          throw e;
        }
      },
      enabled: !!kind && !!id,
    });
    return signals(q);
  }

  const derived = [assignmentKeys.workload, assignmentKeys.events];

  /** Settings: drawn on the click; the server's answer replaces it. A change of the default team may reset it server-side. */
  function useSettingsMutation() {
    return useCacheWriteMutation<AssignmentSettings, AssignmentSettingsPatch>({
      mutationFn: (b) => unwrap<AssignmentSettings>(api.put(`${BASE}/settings`, b)),
      targets: (b) => [
        {
          queryKey: assignmentKeys.settings,
          optimistic: (old: AssignmentSettings | undefined) => listOps.merge(old, b as Partial<AssignmentSettings>),
          commit: (_old: AssignmentSettings | undefined, saved: AssignmentSettings) => saved,
        },
      ],
    });
  }

  /**
   * AssignmentTeam writes. Every one answers with the whole `Team`, written into the cached list on arrival; removing a team also refreshes
   * what the server cascades (rules, default team, cursor, workload).
   */
  function useTeamMutations() {
    const teams = (extra: object = {}) => ({ queryKey: assignmentKeys.teams, ...extra });
    const swap = (old: AssignmentTeam[] | undefined, id: string, saved: AssignmentTeam) => listOps.replace(old, id, saved);
    return {
      create: useCacheWriteMutation<AssignmentTeam, AssignmentTeamInput>({
        mutationFn: (b) => unwrap<AssignmentTeam>(api.post(`${BASE}/teams`, b)),
        targets: [teams({ commit: (old: AssignmentTeam[] | undefined, saved: AssignmentTeam) => listOps.insertSorted(old, saved, compareAssignmentTeams) })],
        invalidate: [assignmentKeys.settings, assignmentKeys.workload],
      }),
      update: useCacheWriteMutation<AssignmentTeam, AssignmentTeamPatch & { id: string }>({
        mutationFn: ({ id, ...b }) => unwrap<AssignmentTeam>(api.patch(`${BASE}/teams/${id}`, b)),
        targets: ({ id, ...changes }) => [
          teams({
            optimistic: (old: AssignmentTeam[] | undefined) => listOps.patch(old, id, changes as Partial<AssignmentTeam>),
            commit: (old: AssignmentTeam[] | undefined, saved: AssignmentTeam) => listOps.insertSorted(listOps.remove(old, id), saved, compareAssignmentTeams),
          }),
        ],
      }),
      remove: useCacheWriteMutation<unknown, { id: string }>({
        mutationFn: ({ id }) => api.delete(`${BASE}/teams/${id}`), // 204: the client answers null
        targets: ({ id }) => [teams({ optimistic: (old: AssignmentTeam[] | undefined) => listOps.remove(old, id) })],
        invalidate: [assignmentKeys.settings, assignmentKeys.rules, assignmentKeys.workload],
      }),
      addMember: useCacheWriteMutation<AssignmentTeam, AssignmentMemberInput & { teamId: string }>({
        mutationFn: ({ teamId, ...b }) => unwrap<AssignmentTeam>(api.post(`${BASE}/teams/${teamId}/members`, b)),
        targets: ({ teamId }) => [teams({ commit: (old: AssignmentTeam[] | undefined, saved: AssignmentTeam) => swap(old, teamId, saved) })],
        invalidate: [assignmentKeys.workload],
      }),
      updateMember: useCacheWriteMutation<AssignmentTeam, AssignmentMemberPatch & { teamId: string; userId: string }>({
        mutationFn: ({ teamId, userId, ...b }) => unwrap<AssignmentTeam>(api.patch(`${BASE}/teams/${teamId}/members/${userId}`, b)),
        targets: ({ teamId, userId, ...changes }) => [
          teams({
            optimistic: (old: AssignmentTeam[] | undefined) =>
              listOps.update(old, teamId, (t) => mapMembers(t, (ms) => ms.map((m) => (m.user_id === userId ? { ...m, ...changes } : m)))),
            commit: (old: AssignmentTeam[] | undefined, saved: AssignmentTeam) => swap(old, teamId, saved),
          }),
        ],
        invalidate: [assignmentKeys.workload],
      }),
      removeMember: useCacheWriteMutation<unknown, { teamId: string; userId: string }>({
        mutationFn: ({ teamId, userId }) => api.delete(`${BASE}/teams/${teamId}/members/${userId}`),
        targets: ({ teamId, userId }) => [
          teams({ optimistic: (old: AssignmentTeam[] | undefined) => listOps.update(old, teamId, (t) => mapMembers(t, (ms) => ms.filter((m) => m.user_id !== userId))) }),
        ],
        invalidate: [assignmentKeys.workload],
      }),
      order: useCacheWriteMutation<AssignmentTeam, { teamId: string; order: string[] }>({
        mutationFn: ({ teamId, order }) => unwrap<AssignmentTeam>(api.put(`${BASE}/teams/${teamId}/order`, { order })),
        targets: ({ teamId, order }) => [
          teams({
            optimistic: (old: AssignmentTeam[] | undefined) =>
              listOps.update(old, teamId, (t) =>
                mapMembers(t, (ms) =>
                  order.map((uid, position) => ({ ...(ms.find((m) => m.user_id === uid) as AssignmentTeamMember), position })),
                ),
              ),
            commit: (old: AssignmentTeam[] | undefined, saved: AssignmentTeam) => swap(old, teamId, saved),
          }),
        ],
      }),
    };
  }

  /** Rules: an upsert per (kind, value), so the answer replaces the row with the same id or is inserted in the server's order. */
  function useRuleMutations() {
    return {
      put: useCacheWriteMutation<AssignmentRule, AssignmentRuleInput>({
        mutationFn: (b) => unwrap<AssignmentRule>(api.put(`${BASE}/rules`, b)),
        targets: [
          { queryKey: assignmentKeys.rules, commit: (old: AssignmentRule[] | undefined, saved: AssignmentRule) => listOps.insertSorted(old, saved, compareRules) },
        ],
      }),
      remove: useCacheWriteMutation<unknown, { id: string }>({
        mutationFn: ({ id }) => api.delete(`${BASE}/rules/${id}`),
        targets: ({ id }) => [{ queryKey: assignmentKeys.rules, optimistic: (old: AssignmentRule[] | undefined) => listOps.remove(old, id) }],
      }),
    };
  }

  /**
   * The verbs a host calls from its own screens (a lead card, an intake job). Each writes the answer into the subject's own cached
   * owner when it is cached; the derived views (workload open counts, team member counts, the events feed) refresh in the background.
   */
  function useAssignmentActions() {
    const subject = (v: { subject_kind: string; subject_id: string }) => assignmentKeys.subject(v.subject_kind, v.subject_id);
    const settle = [assignmentKeys.teams, ...derived];
    return {
      assign: useCacheWriteMutation<AssignmentAssignResult, AssignmentAssignInput>({
        mutationFn: (b) => unwrap<AssignmentAssignResult>(api.post(`${BASE}/assign`, b)),
        targets: (v) => [
          {
            queryKey: subject(v),
            commit: (old: SubjectAssignment | null | undefined, res: AssignmentAssignResult) =>
              res.assigned && old ? { ...old, user_id: res.user_id, team_id: res.team_id, strategy: res.strategy, criterion: res.criterion, closed_at: null } : undefined,
          },
        ],
        invalidate: settle,
      }),
      reassign: useCacheWriteMutation<AssignmentAssignResult, AssignmentReassignInput>({
        mutationFn: (b) => unwrap<AssignmentAssignResult>(api.post(`${BASE}/reassign`, b)),
        targets: (v) => [
          {
            queryKey: subject(v),
            optimistic: (old: SubjectAssignment | null | undefined) => (old ? { ...old, user_id: v.to_user_id } : undefined),
            commit: (old: SubjectAssignment | null | undefined, res: AssignmentAssignResult) =>
              res.assigned && old ? { ...old, user_id: res.user_id, team_id: res.team_id, strategy: res.strategy, criterion: res.criterion, closed_at: null } : undefined,
          },
        ],
        invalidate: settle,
      }),
      unassign: useCacheWriteMutation<AssignmentReleaseResult, AssignmentReleaseInput>({
        mutationFn: (b) => unwrap<AssignmentReleaseResult>(api.post(`${BASE}/unassign`, b)),
        targets: (v) => [{ queryKey: subject(v), optimistic: (old: SubjectAssignment | null | undefined) => (old ? null : undefined), commit: () => null }],
        invalidate: settle,
      }),
      close: useCacheWriteMutation<AssignmentReleaseResult, AssignmentReleaseInput>({
        mutationFn: (b) => unwrap<AssignmentReleaseResult>(api.post(`${BASE}/close`, b)),
        targets: (v) => [
          {
            queryKey: subject(v),
            commit: (old: SubjectAssignment | null | undefined, res: AssignmentReleaseResult) => (res.changed && old ? { ...old, closed_at: new Date().toISOString() } : undefined),
          },
        ],
        invalidate: settle,
      }),
    };
  }

  return {
    useSettings,
    useTeams,
    useRules,
    useWorkload,
    useEvents,
    useSubjectAssignment,
    useSettingsMutation,
    useTeamMutations,
    useRuleMutations,
    useAssignmentActions,
  };
}

export type AssignmentHooks = ReturnType<typeof createAssignmentHooks>;
