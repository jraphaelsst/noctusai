/**
 * Imóveis linked to an atendimento (§3.1–3.4). Own file — `useCardHub.ts` is
 * frozen for this project.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { listOps, pageOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

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
  const adicionar = useCacheWriteMutation<AtendimentoImovel, AtendimentoImovelCreateBody>({
    mutationFn: (body) => api.post<AtendimentoImovel>(base(clienteId), body),
    // The link joins the list of the atendimento it was added to (`principal` flips on its siblings settle).
    targets: (body) => [
      {
        queryKey: KEY(clienteId, body.atendimento_id),
        commit: (old: AtendimentoImoveisResponse | undefined, saved) => {
          if (!old?.items || old.items.some((i) => i.id === saved.id)) return old;
          const next = listOps.within(old, "items", (l) => listOps.replace(l, saved.id, saved));
          return next ? { ...next, total: old.total + 1 } : old;
        },
      },
    ],
    invalidate: [KEY_ROOT(clienteId)],
  });
  const definirPrincipal = useCacheWriteMutation<AtendimentoImovel, { id: string }>({
    mutationFn: ({ id }) =>
      api.put<AtendimentoImovel>(`${base(clienteId)}/${encodeURIComponent(id)}/principal`),
    // Exactly one principal per list: drawn at once on every cached atendimento list.
    targets: ({ id }) => [
      {
        queryKey: KEY_ROOT(clienteId),
        match: "prefix",
        optimistic: (old: AtendimentoImoveisResponse | undefined) =>
          old?.items?.some((i) => i.id === id)
            ? { ...old, items: old.items.map((i) => ({ ...i, principal: i.id === id })) }
            : old,
      },
    ],
  });
  const remover = useCacheWriteMutation<unknown, { id: string }>({
    mutationFn: ({ id }) => api.delete(`${base(clienteId)}/${encodeURIComponent(id)}`),
    targets: ({ id }) => [
      {
        queryKey: KEY_ROOT(clienteId),
        match: "prefix",
        optimistic: (old: AtendimentoImoveisResponse | undefined) => pageOps.remove(old, id),
      },
    ],
  });
  return { adicionar, definirPrincipal, remover };
}
