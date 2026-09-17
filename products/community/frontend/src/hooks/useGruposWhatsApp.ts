/**
 * Grupos WhatsApp hooks — community-m3-contract.md §3#Grupos.
 *
 * `useGrupoMembros` targets `GET /api/whatsapp/grupos/{id}/membros`, which is
 * NOT in the contract's endpoint list (1-7 cover create/list/detail/patch/
 * sincronizar-roster/convite/sessao only) — the FE spec still asks for "row
 * → detail drawer with roster", so a read path for the observed roster must
 * exist somewhere. This is the same shape of gap amendment A17 closed for
 * module 2 (a public tier-listing endpoint the contract's prose implied but
 * never declared): built to a reasonable, convention-following inference
 * (paginated `{items,total}`, denormalized `membro_nome`/`telefone` exactly
 * like `Membro.plano_nome`/`Assinatura.membro_nome` elsewhere in this
 * product) and flagged in this delivery's `drift-found:` footer for the
 * tech-lead to ratify or redirect.
 *
 * `useGrupoConvite` is a manual (`enabled: false`) query — "click-to-reveal"
 * per the contract, never fetched on mount, and the whole calling UI is
 * gated on `isAdmin` client-side (`WhatsApp.tsx`) so a `moderador` never
 * renders the button that would trigger it — the endpoint itself also 403s
 * for `moderador` (D3), so this is belt-and-suspenders, not the only guard.
 */
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type GrupoAcao = "adicionar" | "remover";

export interface Grupo {
  id: string;
  nome: string;
  chat_id: string;
  descricao: string | null;
  ativo: boolean;
  somente_admin: boolean;
  participantes_observados: number;
  /** Denormalized, contract-implied but unlisted (see module 1's
   * `Plano.membros_ativos` precedent) — members entitled to this group
   * who are not yet observed as participants. Optional so an older/partial
   * backend shape never crashes the table. */
  membros_elegiveis?: number;
  sincronizado_em: string | null;
  created_at: string;
  updated_at: string;
}

export interface GrupoListResponse {
  items: Grupo[];
  total: number;
}

export interface GruposParams {
  ativo?: boolean;
  page?: number;
  page_size?: number;
}

/** Either register an existing WhatsApp group by `chat_id`, or ask the
 * backend to create one (`criar: true` + `nome`) — mutually exclusive, per
 * contract endpoint 2. */
export type GrupoCreateInput =
  | { chat_id: string; criar?: false; descricao?: string | null; somente_admin?: boolean }
  | { criar: true; nome: string; descricao?: string | null; somente_admin?: boolean };

export interface GrupoUpdateInput {
  nome?: string;
  descricao?: string | null;
  ativo?: boolean;
  somente_admin?: boolean;
}

export interface SincronizarRosterResponse {
  participantes: number;
}

export interface GrupoConvite {
  link: string;
}

export type SessaoEstado = "WORKING" | "SCAN_QR_CODE" | "STARTING" | "FAILED" | "STOPPED" | string;

export interface SessaoWhatsApp {
  estado: SessaoEstado;
  sessao: string;
}

/** One `grupo_membros` roster row (see the module-header note on
 * `GET .../membros` being an inferred, not-yet-contracted endpoint). */
export interface GrupoMembro {
  id: string;
  participante_jid: string;
  membro_id: string | null;
  /** Denormalized — null when the participant has no matching `membros` row. */
  membro_nome: string | null;
  telefone: string | null;
  papel: "participante" | "admin" | "superadmin";
  visto_em: string | null;
}

export interface GrupoMembrosResponse {
  items: GrupoMembro[];
  total: number;
}

const gruposKeys = {
  all: ["whatsapp", "grupos"] as const,
  list: (params?: GruposParams) => ["whatsapp", "grupos", "list", params ?? {}] as const,
  detail: (id: string) => ["whatsapp", "grupos", "detail", id] as const,
  membros: (id: string) => ["whatsapp", "grupos", id, "membros"] as const,
  convite: (id: string) => ["whatsapp", "grupos", id, "convite"] as const,
  sessao: ["whatsapp", "sessao"] as const,
};

export function useGruposWhatsApp(params?: GruposParams) {
  return useQuery({
    queryKey: gruposKeys.list(params),
    queryFn: () => api.get<GrupoListResponse>("/api/whatsapp/grupos", params),
    placeholderData: keepPreviousData,
  });
}

export function useGrupoWhatsApp(id?: string | null) {
  return useQuery({
    queryKey: gruposKeys.detail(id ?? ""),
    queryFn: () => api.get<Grupo>(`/api/whatsapp/grupos/${id}`),
    enabled: !!id,
  });
}

/** See the module header — an inferred endpoint, not in the contract's
 * endpoint list. `enabled` defaults to "whenever an id is given" so the
 * detail drawer can fetch it eagerly once open. */
export function useGrupoMembros(id?: string | null, params?: { page?: number; page_size?: number }) {
  return useQuery({
    queryKey: [...gruposKeys.membros(id ?? ""), params ?? {}] as const,
    queryFn: () => api.get<GrupoMembrosResponse>(`/api/whatsapp/grupos/${id}/membros`, params),
    enabled: !!id,
    placeholderData: keepPreviousData,
  });
}

export function useCreateGrupoWhatsApp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: GrupoCreateInput) => api.post<Grupo>("/api/whatsapp/grupos", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: gruposKeys.all }),
  });
}

export function useUpdateGrupoWhatsApp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string } & GrupoUpdateInput) =>
      api.patch<Grupo>(`/api/whatsapp/grupos/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: gruposKeys.all }),
  });
}

/** WAHA unreachable -> 502 (contract endpoint 5); render via `errorMessage`. */
export function useSincronizarRoster() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<SincronizarRosterResponse>(`/api/whatsapp/grupos/${id}/sincronizar-roster`, {}),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: gruposKeys.all });
      qc.invalidateQueries({ queryKey: gruposKeys.membros(id) });
    },
  });
}

/** Admin-only, click-to-reveal (never auto-fetched). Call `refetch()` from a
 * click handler gated on `isAdmin`. */
export function useGrupoConvite(id?: string | null) {
  return useQuery({
    queryKey: gruposKeys.convite(id ?? ""),
    queryFn: () => api.get<GrupoConvite>(`/api/whatsapp/grupos/${id}/convite`),
    enabled: false,
    retry: false,
  });
}

export function useRevogarConvite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post(`/api/whatsapp/grupos/${id}/convite/revogar`, {}),
    onSuccess: (_data, id) => qc.removeQueries({ queryKey: gruposKeys.convite(id) }),
  });
}

/** Read-through `get_session` — no QR endpoint exists; pairing is an
 * operator action outside this UI. */
export function useSessaoWhatsApp() {
  return useQuery({
    queryKey: gruposKeys.sessao,
    queryFn: () => api.get<SessaoWhatsApp>("/api/whatsapp/sessao"),
  });
}
