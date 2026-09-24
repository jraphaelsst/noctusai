/**
 * Testemunhas — the org's REGISTRY of signature witnesses (migration 168
 * opened up migration 108's fixed pair). Org-scoped settings resource,
 * unrelated to any one cliente/negociação; a CONTRACT selects a subset of
 * this registry via `useContratoTestemunhas` (per-contract, card_hub-scoped).
 *
 * [Owner decision, migration 168] CPF is now required on create — the
 * contract prints CPF instead of RG, so a witness with no CPF can never be
 * selected for one. `rg` stays on the type only for the 2 legacy rows that
 * still carry one (no longer collected on the form, never printed).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

export interface Testemunha {
  id: string;
  nome: string;
  cpf: string | null;
  /** Legacy display-only — no longer collected on the form or printed on a
   *  contract (migration 168 replaced it with CPF everywhere). */
  rg: string | null;
  /** Migration 168 — the owner's requested contact field. Never printed. */
  celular: string | null;
  /** Optional — only required to send this witness for digital signature
   *  (`papel: "testemunha"` in `EnviarAssinaturaDialog`); the contract print
   *  and its readiness gate never need it (migration 143). */
  email: string | null;
  /** [migration 168] `true` for the 2 legacy rows migration 108 shipped
   *  before CPF existed — kept and listed, just not selectable for a
   *  contract until an operator adds a CPF. */
  cpf_pendente: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface TestemunhaCreate {
  nome: string;
  /** REQUIRED (migration 168, owner decision) — the server validates mod-11
   *  and answers 422 on a bad checksum. */
  cpf: string;
  celular?: string | null;
  email?: string | null;
}

export type TestemunhaPatch = Partial<TestemunhaCreate>;

const BASE = "/api/settings/imobiliaria/testemunhas";
const TESTEMUNHAS_KEY = ["sw", "settings", "testemunhas"] as const;

export function useTestemunhas() {
  return useQuery({
    queryKey: TESTEMUNHAS_KEY,
    queryFn: () =>
      api.get<{ items: Testemunha[]; total: number }>(BASE),
  });
}

export function useCreateTestemunha() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: TestemunhaCreate) =>
      api.post<Testemunha>(BASE, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: TESTEMUNHAS_KEY }),
  });
}

export function useUpdateTestemunha() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: TestemunhaPatch }) =>
      api.patch<Testemunha>(`${BASE}/${id}`, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: TESTEMUNHAS_KEY }),
  });
}

export function useDeleteTestemunha() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`${BASE}/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: TESTEMUNHAS_KEY }),
  });
}
