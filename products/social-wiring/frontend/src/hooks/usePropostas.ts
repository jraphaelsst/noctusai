/**
 * Propostas (lead-to-contract CONTRACT §4.2, §7.3). Own file — the roteiros
 * hooks belong to S3.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import { contratosQueryKey } from "@/hooks/useContratos";
import type {
  AceiteResponse,
  PosAceite,
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
  const invalidar = () => qc.invalidateQueries({ queryKey: propostasQueryKey(clienteId) });
  const invalidarComContratos = () => {
    invalidar();
    qc.invalidateQueries({ queryKey: contratosQueryKey(clienteId) });
    // Aceitar materializes the live negotiation + atendimento imóvel.
    qc.invalidateQueries({ queryKey: ["sw", "clientes", clienteId] });
  };

  const criar = useMutation({
    mutationFn: (body: PropostaCreateBody) => api.post<Proposta>(base(clienteId), body),
    onSuccess: invalidar,
  });
  const salvar = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: PropostaPatch }) =>
      api.patch<Proposta>(item(clienteId, id), patch),
    onSuccess: invalidar,
  });
  const enviar = useMutation({
    mutationFn: ({ id }: { id: string }) => api.post<Proposta>(`${item(clienteId, id)}/enviar`, {}),
    onSuccess: invalidar,
  });
  const recusar = useMutation({
    mutationFn: ({ id, motivo }: { id: string; motivo: string }) =>
      api.post<Proposta>(`${item(clienteId, id)}/recusar`, { motivo }),
    onSuccess: invalidar,
  });
  const aceitar = useMutation({
    mutationFn: ({ id }: { id: string }) =>
      api.post<AceiteResponse>(`${item(clienteId, id)}/aceitar`, {}),
    onSuccess: invalidarComContratos,
    // A partial failure leaves the proposta `enviada`: refresh either way.
    onError: invalidar,
  });
  const excluir = useMutation({
    mutationFn: ({ id }: { id: string }) => api.delete(item(clienteId, id)),
    onSuccess: invalidar,
  });
  const posAceite = useMutation({
    mutationFn: ({ id }: { id: string }) =>
      api.post<PosAceite>(`${item(clienteId, id)}/pos-aceite`, {}),
    onSuccess: () => {
      invalidar();
      qc.invalidateQueries({ queryKey: ["sw", "clientes", clienteId] });
    },
  });
  return { criar, salvar, enviar, recusar, aceitar, excluir, posAceite };
}
