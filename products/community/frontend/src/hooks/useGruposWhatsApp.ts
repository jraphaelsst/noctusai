/**
 * Grupos WhatsApp hooks — community-m3-contract.md §3#Grupos.
 *
 * `useGrupoMembros` used to target `GET /api/whatsapp/grupos/{id}/membros`
 * — an endpoint that was never built (not in the contract's list, items
 * 1-7 cover create/list/detail/patch/sincronizar-roster/convite/sessao
 * only, and no router ever declared it), so the roster drawer 404'd on
 * every open. The detail endpoint ALREADY embeds the roster
 * (`app/routers/whatsapp_grupos_router.py::get_grupo` sets
 * `body["membros"]`, role-filtered — `GrupoRosterItem` for `admin`,
 * `GrupoRosterItemModerador` for `moderador`, D3's phone-redaction
 * boundary). `useGrupoMembros` now `select`s that field off the SAME
 * query `useGrupoWhatsApp` reads (`gruposKeys.detail(id)`) instead of
 * issuing a second, non-existent request (2026-09-20 wiring audit,
 * task 7).
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
  /** Only present on the DETAIL fetch (`GET /grupos/{id}`) — the list
   * endpoint's rows never carry a roster. Role-filtered server-side. */
  membros?: GrupoMembro[];
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

/** One roster row off `Grupo.membros` — shape mirrors the backend's
 * `GrupoRosterItem` (`admin`) / `GrupoRosterItemModerador` (`moderador`,
 * D3): no `id` field (there is no roster-row primary key in the
 * response), `participante_jid` OMITTED for `moderador` (it embeds the
 * raw phone digits), and `telefone` (raw) vs `telefone_mascarado`
 * (pre-redacted server-side) depending on role — never both. */
export interface GrupoMembro {
  participante_jid?: string;
  membro_id: string | null;
  /** Denormalized — null when the participant has no matching `membros` row. */
  membro_nome: string | null;
  telefone?: string | null;
  telefone_mascarado?: string | null;
  papel: "participante" | "admin" | "superadmin";
  visto_em: string;
}

const gruposKeys = {
  all: ["whatsapp", "grupos"] as const,
  list: (params?: GruposParams) => ["whatsapp", "grupos", "list", params ?? {}] as const,
  detail: (id: string) => ["whatsapp", "grupos", "detail", id] as const,
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

/** See the module header — `select`s `.membros` off the SAME detail
 * query `useGrupoWhatsApp` reads (identical `queryKey`), so opening the
 * roster drawer never issues a second request beyond the one the detail
 * fetch already makes, and a `sincronizar-roster` invalidation of that
 * query key refreshes both. */
export function useGrupoMembros(id?: string | null) {
  return useQuery({
    queryKey: gruposKeys.detail(id ?? ""),
    queryFn: () => api.get<Grupo>(`/api/whatsapp/grupos/${id}`),
    enabled: !!id,
    select: (grupo) => grupo.membros ?? [],
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
    // `gruposKeys.all` is a PREFIX of both the list AND detail query keys
    // (`["whatsapp","grupos", ...]`), so this one invalidation already
    // refreshes `useGrupoMembros`'s query too — it reads the SAME detail
    // key, not a separate `membros` key (removed, 2026-09-20 wiring
    // audit task 7).
    onSuccess: () => qc.invalidateQueries({ queryKey: gruposKeys.all }),
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
