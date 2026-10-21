/**
 * Propostas (lead-to-contract CONTRACT §4.2, §7.3). Own file — the roteiros
 * hooks belong to S3.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { contratosQueryKey } from "@/hooks/useContratos";
import type {
  AceiteResponse,
  PosAceiteResponse,
  Proposta,
  PropostaCreateBody,
  PropostaPatch,
} from "@/types/propostas";

const base = (clienteId: string) => `/api/clientes/${encodeURIComponent(clienteId)}/propostas`;
const item = (clienteId: string, id: string) => `${base(clienteId)}/${encodeURIComponent(id)}`;

export const propostasQueryKey = (clienteId: string) =>
  ["sw", "clientes", clienteId, "propostas"] as const;

export function usePropostas(clienteId: string | null) {
  const query = useQuery({
    queryKey: [...propostasQueryKey(clienteId ?? "__none__"), "list"],
    queryFn: () => api.get<Proposta[]>(base(clienteId as string)),
    enabled: !!clienteId,
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export function useProposta(clienteId: string | null, id: string | null) {
  const query = useQuery({
    queryKey: [...propostasQueryKey(clienteId ?? "__none__"), "item", id],
    queryFn: () => api.get<Proposta>(item(clienteId as string, id as string)),
    enabled: !!clienteId && !!id,
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export function usePropostaMutations(clienteId: string) {
  const qc = useQueryClient();
  const listKey = [...propostasQueryKey(clienteId), "list"] as const;
  // A saved proposta replaces its row in the list and its own detail.
  const salvaNoCache = (id: string) => [
    { queryKey: listKey, commit: (old: Proposta[] | undefined, saved: Proposta) => listOps.patch(old, id, saved) },
    {
      queryKey: [...propostasQueryKey(clienteId), "item", id],
      commit: (old: Proposta | undefined, saved: Proposta) => listOps.merge(old, saved),
    },
  ];
  const settle = [propostasQueryKey(clienteId)];
  const aceitarSettle = [...settle, contratosQueryKey(clienteId), ["sw", "clientes", clienteId]];

  const criar = useCacheWriteMutation<Proposta, PropostaCreateBody>({
    mutationFn: (body) => api.post<Proposta>(base(clienteId), body),
    targets: [{ queryKey: listKey, commit: (old, saved) => listOps.replace(old, saved.id, saved) }],
    invalidate: settle,
  });
  const salvar = useCacheWriteMutation<Proposta, { id: string; patch: PropostaPatch }>({
    mutationFn: ({ id, patch }) => api.patch<Proposta>(item(clienteId, id), patch),
    targets: ({ id }) => salvaNoCache(id),
    invalidate: settle,
  });
  const enviar = useCacheWriteMutation<Proposta, { id: string }>({
    mutationFn: ({ id }) => api.post<Proposta>(`${item(clienteId, id)}/enviar`, {}),
    targets: ({ id }) => salvaNoCache(id),
    invalidate: settle,
  });
  const recusar = useCacheWriteMutation<Proposta, { id: string; motivo: string }>({
    mutationFn: ({ id, motivo }) => api.post<Proposta>(`${item(clienteId, id)}/recusar`, { motivo }),
    targets: ({ id }) => salvaNoCache(id),
    invalidate: settle,
  });
  const aceitar = useCacheWriteMutation<AceiteResponse, { id: string }>({
    mutationFn: ({ id }) => api.post<AceiteResponse>(`${item(clienteId, id)}/aceitar`, {}),
    // The answer carries the accepted proposta; contratos and the live negotiation (materialized) refetch.
    targets: ({ id }) => [
      {
        queryKey: listKey,
        commit: (old: Proposta[] | undefined, saved) => listOps.patch(old, id, saved.proposta),
      },
      {
        queryKey: [...propostasQueryKey(clienteId), "item", id],
        commit: (old: Proposta | undefined, saved) => listOps.merge(old, saved.proposta),
      },
    ],
    invalidate: aceitarSettle,
    // A partial failure leaves the proposta `enviada`: refresh either way (settle already does).
  });
  const excluir = useCacheWriteMutation<unknown, { id: string }>({
    mutationFn: ({ id }) => api.delete(item(clienteId, id)),
    targets: ({ id }) => [{ queryKey: listKey, optimistic: (old) => listOps.remove(old, id) }],
    invalidate: settle,
  });
  const posAceite = useMutation({ // noc-allow: invalidate-only — resumes the post-acceptance steps server-side (funil, pós-aceite); the answer is the step report, not the proposta/negotiation rows it changed
    mutationFn: ({ id }: { id: string }) =>
      api.post<PosAceiteResponse>(`${item(clienteId, id)}/pos-aceite`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: propostasQueryKey(clienteId) });
      qc.invalidateQueries({ queryKey: ["sw", "clientes", clienteId] });
    },
  });
  return { criar, salvar, enviar, recusar, aceitar, excluir, posAceite };
}
