import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

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

const TEAM_KEY = ["sw", "team"] as const;
const INVITES_KEY = ["sw", "team", "invitations"] as const;

export function useTeamMembers() {
  return useQuery({
    queryKey: TEAM_KEY,
    queryFn: async () => {
      const res = await api.get<{ data: Member[] }>("/api/team");
      return res.data ?? [];
    },
  });
}

export function useTeamInvitations() {
  return useQuery({
    queryKey: INVITES_KEY,
    queryFn: async () => {
      try {
        const res = await api.get<{ data: Invitation[] }>("/api/team/invitations");
        return res.data ?? [];
      } catch {
        return [];
      }
    },
  });
}

export function useInviteMember() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { email: string; role: "admin" | "member" }) =>
      api.post("/api/team/invite", payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TEAM_KEY });
      qc.invalidateQueries({ queryKey: INVITES_KEY });
    },
  });
}

export function useRemoveMember() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (memberId: string) => api.delete(`/api/team/${memberId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TEAM_KEY });
    },
  });
}

export function useCancelInvitation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (inviteId: string) => api.delete(`/api/team/invitations/${inviteId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: INVITES_KEY });
    },
  });
}
