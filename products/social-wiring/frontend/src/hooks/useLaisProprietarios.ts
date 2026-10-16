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
