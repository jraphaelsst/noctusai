/**
 * Agent Studio — client brains (CONTRACT §D2):
 *   GET/POST   /api/studio/agents/{key}/clients
 *   GET/PATCH  /api/studio/agents/{key}/clients/{client_id}
 *   POST       /api/studio/agents/{key}/clients/{client_id}/entries
 *   PATCH/DELETE .../clients/{client_id}/entries/{entry_id}
 *
 * A client's `resumo` + active entries are compiled into the
 * `# Cliente em foco` block (§C.5), so every write here also invalidates the
 * agent's compiled views.
 *
 * Request bodies are not spelled out by §D2; `types.ts` documents the chosen
 * shape (the §B1 writable columns).
 */
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  Client,
  ClientCreateInput,
  ClientEntry,
  ClientEntryCreateInput,
  ClientEntryPatchInput,
  ClientListResponse,
  ClientPatchInput,
} from "@/api/studio/types";
import { keepWithinAgent, seg, studioKeys, toView } from "./keys";

const base = (key: string) => `/api/studio/agents/${seg(key)}/clients`;

function afterClientWrite(qc: QueryClient, key: string, clientId?: string) {
  void qc.invalidateQueries({ queryKey: studioKeys.clients(key), exact: true });
  if (clientId) void qc.invalidateQueries({ queryKey: studioKeys.client(key, clientId) });
  void qc.invalidateQueries({ queryKey: studioKeys.compiledAll(key) });
}

export function useClients(key: string) {
  const q = useQuery<ClientListResponse>({
    queryKey: studioKeys.clients(key),
    queryFn: () => api.get<ClientListResponse>(base(key)),
    enabled: !!key,
    placeholderData: keepWithinAgent<ClientListResponse>(key),
  });
  const view = toView(q);
  return { ...view, data: q.data?.items };
}

export function useClient(key: string, clientId: string | null) {
  const q = useQuery<Client>({
    queryKey: studioKeys.client(key, clientId ?? ""),
    queryFn: () => api.get<Client>(`${base(key)}/${seg(clientId as string)}`),
    enabled: !!key && !!clientId,
    placeholderData: keepWithinAgent<Client>(key),
  });
  return toView(q);
}

export function useCreateClient(key: string) {
  const qc = useQueryClient();
  return useMutation<Client, unknown, ClientCreateInput>({
    mutationFn: (payload) => api.post<Client>(base(key), payload),
    onSuccess: (created) => {
      qc.setQueryData(studioKeys.client(key, created.id), created);
      afterClientWrite(qc, key);
    },
  });
}

export function useUpdateClient(key: string) {
  const qc = useQueryClient();
  return useMutation<Client, unknown, { clientId: string; patch: ClientPatchInput }>({
    mutationFn: ({ clientId, patch }) => api.patch<Client>(`${base(key)}/${seg(clientId)}`, patch),
    onSuccess: (updated) => {
      qc.setQueryData(studioKeys.client(key, updated.id), updated);
      afterClientWrite(qc, key);
    },
  });
}

export function useCreateClientEntry(key: string) {
  const qc = useQueryClient();
  return useMutation<ClientEntry, unknown, { clientId: string; entry: ClientEntryCreateInput }>({
    mutationFn: ({ clientId, entry }) => api.post<ClientEntry>(`${base(key)}/${seg(clientId)}/entries`, entry),
    onSuccess: (_e, { clientId }) => afterClientWrite(qc, key, clientId),
  });
}

export function useUpdateClientEntry(key: string) {
  const qc = useQueryClient();
  return useMutation<ClientEntry, unknown, { clientId: string; entryId: string; patch: ClientEntryPatchInput }>({
    mutationFn: ({ clientId, entryId, patch }) =>
      api.patch<ClientEntry>(`${base(key)}/${seg(clientId)}/entries/${seg(entryId)}`, patch),
    onSuccess: (_e, { clientId }) => afterClientWrite(qc, key, clientId),
  });
}

export function useDeleteClientEntry(key: string) {
  const qc = useQueryClient();
  return useMutation<null, unknown, { clientId: string; entryId: string }>({
    mutationFn: ({ clientId, entryId }) => api.delete<null>(`${base(key)}/${seg(clientId)}/entries/${seg(entryId)}`),
    onSuccess: (_e, { clientId }) => afterClientWrite(qc, key, clientId),
  });
}
