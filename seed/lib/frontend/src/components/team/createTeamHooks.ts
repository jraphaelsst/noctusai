/**
 * `createTeamHooks(api)` — the seed `/api/team` router, as TanStack Query v5
 * hooks. Pairs with the `<TeamPage/>` organ (same directory).
 *
 * Contract (seed `noctusai_seed.routers._create_team_router` + `TeamPolicy`):
 *
 *   GET    /api/team                    → { data: TeamMember[] }   staff-only roster
 *   GET    /api/team/policy             → TeamPolicyContract       role vocabulary
 *   GET    /api/team/invitations        → { data: TeamInvitation[] } (owner/admin)
 *   POST   /api/team/invite             → { email, role } → TeamInviteResponse
 *   DELETE /api/team/invitations/{id}   → { ok: true }
 *
 * `DELETE /api/team/{id}` is deliberately NOT wrapped: removal from the org is a
 * NoctusAI Core action (the route always answers 409 `TEAM_REMOVE_CORE_ONLY`).
 *
 * 🔴 TWO loading signals, never `isLoading` and never a bare `isFetching`
 * (`KB § PATTERNS/frontend/lying-loading-state.md`): every query hook returns
 * `showSkeleton` (first load only) + `isRefreshing` (refetch over data on
 * screen). An invite/cancel invalidates these queries; gating on `isFetching`
 * alone would blank a populated table on every write.
 *
 * Same injection pattern as `createApiKeysHooks`: the product passes its own
 * authenticated api client.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { ApiClient } from '../../api';

// ---------------------------------------------------------------------------
// Types — mirror the seed team router verbatim.
// ---------------------------------------------------------------------------

/** One roster row (`_TEAM_MEMBER_COLUMNS`). */
export interface TeamMember {
  id: string;
  email: string;
  nome: string | null;
  org_id?: string | null;
  org_role: string | null;
  role?: string | null;
  avatar_url?: string | null;
  created_at: string | null;
  last_active_at?: string | null;
}

/** One pending invitation (`noctusai_lib.domain.invitations`). */
export interface TeamInvitation {
  id: string;
  email: string;
  role: string;
  status?: string;
  created_at?: string | null;
  expires_at?: string | null;
}

/** `GET /api/team/policy` — `TeamPolicy.as_contract()`. */
export interface TeamPolicyContract {
  staff_roles: string[];
  invitable_roles: string[];
  labels: Record<string, string>;
}

/**
 * `POST /api/team/invite`. `email_enviado` is the TRUTH about the e-mail: the
 * invitation row can exist while no e-mail went out (provider unconfigured or
 * a send failure) — `email_motivo` says why.
 */
export interface TeamInviteResponse {
  data: TeamInvitation & { token?: string };
  email_enviado: boolean;
  email_motivo?: string;
}

export interface TeamInviteBody {
  email: string;
  role: string;
}

/** The minimal client shape these hooks need (the seed `ApiClient` satisfies it). */
export type TeamApi = Pick<ApiClient, 'get' | 'post' | 'delete'>;

export const TEAM_QUERY_KEYS = {
  roster: ['team', 'roster'] as const,
  policy: ['team', 'policy'] as const,
  invitations: ['team', 'invitations'] as const,
};

/** The two loading signals, derived off `data` (never `isLoading`). */
function loadingSignals<T extends { isPending: boolean; isFetching: boolean; data: unknown }>(
  query: T,
): T & { showSkeleton: boolean; isRefreshing: boolean } {
  const hasData = query.data !== undefined && query.data !== null;
  return {
    ...query,
    showSkeleton: query.isPending && !hasData,
    isRefreshing: query.isFetching && hasData,
  };
}

function errorMessage(err: unknown, fallback: string): string {
  const msg = (err as { message?: unknown } | null)?.message;
  return typeof msg === 'string' && msg ? msg : fallback;
}

export function createTeamHooks(api: TeamApi) {
  function useTeamRoster(enabled = true) {
    const query = useQuery<TeamMember[]>({
      queryKey: TEAM_QUERY_KEYS.roster,
      queryFn: async () => (await api.get<{ data: TeamMember[] }>('/api/team')).data ?? [],
      enabled,
    });
    return loadingSignals(query);
  }

  function useTeamPolicy(enabled = true) {
    const query = useQuery<TeamPolicyContract>({
      queryKey: TEAM_QUERY_KEYS.policy,
      queryFn: () => api.get<TeamPolicyContract>('/api/team/policy'),
      enabled,
      staleTime: 5 * 60 * 1000,
    });
    return loadingSignals(query);
  }

  /** Owner/admin only server-side — pass `enabled` from the caller's gate. */
  function useTeamInvitations(enabled = true) {
    const query = useQuery<TeamInvitation[]>({
      queryKey: TEAM_QUERY_KEYS.invitations,
      queryFn: async () =>
        (await api.get<{ data: TeamInvitation[] }>('/api/team/invitations')).data ?? [],
      enabled,
    });
    return loadingSignals(query);
  }

  /**
   * POST /api/team/invite. The toast tells the e-mail truth: success only when
   * `email_enviado`, otherwise a warning carrying `email_motivo` — the
   * invitation exists, but nobody was told about it.
   */
  function useInviteMember() {
    const qc = useQueryClient();
    return useMutation<TeamInviteResponse, unknown, TeamInviteBody>({
      mutationFn: (body) => api.post<TeamInviteResponse>('/api/team/invite', body),
      onSuccess: (res, body) => {
        if (res.email_enviado) {
          toast.success(`Convite enviado para ${body.email}.`);
        } else {
          toast.warning('Convite criado, mas o e-mail não foi enviado.', {
            description: `${res.email_motivo ?? 'Motivo desconhecido'}. O convite aparece em "Convites pendentes".`,
          });
        }
        void qc.invalidateQueries({ queryKey: TEAM_QUERY_KEYS.invitations });
      },
      onError: (err) => {
        toast.error('Erro ao enviar convite', {
          description: errorMessage(err, 'Tente novamente.'),
        });
      },
    });
  }

  function useCancelInvitation() {
    const qc = useQueryClient();
    return useMutation<unknown, unknown, string>({
      mutationFn: (id) => api.delete(`/api/team/invitations/${encodeURIComponent(id)}`),
      onSuccess: () => {
        toast.success('Convite cancelado.');
        void qc.invalidateQueries({ queryKey: TEAM_QUERY_KEYS.invitations });
      },
      onError: (err) => {
        toast.error('Erro ao cancelar convite', {
          description: errorMessage(err, 'Tente novamente.'),
        });
      },
    });
  }

  return {
    useTeamRoster,
    useTeamPolicy,
    useTeamInvitations,
    useInviteMember,
    useCancelInvitation,
  };
}

export type TeamHooks = ReturnType<typeof createTeamHooks>;
