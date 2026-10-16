/** Lais › Atualização de imóveis — owner conversations (contract §14 W12). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Transporte } from "@/hooks/useLaisTransporte";

export type ProprietarioStatus = "pendente" | "enviado" | "respondido" | "atualizado" | "erro" | "parar";

export const STATUS_LABEL: Record<ProprietarioStatus, string> = {
  pendente: "Pendente",
  enviado: "Enviado",
  respondido: "Respondido",
  atualizado: "Atualizado",
  erro: "Erro",
  parar: "Não contatar",
};

export interface Proprietario {
  id: string;
  nome: string;
  imovel_codigo: string | null;
  status: ProprietarioStatus;
  /** Owner-confirmed values (Lais-owned storage; the Vista mirror is never written). All null until confirmed. */
  status_confirmado?: string | null;
  preco_confirmado?: number | string | null;
  preco_tipo_confirmado?: "venda" | "locacao" | null;
  confirmado_at?: string | null;
}

/** "Suspenso · R$ 450.000,00 (venda) — confirmado pelo proprietário em 10/10/2026", or null when nothing was confirmed. */
export function textoConfirmacao(p: Proprietario): string | null {
  if (!p.confirmado_at || (!p.status_confirmado && p.preco_confirmado == null)) return null;
  const partes: string[] = [];
  if (p.status_confirmado) partes.push(p.status_confirmado);
  if (p.preco_confirmado != null) {
    const brl = Number(p.preco_confirmado).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
    partes.push(p.preco_tipo_confirmado ? `${brl} (${p.preco_tipo_confirmado === "venda" ? "venda" : "locação"})` : brl);
  }
  const d = new Date(p.confirmado_at);
  const data = d.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
  return `${partes.join(" · ")} — confirmado pelo proprietário em ${data}`;
}
export interface ProprietariosList {
  items: Proprietario[];
  transporte?: Transporte;
}

export const PROPRIETARIOS_KEY = ["sw", "lais", "proprietarios"] as const;
const BASE = "/api/lais/proprietarios";

export function useProprietarios(status: string, q: string) {
  return useQuery<ProprietariosList>({
    queryKey: [...PROPRIETARIOS_KEY, status, q],
    placeholderData: (prev) => prev,
    queryFn: async () => {
      const qs = new URLSearchParams();
      if (status) qs.set("status", status);
      if (q) qs.set("q", q);
      const s = qs.toString();
      const r = await api.get<{ data: Proprietario[]; meta?: { transporte?: Transporte } }>(s ? `${BASE}?${s}` : BASE);
      return { items: r.data, transporte: r.meta?.transporte };
    },
  });
}

export function useSolicitarAtualizacao() {
  const qc = useQueryClient();
  return useMutation<unknown, unknown, string>({
    mutationFn: async (id) => api.post(`${BASE}/${id}/solicitar`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: PROPRIETARIOS_KEY }),
  });
}
