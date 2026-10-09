/**
 * Per-contract signing company — which of the org's REGISTERED imobiliárias
 * (`useImobiliarias.ts`) signs THIS contract. Exactly one (a nullable FK), so
 * unlike `useContratoTestemunhas` there is no list: GET returns the RESOLVED
 * company and PUT `{ imobiliaria_id }` replaces the choice (`null` clears it).
 *
 * `origem`: "selecionada" (chosen on the contract, even if since removed from
 * the registry → `excluida`), "unica" (auto-selected: the org has exactly one
 * active company), `null` (nothing resolved — the contract cannot generate).
 *
 * Contract: products/social-wiring/projects/signing-companies/CONTRACT.md.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import { contratosQueryKey } from "@/hooks/useContratos";
import type { ImobiliariaCampoObrigatorio } from "@/hooks/useImobiliarias";

export interface ImobiliariaResolvida {
  id: string;
  razao_social: string | null;
  nome_fantasia: string | null;
  cnpj: string | null;
  /** Soft-deleted from the registry after this contract chose it. It stays on
   *  the contract but cannot be newly picked for another one. */
  excluida: boolean;
  faltando: ImobiliariaCampoObrigatorio[];
}

export interface ContratoImobiliaria {
  imobiliaria: ImobiliariaResolvida | null;
  origem: "selecionada" | "unica" | null;
}

const base = (clienteId: string, contratoId: string) =>
  `/api/clientes/${encodeURIComponent(clienteId)}/contratos/${encodeURIComponent(contratoId)}/imobiliaria`;

const KEY = (clienteId: string, contratoId: string) =>
  ["sw", "clientes", clienteId, "contratos", contratoId, "imobiliaria"] as const;

export function useContratoImobiliaria(clienteId: string | null, contratoId: string | null) {
  return useQuery({
    queryKey: KEY(clienteId ?? "__none__", contratoId ?? "__none__"),
    queryFn: () => api.get<ContratoImobiliaria>(base(clienteId as string, contratoId as string)),
    enabled: !!clienteId && !!contratoId,
    // No placeholderData: this answer is contract-scoped, and showing the
    // PREVIOUS contract's company on another contract would lie. Each card
    // mounts its own instance, so the key never changes under one component.
  });
}

export function useDefinirContratoImobiliaria(clienteId: string, contratoId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (imobiliariaId: string | null) =>
      api.put<ContratoImobiliaria>(base(clienteId, contratoId), {
        imobiliaria_id: imobiliariaId,
      }),
    onSuccess: (data) => {
      qc.setQueryData(KEY(clienteId, contratoId), data);
      // The generator's readiness (`imobiliaria.selecao`) depends on this.
      qc.invalidateQueries({ queryKey: [...contratosQueryKey(clienteId), contratoId, "geracao"] });
    },
  });
}
