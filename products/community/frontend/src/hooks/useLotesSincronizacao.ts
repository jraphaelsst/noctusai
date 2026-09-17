/**
 * Lotes de sincronização hooks — community-m3-contract.md §3#Sincronização,
 * the manager-confirmed state machine:
 * `proposto -> confirmado -> aplicado | aplicado_parcial`, or
 * `-> cancelado` / `-> expirado`.
 *
 * `grupo_nome` on `Lote` is a denormalization ASSUMPTION, not literal
 * contract text: the migration's `lotes_sincronizacao` table has no such
 * column, but every other list/detail response in this product denormalizes
 * its parent name for display (`Membro.plano_nome`, `Assinatura.membro_nome`
 * + `plano_nome`, `Grupo.membros_elegiveis`) so the FE never joins. Flagged
 * in this delivery's `drift-found:` footer alongside the `/membros` roster
 * gap in `useGruposWhatsApp.ts`.
 *
 * `Lote.itens[].telefone` is ALWAYS rendered through `maskPhone()` by the
 * consuming page (`whatsapp/Sincronizacao.tsx`), never inline here or raw —
 * the confirm-then-apply preview masks to the last 4 digits regardless of
 * role (community-m3-contract.md §4), so masking is a display-layer
 * decision applied uniformly rather than trusted to arrive pre-masked.
 */
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { GrupoAcao } from "@/hooks/useGruposWhatsApp";

export type LoteEstado =
  | "proposto"
  | "confirmado"
  | "aplicado"
  | "aplicado_parcial"
  | "cancelado"
  | "expirado";

export type LoteItemResultado =
  | "pendente"
  | "adicionado"
  | "removido"
  | "convite_necessario"
  | "falhou";

export interface LoteItem {
  id: string;
  membro_id: string | null;
  /** Denormalized; null when the participant has no matching `membros` row
   * (still shown in the preview by `participante_jid`, never dropped). */
  membro_nome: string | null;
  participante_jid: string;
  telefone: string | null;
  resultado: LoteItemResultado;
  codigo_waha: number | null;
  processado_em: string | null;
}

/** Members left out of the computed diff (e.g. no `telefone` on file) —
 * contract endpoint 8: "never silently dropped". */
export interface LoteIgnorado {
  membro_id: string;
  nome: string;
  motivo: string;
}

export interface Lote {
  id: string;
  grupo_id: string;
  /** Denormalization assumption — see module header. */
  grupo_nome?: string;
  acao: GrupoAcao;
  estado: LoteEstado;
  total_itens: number;
  proposto_por: string | null;
  confirmado_por: string | null;
  proposto_em: string | null;
  confirmado_em: string | null;
  aplicado_em: string | null;
  expira_em: string;
  motivo_falha: string | null;
  itens: LoteItem[];
  ignorados: LoteIgnorado[];
}

export interface LoteListResponse {
  items: Lote[];
  total: number;
}

export interface LotesParams {
  grupo_id?: string;
  estado?: LoteEstado;
  page?: number;
  page_size?: number;
}

/** The one `convite_necessario` member plus the group's invite link, so a
 * manager can invite them by hand (contract endpoint 13, admin-only). */
export interface ConvitePendenteItem {
  membro_id: string | null;
  nome: string | null;
  telefone: string | null;
  participante_jid: string;
}

export interface ConvitesPendentesResponse {
  items: ConvitePendenteItem[];
  total: number;
  /** The group's invite link — present because this whole endpoint is
   * admin-only (endpoint 13), never separately redacted. */
  link: string | null;
}

const lotesKeys = {
  all: ["whatsapp", "lotes"] as const,
  list: (params?: LotesParams) => ["whatsapp", "lotes", "list", params ?? {}] as const,
  detail: (id: string) => ["whatsapp", "lotes", "detail", id] as const,
  convitesPendentes: (id: string) => ["whatsapp", "lotes", id, "convites-pendentes"] as const,
};

export function useLotesSincronizacao(params?: LotesParams) {
  return useQuery({
    queryKey: lotesKeys.list(params),
    queryFn: () => api.get<LoteListResponse>("/api/whatsapp/lotes", params),
    placeholderData: keepPreviousData,
  });
}

export function useLoteSincronizacao(id?: string | null) {
  return useQuery({
    queryKey: lotesKeys.detail(id ?? ""),
    queryFn: () => api.get<Lote>(`/api/whatsapp/lotes/${id}`),
    enabled: !!id,
  });
}

/** Computes only — the sole WAHA call this endpoint makes is the roster
 * read. 409 when the group already has a non-terminal lote, or the diff
 * exceeds `LOTE_MAX_ITENS`; both render via `errorMessage`, never retried
 * automatically. */
export function useCreateLoteSincronizacao() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ grupoId, acao }: { grupoId: string; acao: GrupoAcao }) =>
      api.post<Lote>(`/api/whatsapp/grupos/${grupoId}/lotes`, { acao }),
    onSuccess: () => qc.invalidateQueries({ queryKey: lotesKeys.all }),
  });
}

/** Body is always `{confirmo: true}` — the checkbox + typed-confirm UI is
 * the gate; this mutation never fires without both (`Sincronizacao.tsx`). */
export function useConfirmarLote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<Lote>(`/api/whatsapp/lotes/${id}/confirmar`, { confirmo: true }),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: lotesKeys.all });
      qc.invalidateQueries({ queryKey: lotesKeys.detail(id) });
    },
  });
}

/** The ONLY endpoint that mutates WhatsApp membership. Requires
 * `confirmado`, else 409 (rendered, never retried automatically — ban-risk
 * posture §5). Returns 200 even for `aplicado_parcial`, never 5xx. */
export function useAplicarLote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<Lote>(`/api/whatsapp/lotes/${id}/aplicar`, {}),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: lotesKeys.all });
      qc.invalidateQueries({ queryKey: lotesKeys.detail(id) });
    },
  });
}

export function useCancelarLote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<Lote>(`/api/whatsapp/lotes/${id}/cancelar`, {}),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: lotesKeys.all });
      qc.invalidateQueries({ queryKey: lotesKeys.detail(id) });
    },
  });
}

/** Admin-only (contract endpoint 13) — gate the calling UI on `isAdmin`
 * client-side too, so the whole "Convites pendentes" panel (link included)
 * is genuinely absent from the DOM for a `moderador`, not merely unfetched. */
export function useConvitesPendentes(loteId?: string | null, enabled = true) {
  return useQuery({
    queryKey: lotesKeys.convitesPendentes(loteId ?? ""),
    queryFn: () => api.get<ConvitesPendentesResponse>(`/api/whatsapp/lotes/${loteId}/convites-pendentes`),
    enabled: !!loteId && enabled,
  });
}
