/**
 * Imóveis linked to an atendimento (§3.1–3.4). Own file — `useCardHub.ts` is
 * frozen for this project.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import type {
  AtendimentoImovel,
  AtendimentoImovelCreateBody,
  AtendimentoImoveisResponse,
} from "@/types/atendimentoImoveis";

const base = (clienteId: string) =>
  `/api/clientes/${encodeURIComponent(clienteId)}/atendimento-imoveis`;

const KEY_ROOT = (clienteId: string) =>
  ["sw", "clientes", clienteId, "atendimento-imoveis"] as const;
const KEY = (clienteId: string, atendimentoId?: string | null) =>
  [...KEY_ROOT(clienteId), atendimentoId ?? null] as const;

export function useAtendimentoImoveis(clienteId: string | null, atendimentoId?: string | null) {
  const query = useQuery({
    queryKey: KEY(clienteId ?? "__none__", atendimentoId),
    queryFn: () =>
      api.get<AtendimentoImoveisResponse>(
        `${base(clienteId as string)}${atendimentoId ? `?atendimento_id=${encodeURIComponent(atendimentoId)}` : ""}`,
      ),
    enabled: !!clienteId,
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export function useAtendimentoImoveisMutations(clienteId: string) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: KEY_ROOT(clienteId) });

  const adicionar = useMutation({
    mutationFn: (body: AtendimentoImovelCreateBody) =>
      api.post<AtendimentoImovel>(base(clienteId), body),
    onSuccess: invalidate,
  });
  const definirPrincipal = useMutation({
    mutationFn: ({ id }: { id: string }) =>
      api.put<AtendimentoImovel>(`${base(clienteId)}/${encodeURIComponent(id)}/principal`),
    onSuccess: invalidate,
  });
  const remover = useMutation({
    mutationFn: ({ id }: { id: string }) =>
      api.delete(`${base(clienteId)}/${encodeURIComponent(id)}`),
    onSuccess: invalidate,
  });
  return { adicionar, definirPrincipal, remover };
}
