/**
 * Member portal hooks — ninho-vazio CONTRACT.md §Member portal.
 *
 * `GET /api/portal/minha-conta` + `POST /api/portal/assinatura/cancelar`.
 * Both are `membro`-only server-side (`get_membro_context`). Personal data
 * scoped to the session — no `placeholderData` (fixed key).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { euKeys, type NivelGrupoterapia } from "@/hooks/useEu";
import type { Ciclo } from "@/hooks/usePlanos";

/** `assinaturas.estado` including the ninho-vazio grace/expiry states. */
export type PortalAssinaturaEstado =
  | "iniciada"
  | "ativa"
  | "inadimplente"
  | "carencia"
  | "expirada"
  | "cancelada"
  | "pausada";

export interface PortalMembro {
  id: string;
  nome: string;
  email: string;
  telefone: string | null;
  status: string;
  entrou_em: string | null;
}

export interface PortalPlano {
  id: string;
  nome: string;
  preco_centavos: number;
  ciclo: Ciclo;
  nivel_grupoterapia: NivelGrupoterapia;
}

export interface PortalAssinatura {
  id: string;
  estado: PortalAssinaturaEstado;
  metodo: string | null;
  proxima_cobranca: string | null;
  pago_ate: string | null;
  carencia_ate: string | null;
  cancelada_em: string | null;
  gateway: string | null;
}

export interface PortalPagamento {
  id: string;
  valor_centavos: number;
  estado: string;
  metodo: string | null;
  vencimento: string | null;
  pago_em: string | null;
  url_fatura: string | null;
}

export interface PortalPlanoDisponivel {
  id: string;
  nome: string;
  descricao: string | null;
  preco_centavos: number;
  ciclo: Ciclo;
  nivel_grupoterapia: NivelGrupoterapia;
}

export interface MinhaConta {
  membro: PortalMembro;
  plano: PortalPlano | null;
  assinatura: PortalAssinatura | null;
  pagamentos: PortalPagamento[];
  planos_disponiveis: PortalPlanoDisponivel[];
}

export const portalKeys = {
  all: ["portal"] as const,
  minhaConta: () => ["portal", "minha-conta"] as const,
};

export function useMinhaConta(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: portalKeys.minhaConta(),
    queryFn: () => api.get<MinhaConta>("/api/portal/minha-conta"),
    enabled: options.enabled ?? true,
  });
}

export function useCancelarAssinatura() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { motivo: string | null }) =>
      api.post<PortalAssinatura>("/api/portal/assinatura/cancelar", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: portalKeys.all });
      qc.invalidateQueries({ queryKey: euKeys.all });
    },
  });
}

/** Estados in which the member still has a paid subscription to cancel. */
export const ESTADOS_CANCELAVEIS: PortalAssinaturaEstado[] = ["iniciada", "ativa", "inadimplente", "carencia"];
