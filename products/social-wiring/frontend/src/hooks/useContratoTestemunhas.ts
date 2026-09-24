/**
 * Per-contract witness selection (migration 168) — which of the org's
 * REGISTERED testemunhas (`useTestemunhas.ts`) sign THIS contract, and in
 * what order.
 *
 * Sibling shape to `useContratos.ts`'s `useAssinaturas`/`useContratoGeracao`:
 * one GET per contract, scoped `clienteId`/`contratoId`, PUT replaces the
 * whole selection (never a partial patch) — same "the server owns the
 * canonical order" posture `matriculas`' act-selection hooks take.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

export interface TestemunhaSelecionada {
  id: string;
  nome: string;
  cpf: string | null;
  email: string | null;
  celular: string | null;
}

export interface ContratoTestemunhaItem {
  /** The selection row's own id — not the testemunha's. */
  id: string;
  ordem: number;
  testemunha: TestemunhaSelecionada;
}

const base = (clienteId: string, contratoId: string) =>
  `/api/clientes/${encodeURIComponent(clienteId)}/contratos/${encodeURIComponent(contratoId)}/testemunhas`;

const KEY = (clienteId: string, contratoId: string) =>
  ["sw", "clientes", clienteId, "contratos", contratoId, "testemunhas"] as const;

export function useContratoTestemunhas(clienteId: string | null, contratoId: string | null) {
  return useQuery({
    queryKey: KEY(clienteId ?? "__none__", contratoId ?? "__none__"),
    queryFn: () =>
      api.get<{ items: ContratoTestemunhaItem[]; total: number }>(
        base(clienteId as string, contratoId as string),
      ),
    enabled: !!clienteId && !!contratoId,
  });
}

export function useDefinirContratoTestemunhas(clienteId: string, contratoId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (testemunhaIds: string[]) =>
      api.put<{ items: ContratoTestemunhaItem[]; total: number }>(
        base(clienteId, contratoId),
        { testemunha_ids: testemunhaIds },
      ),
    onSuccess: (data) => {
      qc.setQueryData(KEY(clienteId, contratoId), data);
    },
  });
}
