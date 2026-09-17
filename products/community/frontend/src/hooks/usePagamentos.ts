/**
 * Pagamentos (payments) hook — community-m2-contract.md
 * §Endpoints#Manager-+-member-views, §Frontend#/financeiro.
 *
 * Admin-only (amendment A16/P3): a `moderador` gets a strict 403 on this
 * route, never a redacted 200. `pages/Financeiro.tsx` renders the server's
 * `detail` for that 403 rather than assuming payment fields exist — this
 * hook's `error` is a real backend refusal, not a network blip, for a
 * `moderador` session.
 */
import { useQuery, keepPreviousData } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { AssinaturaEstado, AssinaturaGateway, AssinaturaMetodo } from "@/hooks/useAssinaturas";

/** `pagamentos.estado` has its own vocabulary — distinct from `assinaturas.estado`. */
export type PagamentoEstado = "pendente" | "pago" | "falhou" | "estornado";

export interface Pagamento {
  id: string;
  membro_id: string;
  membro_nome: string;
  assinatura_id: string | null;
  gateway: AssinaturaGateway;
  cobranca_externa_id: string;
  valor_centavos: number;
  metodo: AssinaturaMetodo;
  estado: PagamentoEstado;
  pago_em: string | null;
  vencimento: string | null;
  url_fatura: string | null;
  pix_payload: string | null;
  pix_imagem_base64: string | null;
  created_at: string;
}

export interface PagamentoListResponse {
  items: Pagamento[];
  total: number;
}

export interface PagamentosParams {
  membro_id?: string;
  assinatura_id?: string;
  estado?: PagamentoEstado | AssinaturaEstado;
  page?: number;
  page_size?: number;
}

export function usePagamentos(params?: PagamentosParams) {
  return useQuery({
    queryKey: ["pagamentos", "list", params ?? {}] as const,
    queryFn: () => api.get<PagamentoListResponse>("/api/pagamentos", params),
    placeholderData: keepPreviousData,
  });
}
