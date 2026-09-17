/**
 * Transmissões hooks — community-m3-contract.md §3#Transmissões.
 *
 * `Transmissao.destinos` is embedded directly rather than fetched through a
 * separate detail call: the contract lists only `GET /api/whatsapp/
 * transmissoes` (list) with no single-resource GET, yet the FE spec asks for
 * a "per-destino delivery table" — so the list item is assumed to carry its
 * `transmissao_destinos` rows inline (same denormalize-instead-of-join
 * convention as `Lote.itens`, which IS contracted that way on the single-GET
 * endpoint). Flagged in this delivery's `drift-found:` footer together with
 * the other two inferred shapes (`Grupo` roster, `Lote.grupo_nome`).
 */
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type TransmissaoTipo = "anuncio" | "lembrete_evento" | "conteudo";
export type TransmissaoEstado = "rascunho" | "agendada" | "enviando" | "enviada" | "falhou";
export type TransmissaoDestinoEstado = "pendente" | "enviado" | "falhou";

export interface TransmissaoDestino {
  id: string;
  grupo_id: string;
  /** Denormalized — see module header. */
  grupo_nome?: string;
  estado: TransmissaoDestinoEstado;
  provider_message_id: string | null;
  erro: string | null;
  enviado_em: string | null;
}

export interface Transmissao {
  id: string;
  titulo: string;
  corpo: string;
  tipo: TransmissaoTipo;
  estado: TransmissaoEstado;
  agendada_para: string | null;
  enviada_em: string | null;
  criada_por: string | null;
  /** Assumed embedded — see module header. Optional so a leaner backend
   * shape never crashes the delivery table (renders empty). */
  destinos?: TransmissaoDestino[];
}

export interface TransmissaoListResponse {
  items: Transmissao[];
  total: number;
}

export interface TransmissoesParams {
  estado?: TransmissaoEstado;
  page?: number;
  page_size?: number;
}

export interface TransmissaoCreateInput {
  titulo: string;
  corpo: string;
  tipo: TransmissaoTipo;
  grupo_ids: string[];
  /** Omit to save as `rascunho`; set to schedule as `agendada`. */
  agendada_para?: string;
}

export type TransmissaoUpdateInput = Partial<Omit<TransmissaoCreateInput, "grupo_ids">> & {
  grupo_ids?: string[];
};

export interface EnviarTransmissaoResponse {
  transmissao_id: string;
  destinos: number;
}

const transmissoesKeys = {
  all: ["whatsapp", "transmissoes"] as const,
  list: (params?: TransmissoesParams) => ["whatsapp", "transmissoes", "list", params ?? {}] as const,
};

export function useTransmissoes(params?: TransmissoesParams) {
  return useQuery({
    queryKey: transmissoesKeys.list(params),
    queryFn: () => api.get<TransmissaoListResponse>("/api/whatsapp/transmissoes", params),
    placeholderData: keepPreviousData,
  });
}

/** `grupo_ids` non-empty; an unknown id -> 422 (rendered via `errorMessage`). */
export function useCreateTransmissao() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: TransmissaoCreateInput) => api.post<Transmissao>("/api/whatsapp/transmissoes", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: transmissoesKeys.all }),
  });
}

/** `rascunho`/`agendada` only, else 409 — the form disables itself once the
 * consumer knows the current `estado` is neither. */
export function useUpdateTransmissao() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string } & TransmissaoUpdateInput) =>
      api.patch<Transmissao>(`/api/whatsapp/transmissoes/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: transmissoesKeys.all }),
  });
}

/** Enqueues one job per destino, paced on the slow `whatsapp_groups`
 * bucket — 202, never synchronous. All-failed still returns 202 with
 * `estado: "falhou"` set server-side; the FE never treats 202 as success
 * text beyond "enviando", it re-fetches and shows the real per-destino
 * state. */
export function useEnviarTransmissao() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<EnviarTransmissaoResponse>(`/api/whatsapp/transmissoes/${id}/enviar`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: transmissoesKeys.all }),
  });
}

/** `rascunho`/`agendada` only, 204. */
export function useDeleteTransmissao() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/whatsapp/transmissoes/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: transmissoesKeys.all }),
  });
}
