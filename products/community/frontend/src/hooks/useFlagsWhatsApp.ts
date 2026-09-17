/**
 * Mensagem-flags hooks — community-m3-contract.md §3#Ingest-+-flags
 * (endpoint 20).
 *
 * HOOK ONLY — no page. §7 "Out of scope for module 3" explicitly names "the
 * moderation queue UI (module 8 consumes the flags this module produces)":
 * this module ingests messages and writes `mensagem_flags` rows, but the
 * human-review surface for them ships in module 8. The data-access hook is
 * built now (per this dispatch's brief, which lists `useFlagsWhatsApp`
 * alongside the three page-owning hooks) so module 8 does not have to
 * reverse-engineer the endpoint shape from the migration later.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type FlagSeveridade = "baixa" | "media" | "alta";
export type FlagEstado = "aberta" | "resolvida" | "descartada";

export interface MensagemFlag {
  id: string;
  mensagem_id: string;
  categoria: string;
  severidade: FlagSeveridade;
  /** Never message text (LGPD §6) — a categorized explanation only. */
  justificativa: string;
  modelo: string;
  prompt_versao: string;
  estado: FlagEstado;
  resolvido_por: string | null;
  resolvido_em: string | null;
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
