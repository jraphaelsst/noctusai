/**
 * usePessoa — `GET /api/clientes/{id}/resumo` (CONTRACT §4.5), the one payload
 * behind `/clientes/:id` AND `/vendedores/:id`.
 *
 * No `placeholderData`: the key is a PERSON id, and carrying person A's
 * atendimentos/contacts onto person B's screen while B loads would show one
 * individual's personal data under another's name (authorisation-scoped
 * personal data — the documented exception in lying-loading-state.md).
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import type { PessoaResumo } from "@/types/pessoa";

export const PESSOA_ROOT_KEY = ["sw", "pessoa"] as const;
export const pessoaKey = (clienteId: string) => [...PESSOA_ROOT_KEY, clienteId] as const;

export function usePessoaResumo(clienteId: string | undefined) {
  return useQuery({
    queryKey: [...pessoaKey(clienteId ?? "__none__"), "resumo"],
    queryFn: () =>
      api.get<PessoaResumo>(`/api/clientes/${encodeURIComponent(clienteId as string)}/resumo`),
    enabled: !!clienteId,
  });
}
