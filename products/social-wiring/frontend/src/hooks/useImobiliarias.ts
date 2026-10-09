/**
 * Imobiliárias — the org's REGISTRY of signing companies. One org registers N
 * companies; each CONTRACT chooses which one signs (`useContratoImobiliaria`).
 * Identity (razão social, CNPJ, CRECI, responsável, endereço) lives here, per
 * company; the org-wide operational settings stay on `useDadosImobiliaria`.
 *
 * Contract: products/social-wiring/projects/signing-companies/CONTRACT.md.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

/** The fields a contract REQUIRES of its signing company (`faltando` subset). */
export type ImobiliariaCampoObrigatorio =
  | "razao_social"
  | "cnpj"
  | "responsavel_nome"
  | "responsavel_creci"
  | "endereco_cidade";

export interface Imobiliaria {
  id: string;
  razao_social: string | null;
  nome_fantasia: string | null;
  cnpj: string | null;
  creci_pj: string | null;
  creci_pj_regiao: string | null;
  responsavel_nome: string | null;
  responsavel_creci: string | null;
  responsavel_creci_regiao: string | null;
  telefone: string | null;
  email: string | null;
  endereco_cep: string | null;
  endereco_logradouro: string | null;
  endereco_numero: string | null;
  endereco_complemento: string | null;
  endereco_bairro: string | null;
  endereco_cidade: string | null;
  endereco_uf: string | null;
  /** Derived server-side, never stored. `[]` = complete. */
  faltando: ImobiliariaCampoObrigatorio[];
  /** Informative only — deleting never touches those contracts (soft delete). */
  contratos_em_uso: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface ImobiliariaCreate {
  razao_social: string;
  cnpj: string;
  nome_fantasia?: string | null;
  creci_pj?: string | null;
  creci_pj_regiao?: string | null;
  responsavel_nome?: string | null;
  responsavel_creci?: string | null;
  responsavel_creci_regiao?: string | null;
  telefone?: string | null;
  email?: string | null;
  endereco_cep?: string | null;
  endereco_logradouro?: string | null;
  endereco_numero?: string | null;
  endereco_complemento?: string | null;
  endereco_bairro?: string | null;
  endereco_cidade?: string | null;
  endereco_uf?: string | null;
}

export type ImobiliariaPatch = Partial<ImobiliariaCreate>;

const BASE = "/api/settings/imobiliarias";
export const IMOBILIARIAS_KEY = ["sw", "settings", "imobiliarias"] as const;

/** Rótulos pt-BR dos campos que o contrato exige — usados em "Incompleta: …". */
export const ROTULO_CAMPO_OBRIGATORIO: Record<ImobiliariaCampoObrigatorio, string> = {
  razao_social: "razão social",
  cnpj: "CNPJ",
  responsavel_nome: "responsável",
  responsavel_creci: "CRECI do responsável",
  endereco_cidade: "cidade",
};

export function useImobiliarias() {
  return useQuery({
    queryKey: IMOBILIARIAS_KEY,
    queryFn: () => api.get<{ items: Imobiliaria[]; total: number }>(BASE),
  });
}

/** A registry change can alter any card's resolved company (`unica`) and its
 *  `faltando` — so every per-contract selection is invalidated with it. */
function useInvalidarImobiliarias() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: IMOBILIARIAS_KEY });
    qc.invalidateQueries({
      predicate: (q) => q.queryKey[0] === "sw" && q.queryKey.includes("imobiliaria"),
    });
  };
}

export function useCreateImobiliaria() {
  const invalidar = useInvalidarImobiliarias();
  return useMutation({
    mutationFn: (payload: ImobiliariaCreate) => api.post<Imobiliaria>(BASE, payload),
    onSuccess: invalidar,
  });
}

export function useUpdateImobiliaria() {
  const invalidar = useInvalidarImobiliarias();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: ImobiliariaPatch }) =>
      api.patch<Imobiliaria>(`${BASE}/${id}`, patch),
    onSuccess: invalidar,
  });
}

export function useDeleteImobiliaria() {
  const invalidar = useInvalidarImobiliarias();
  return useMutation({
    mutationFn: (id: string) => api.delete(`${BASE}/${id}`),
    onSuccess: invalidar,
  });
}
