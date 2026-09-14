/**
 * Testemunhas padrão da imobiliária — up to two standing witnesses reused in
 * every contract's signature block. Org-scoped settings resource, unrelated
 * to any one cliente/negociação.
 *
 * The backend caps this at 2 per org and answers a third POST with 409 — the
 * UI surfaces that message rather than pre-guessing it, since "2" living in
 * two places (here and the backend) is exactly the kind of number that drifts.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

export interface Testemunha {
  id: string;
  nome: string;
  cpf: string | null;
  rg: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface TestemunhaCreate {
  nome: string;
  cpf?: string | null;
  rg?: string | null;
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
