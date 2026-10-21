/**
 * Imobiliárias — the org's REGISTRY of signing companies. One org registers N
 * companies; each CONTRACT chooses which one signs (`useContratoImobiliaria`).
 * Identity (razão social, CNPJ, CRECI, responsável, endereço) lives here, per
 * company; the org-wide operational settings stay on `useDadosImobiliaria`.
 *
 * Contract: products/social-wiring/projects/signing-companies/CONTRACT.md.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { pageOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

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

type ImobiliariasCache = { items: Imobiliaria[]; total: number };

/** A registry change can alter any card's resolved company (`unica`) and its
 *  `faltando` — so every per-contract selection is invalidated with it. */
function useInvalidarSelecoes() {
  const qc = useQueryClient();
  return () =>
    qc.invalidateQueries({
      predicate: (q) => q.queryKey[0] === "sw" && q.queryKey.includes("imobiliaria"),
    });
}

export function useCreateImobiliaria() {
  const invalidarSelecoes = useInvalidarSelecoes();
  return useCacheWriteMutation<Imobiliaria, ImobiliariaCreate>({
    mutationFn: (payload) => api.post<Imobiliaria>(BASE, payload),
    targets: [
      {
        queryKey: IMOBILIARIAS_KEY,
        commit: (old: ImobiliariasCache | undefined, saved) => pageOps.add(old, saved),
      },
    ],
    onSuccess: invalidarSelecoes,
  });
}

export function useUpdateImobiliaria() {
  const invalidarSelecoes = useInvalidarSelecoes();
  return useCacheWriteMutation<Imobiliaria, { id: string; patch: ImobiliariaPatch }>({
    mutationFn: ({ id, patch }) => api.patch<Imobiliaria>(`${BASE}/${id}`, patch),
    targets: ({ id }) => [
      {
        queryKey: IMOBILIARIAS_KEY,
        commit: (old: ImobiliariasCache | undefined, saved) => pageOps.replace(old, id, saved),
      },
    ],
    onSuccess: invalidarSelecoes,
  });
}

export function useDeleteImobiliaria() {
  const invalidarSelecoes = useInvalidarSelecoes();
  return useCacheWriteMutation<unknown, string>({
    mutationFn: (id) => api.delete(`${BASE}/${id}`),
    targets: (id) => [
      {
        queryKey: IMOBILIARIAS_KEY,
        optimistic: (old: ImobiliariasCache | undefined) => pageOps.remove(old, id),
      },
    ],
    onSuccess: invalidarSelecoes,
  });
}
