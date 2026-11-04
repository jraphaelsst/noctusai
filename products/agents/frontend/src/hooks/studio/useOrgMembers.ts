/**
 * The org's members (name + id) for the evaluation-mode picker. Source: the seed's `/api/team` roster
 * (the same one the core Equipe page reads). Any member may read it; the server scopes it to the org.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { OrgMember } from "@/api/studio/types-julia";
import { toView } from "./keys";

export function useOrgMembers(enabled = true) {
  const q = useQuery<OrgMember[]>({
    queryKey: ["studio", "__org__", "members"],
    queryFn: async () => (await api.get<{ data: OrgMember[] }>("/api/team")).data ?? [],
    enabled,
    retry: false,
    placeholderData: (prev) => prev,
  });
  return toView(q);
}
