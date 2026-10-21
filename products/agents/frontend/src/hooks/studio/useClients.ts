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
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
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

/** Derived views of a client write: the list's `total_entradas` and the compiled `# Cliente em foco` block. */
const afterEntryWrite = (key: string) => [studioKeys.clients(key), studioKeys.compiledAll(key)];

function afterClientWrite(qc: QueryClient, key: string) {
  void qc.invalidateQueries({ queryKey: studioKeys.clients(key), exact: true });
  void qc.invalidateQueries({ queryKey: studioKeys.compiledAll(key) });
}

/** Edit one cached client detail (`entradas`); the list/compiled views refresh behind. */
const clientTarget = <TData, TVars>(
  key: string,
  clientId: string,
  rest: {
    optimistic?: (entradas: ClientEntry[], vars: TVars, tempId: string) => ClientEntry[] | undefined;
    commit?: (entradas: ClientEntry[], result: TData, tempId: string) => ClientEntry[] | undefined;
  },
) => ({
  queryKey: studioKeys.client(key, clientId),
  optimistic: rest.optimistic
    ? (old: Client | undefined, vars: TVars, ctx: { tempId: string }) =>
        listOps.within(old, "entradas", (l) => rest.optimistic!(l, vars, ctx.tempId))
    : undefined,
  commit: rest.commit
    ? (old: Client | undefined, result: TData, _vars: TVars, ctx: { tempId: string }) =>
        listOps.within(old, "entradas", (l) => rest.commit!(l, result, ctx.tempId))
    : undefined,
});

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
  type Vars = { clientId: string; entry: ClientEntryCreateInput };
  // The server assigns id + created_at, so commit-only (the entry shows after one round trip).
  return useCacheWriteMutation<ClientEntry, Vars>({
    mutationFn: ({ clientId, entry }) => api.post<ClientEntry>(`${base(key)}/${seg(clientId)}/entries`, entry),
    targets: ({ clientId }) => [
      clientTarget<ClientEntry, Vars>(key, clientId, {
        commit: (l, saved, tempId) => listOps.replace(l, tempId, saved),
      }),
    ],
    invalidate: afterEntryWrite(key),
  });
}

export function useUpdateClientEntry(key: string) {
  type Vars = { clientId: string; entryId: string; patch: ClientEntryPatchInput };
  return useCacheWriteMutation<ClientEntry, Vars>({
    mutationFn: ({ clientId, entryId, patch }) =>
      api.patch<ClientEntry>(`${base(key)}/${seg(clientId)}/entries/${seg(entryId)}`, patch),
    targets: ({ clientId, entryId }) => [
      clientTarget<ClientEntry, Vars>(key, clientId, {
        optimistic: (l, { patch }) => listOps.patch(l, entryId, patch as Partial<ClientEntry>),
        commit: (l, saved) => listOps.replace(l, entryId, saved),
      }),
    ],
    invalidate: afterEntryWrite(key),
  });
}

export function useDeleteClientEntry(key: string) {
  type Vars = { clientId: string; entryId: string };
  return useCacheWriteMutation<null, Vars>({
    mutationFn: ({ clientId, entryId }) => api.delete<null>(`${base(key)}/${seg(clientId)}/entries/${seg(entryId)}`),
    targets: ({ clientId, entryId }) => [
      clientTarget<null, Vars>(key, clientId, { optimistic: (l) => listOps.remove(l, entryId) }),
    ],
    invalidate: afterEntryWrite(key),
  });
}
