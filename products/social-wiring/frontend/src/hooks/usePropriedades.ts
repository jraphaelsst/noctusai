/**
 * usePropriedades — imóveis a cliente OWNS (proprietários, CONTRACT §4.2).
 * Person-keyed ⇒ no `placeholderData` (see `usePessoa.ts`).
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { listOps, pageOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { pessoaKey } from "@/hooks/usePessoa";
import type { ItemsTotal, PropriedadeItem } from "@/types/interesses";

const base = (clienteId: string) => `/api/clientes/${encodeURIComponent(clienteId)}`;
export const propriedadesKey = (clienteId: string) =>
  [...pessoaKey(clienteId), "propriedades"] as const;

export function usePropriedades(clienteId: string | undefined) {
  return useQuery({
    queryKey: propriedadesKey(clienteId ?? "__none__"),
    queryFn: () =>
      api.get<ItemsTotal<PropriedadeItem>>(`${base(clienteId as string)}/propriedades`),
    enabled: !!clienteId,
  });
}

/** Add / remove. Both write the list at once and refresh the person payload (`contagens`, server-computed). */
export function usePropriedadeMutations(clienteId: string) {
  const add = useCacheWriteMutation<PropriedadeItem, string>({
    mutationFn: (codigo) =>
      api.post<PropriedadeItem>(`${base(clienteId)}/propriedades`, { codigo }),
    targets: [
      {
        queryKey: propriedadesKey(clienteId),
        commit: (old: ItemsTotal<PropriedadeItem> | undefined, saved) => {
          if (!old?.items || old.items.some((i) => i.id === saved.id)) return old;
          const next = listOps.within(old, "items", (l) => listOps.replace(l, saved.id, saved));
          return next ? { ...next, total: old.total + 1 } : old;
        },
      },
    ],
    invalidate: [pessoaKey(clienteId)],
  });

  const remove = useCacheWriteMutation<unknown, string>({
    mutationFn: (id) =>
      api.delete(`${base(clienteId)}/propriedades/${encodeURIComponent(id)}`),
    targets: (id) => [
      {
        queryKey: propriedadesKey(clienteId),
        optimistic: (old: ItemsTotal<PropriedadeItem> | undefined) => pageOps.remove(old, id),
      },
    ],
    invalidate: [pessoaKey(clienteId)],
  });

  return { add, remove };
}
