/**
 * Member grupoterapia hooks — ninho-vazio CONTRACT.md §Grupoterapia (member).
 *
 * `GET /api/portal/grupoterapia`, `POST|DELETE
 * /api/portal/grupoterapia/{id}/reserva`. `link_sala` is null whenever
 * `acesso === "bloqueado"` (server-side guarantee) — the page additionally
 * never renders a link for a blocked item.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { NivelGrupoterapia } from "@/hooks/useEu";

export type AcessoSessao = "bloqueado" | "ouvir" | "falar";

export interface PortalSessao {
  id: string;
  titulo: string;
  descricao: string | null;
  inicio: string;
  duracao_minutos: number;
  status: string;
  vagas_fala: number;
  vagas_restantes: number;
  minha_reserva: boolean;
  acesso: AcessoSessao;
  link_sala: string | null;
}

export interface PortalGrupoterapiaResponse {
  nivel: NivelGrupoterapia;
  items: PortalSessao[];
}

export const portalGrupoterapiaKeys = {
  all: ["portal-grupoterapia"] as const,
};

export function usePortalGrupoterapia() {
  return useQuery({
    queryKey: portalGrupoterapiaKeys.all,
    queryFn: () => api.get<PortalGrupoterapiaResponse>("/api/portal/grupoterapia"),
  });
}

export function useReservarVagaFala() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sessaoId: string) =>
      api.post<{ status: "confirmada" }>(`/api/portal/grupoterapia/${sessaoId}/reserva`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: portalGrupoterapiaKeys.all }),
  });
}

export function useCancelarReservaFala() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sessaoId: string) => api.delete(`/api/portal/grupoterapia/${sessaoId}/reserva`),
    onSuccess: () => qc.invalidateQueries({ queryKey: portalGrupoterapiaKeys.all }),
  });
}
