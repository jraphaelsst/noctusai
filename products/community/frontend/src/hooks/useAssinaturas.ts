/**
 * Assinaturas (subscriptions) hooks — community-m2-contract.md
 * §Endpoints#Manager-+-member-views, §Frontend#/financeiro, #/membros.
 *
 * A `moderador` gets a REDACTED shape on this same endpoint (amendment P3):
 * `estado`, `metodo`, `ciclo`, `plano_nome`, `membro_nome`, `ativa_em` — and
 * NOT `assinatura_externa_id`. So that field is OPTIONAL on the `Assinatura`
 * type and every consumer must render it as absent-safe (never assume it
 * exists) — `pages/Financeiro.tsx` and the Membros detail-dialog summary
 * both do `assinatura.assinatura_externa_id ?? undefined` rather than
 * indexing it unconditionally.
 */
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type AssinaturaEstado = "iniciada" | "ativa" | "inadimplente" | "pausada" | "cancelada";
export type AssinaturaMetodo = "cartao" | "pix" | "boleto";
export type AssinaturaGateway = "stripe" | "asaas";
export type AssinaturaCiclo = "mensal" | "anual";

export interface Assinatura {
  id: string;
  membro_id: string;
  membro_nome: string;
  plano_id: string;
  plano_nome: string;
  gateway: AssinaturaGateway;
  estado: AssinaturaEstado;
  metodo: AssinaturaMetodo;
  ciclo: AssinaturaCiclo;
  /** Absent for a `moderador` caller (P3) — never assume present. */
  assinatura_externa_id?: string | null;
  iniciada_em: string | null;
  ativa_em: string | null;
  cancelada_em: string | null;
}

export interface AssinaturaListResponse {
  items: Assinatura[];
  total: number;
}

export interface AssinaturasParams {
  membro_id?: string;
  estado?: AssinaturaEstado;
  page?: number;
  page_size?: number;
}

const assinaturasKeys = {
  all: ["assinaturas"] as const,
  list: (params?: AssinaturasParams) => ["assinaturas", "list", params ?? {}] as const,
};

export function useAssinaturas(params?: AssinaturasParams) {
  return useQuery({
    queryKey: assinaturasKeys.list(params),
    queryFn: () => api.get<AssinaturaListResponse>("/api/assinaturas", params),
    placeholderData: keepPreviousData,
    enabled: params?.membro_id === undefined || !!params.membro_id,
  });
}

/**
 * Cancels at the gateway then locally (admin-only). Gateway failure → 502,
 * nothing changed locally (amendment A14) — the server's `detail` is the
 * message to render on error, never a generic fallback.
 */
export function useCancelarAssinatura() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, motivo }: { id: string; motivo: string }) =>
      api.post<Assinatura>(`/api/assinaturas/${id}/cancelar`, { motivo }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: assinaturasKeys.all });
      qc.invalidateQueries({ queryKey: ["membros"] });
    },
  });
}
