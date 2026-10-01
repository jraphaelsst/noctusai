import { useQuery } from "@tanstack/react-query";
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

const TEAM_KEY = ["sw", "team"] as const;

export function useTeamMembers() {
  return useQuery({
    queryKey: TEAM_KEY,
    queryFn: async () => {
      const res = await api.get<{ data: Member[] }>("/api/team");
      return res.data ?? [];
    },
  });
}
