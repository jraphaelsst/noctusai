/**
 * Client ("client brain") hooks — Agent Studio CONTRACT.md §D2.
 *
 * §D2 is owned by slice FE-DEF (`src/hooks/studio/useClients.ts`), but that
 * file is not on this branch (parallel slice, contract §J2.4) — FE-KE needs
 * clients for both the Clients tab (full CRUD) and the Conversar tab's
 * client selector, so this is FE-KE's OWN reader, deliberately named
 * `useClientsKe` per CONTRACT.md §J to avoid a path collision with
 * FE-DEF's eventual `useClients.ts` at merge time.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  ClientCreate,
  ClientDetail,
  ClientEntryCreate,
  ClientEntryPatch,
  ClientListResponse,
  ClientPatch,
} from "@/api/studio/types-ke";

const listKey = (agentKey: string) => ["studio", agentKey, "clients"] as const;
const detailKey = (agentKey: string, clientId: string) => ["studio", agentKey, "clients", clientId] as const;

export function useClientsKe(agentKey: string) {
  const query = useQuery<ClientListResponse>({
    queryKey: listKey(agentKey),
    queryFn: () => api.get<ClientListResponse>(`/api/studio/agents/${agentKey}/clients`),
    enabled: !!agentKey,
  });

  return {
    data: query.data?.items,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
    isError: query.isError,
    error: query.error,
  };
}

export function useClientKe(agentKey: string, clientId: string | null) {
  const query = useQuery<ClientDetail>({
    queryKey: detailKey(agentKey, clientId ?? ""),
    queryFn: () => api.get<ClientDetail>(`/api/studio/agents/${agentKey}/clients/${clientId}`),
    enabled: !!agentKey && !!clientId,
  });

  return {
    data: query.data,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
    isError: query.isError,
    error: query.error,
  };
}

export function useCreateClientKe(agentKey: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ClientCreate) => api.post<ClientDetail>(`/api/studio/agents/${agentKey}/clients`, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: listKey(agentKey) }),
  });
}

export function useUpdateClientKe(agentKey: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ clientId, patch }: { clientId: string; patch: ClientPatch }) =>
      api.patch<ClientDetail>(`/api/studio/agents/${agentKey}/clients/${clientId}`, patch),
    onSuccess: (updated) => {
      qc.setQueryData(detailKey(agentKey, updated.id), updated);
      qc.invalidateQueries({ queryKey: listKey(agentKey) });
    },
  });
}

export function useCreateClientEntry(agentKey: string, clientId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ClientEntryCreate) =>
      api.post(`/api/studio/agents/${agentKey}/clients/${clientId}/entries`, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: detailKey(agentKey, clientId) });
      qc.invalidateQueries({ queryKey: listKey(agentKey) });
    },
  });
}

export function useUpdateClientEntry(agentKey: string, clientId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ entryId, patch }: { entryId: string; patch: ClientEntryPatch }) =>
      api.patch(`/api/studio/agents/${agentKey}/clients/${clientId}/entries/${entryId}`, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: detailKey(agentKey, clientId) }),
  });
}

export function useDeleteClientEntry(agentKey: string, clientId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (entryId: string) => api.delete(`/api/studio/agents/${agentKey}/clients/${clientId}/entries/${entryId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: detailKey(agentKey, clientId) });
      qc.invalidateQueries({ queryKey: listKey(agentKey) });
    },
  });
}
