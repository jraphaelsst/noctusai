/**
 * Equipe — the agency's LOGIN accounts + pending invites (not to be confused
 * with Profissionais/Custos — see `00-plataforma.md § 0.4`). Backend: the
 * seed's standard team router (`standard_routers=["team"]` in
 * `app/main.py`), not igig-specific code.
 *
 *   GET    /api/team                    → {data: Member[]}
 *   GET    /api/team/invitations        → {data: Invitation[]}   (admin)
 *   POST   /api/team/invite             {email, role}            (owner/admin/manager)
 *   DELETE /api/team/{id}                                        (admin)
 *   DELETE /api/team/invitations/{id}                            (admin)
 *
 * TanStack Query per the platform convention — Equipe.tsx used to hand-roll
 * `useEffect`+`useState` fetching with no cache, no retry, and a silently
 * swallowed invitations error (achado #18).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrapData } from "@/lib/api";

export interface Member {
  id: string;
  nome: string;
  email: string;
  role: string;
  org_role: string;
  avatar_url?: string;
  created_at: string;
}

export interface Invitation {
  id: string;
  email: string;
  role: string;
  status: string;
  created_at: string;
  expires_at: string;
}

export const EQUIPE_QUERY_KEY = ["igig", "equipe"] as const;
const MEMBROS_KEY = [...EQUIPE_QUERY_KEY, "membros"] as const;
const CONVITES_KEY = [...EQUIPE_QUERY_KEY, "convites"] as const;

export function useMembros() {
  const query = useQuery({
    queryKey: MEMBROS_KEY,
    queryFn: () => api.get("/api/team").then(unwrapData<Member[]>),
  });
  return {
    ...query,
    membros: query.data ?? [],
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

/**
 * Pending invitations — admin-only (403 for a non-admin). A failure here
 * used to be swallowed to `[]` with no error shown at all (achado #18): the
 * page looked like "no pending invites" when it was really "could not load
 * them".
 */
export function useConvitesPendentes(podeVer: boolean) {
  const query = useQuery({
    queryKey: CONVITES_KEY,
    queryFn: () => api.get("/api/team/invitations").then(unwrapData<Invitation[]>),
    enabled: podeVer,
  });
  return {
    ...query,
    convites: query.data ?? [],
    showSkeleton: podeVer && query.isPending && !query.data,
  };
}

export function useConvidar() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { email: string; role: string }) =>
      api.post("/api/team/invite", payload).then(unwrapData<Invitation>),
    onSuccess: () => qc.invalidateQueries({ queryKey: CONVITES_KEY }),
  });
}

export function useCancelarConvite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/team/invitations/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: CONVITES_KEY }),
  });
}

export function useRemoverMembro() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/team/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: MEMBROS_KEY }),
  });
}
