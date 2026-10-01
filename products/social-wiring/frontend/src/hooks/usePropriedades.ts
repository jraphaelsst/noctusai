/**
 * usePropriedades — imóveis a cliente OWNS (proprietários, CONTRACT §4.2).
 * Person-keyed ⇒ no `placeholderData` (see `usePessoa.ts`).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

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

export function usePropriedadeMutations(clienteId: string) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: pessoaKey(clienteId) });

  const add = useMutation({
    mutationFn: (codigo: string) =>
      api.post<PropriedadeItem>(`${base(clienteId)}/propriedades`, { codigo }),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (id: string) =>
      api.delete(`${base(clienteId)}/propriedades/${encodeURIComponent(id)}`),
    onSuccess: invalidate,
  });

  return { add, remove };
}
