/**
 * Mensagem-flags hooks — community-m3-contract.md §3#Ingest-+-flags
 * (endpoint 20). Consumed by the moderation queue page
 * (`pages/whatsapp/Moderacao.tsx`). The API carries no message text and no
 * author (LGPD §6) — only a categorized justification and the group id.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type FlagSeveridade = "baixa" | "media" | "alta";
export type FlagEstado = "aberta" | "resolvida" | "descartada";

export interface MensagemFlag {
  id: string;
  mensagem_id: string;
  grupo_id: string | null;
  categoria: string | null;
  severidade: FlagSeveridade;
  /** Never message text (LGPD §6) — a categorized explanation only. */
  justificativa: string | null;
  modelo: string | null;
  prompt_versao: string | null;
  estado: FlagEstado;
  resolvido_por: string | null;
  resolvido_em: string | null;
  created_at: string;
}

export interface FlagListResponse {
  items: MensagemFlag[];
  total: number;
}

export interface FlagsParams {
  estado?: FlagEstado;
  severidade?: FlagSeveridade;
  page?: number;
  page_size?: number;
}

export interface ResolverFlagInput {
  estado: "resolvida" | "descartada";
  nota?: string;
}

const flagsKeys = {
  all: ["whatsapp", "flags"] as const,
  list: (params?: FlagsParams) => ["whatsapp", "flags", "list", params ?? {}] as const,
};

/** admin+moderador — moderation IS the moderador's job (contract endpoint 20). */
export function useFlagsWhatsApp(params?: FlagsParams) {
  return useQuery({
    queryKey: flagsKeys.list(params),
    queryFn: () => api.get<FlagListResponse>("/api/whatsapp/flags", params),
  });
}

export function useResolverFlag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string } & ResolverFlagInput) =>
      api.post<MensagemFlag>(`/api/whatsapp/flags/${id}/resolver`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: flagsKeys.all }),
  });
}
