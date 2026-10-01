/**
 * useInteresses — a cliente's interest list (CONTRACT §4.1).
 *
 * Person-keyed ⇒ no `placeholderData` (see `usePessoa.ts`): another person's
 * interests must never flash under this person's name.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

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

/** Add / remove. Both refresh the list AND the person payload (`contagens`). */
export function useInteresseMutations(clienteId: string) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: pessoaKey(clienteId) });

  const add = useMutation({
    mutationFn: (body: InteresseCriarBody) =>
      api.post<InteresseItem>(`${base(clienteId)}/interesses`, body),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (interesseId: string) =>
      api.delete(`${base(clienteId)}/interesses/${encodeURIComponent(interesseId)}`),
    onSuccess: invalidate,
  });

  return { add, remove };
}
