/**
 * useInteresses — a cliente's interest list (CONTRACT §4.1).
 *
 * Person-keyed ⇒ no `placeholderData` (see `usePessoa.ts`): another person's
 * interests must never flash under this person's name.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { listOps, pageOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { pessoaKey } from "@/hooks/usePessoa";
import type { InteresseCriarBody, InteresseItem, ItemsTotal } from "@/types/interesses";

const base = (clienteId: string) => `/api/clientes/${encodeURIComponent(clienteId)}`;
export const interessesKey = (clienteId: string) =>
  [...pessoaKey(clienteId), "interesses"] as const;

export function useInteresses(clienteId: string | undefined) {
  return useQuery({
    queryKey: interessesKey(clienteId ?? "__none__"),
    queryFn: () =>
      api.get<ItemsTotal<InteresseItem>>(`${base(clienteId as string)}/interesses`),
    enabled: !!clienteId,
  });
}

/** Add / remove. Both write the list at once and refresh the person payload (`contagens`, server-computed). */
export function useInteresseMutations(clienteId: string) {
  const add = useCacheWriteMutation<InteresseItem, InteresseCriarBody>({
    mutationFn: (body) => api.post<InteresseItem>(`${base(clienteId)}/interesses`, body),
    targets: [
      {
        queryKey: interessesKey(clienteId),
        commit: (old: ItemsTotal<InteresseItem> | undefined, saved) => {
          if (!old?.items || old.items.some((i) => i.id === saved.id)) return old;
          const next = listOps.within(old, "items", (l) => listOps.replace(l, saved.id, saved));
          return next ? { ...next, total: old.total + 1 } : old;
        },
      },
    ],
    invalidate: [pessoaKey(clienteId)],
  });

  const remove = useCacheWriteMutation<unknown, string>({
    mutationFn: (interesseId) =>
      api.delete(`${base(clienteId)}/interesses/${encodeURIComponent(interesseId)}`),
    targets: (interesseId) => [
      {
        queryKey: interessesKey(clienteId),
        optimistic: (old: ItemsTotal<InteresseItem> | undefined) => pageOps.remove(old, interesseId),
      },
    ],
    invalidate: [pessoaKey(clienteId)],
  });

  return { add, remove };
}
