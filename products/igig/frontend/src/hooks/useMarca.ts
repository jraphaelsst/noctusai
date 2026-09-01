/**
 * Central da Marca hooks — Módulo 2.
 *
 * Backend mirror: `app/routers/marca_router.py`.
 *
 * The Cofre hooks deliberately have no "list passwords" shape: the API never
 * returns one, and modelling it here would invite a component to expect it.
 * `revelar` is a mutation, not a query — it is an audited, admin-only action
 * with a server-side log, and caching it would defeat both.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

// ─── Types (mirror backend app/schemas/marca.py) ───────────────────────
export interface CorPaleta {
  nome: string;
  hex: string;
}

export interface LinhaEditorial {
  nome: string;
  descricao?: string | null;
}

export interface Persona {
  nome: string;
  avatar_url?: string | null;
  faixa_etaria?: string | null;
  ocupacao?: string | null;
  dores: string[];
  desejos: string[];
}

export type NivelFormalidade = "informal" | "neutro" | "formal";

export interface Marca {
  id: string;
  org_id: string;
  cliente_id: string;
  nome: string;
  logo_url: string | null;
  paleta: CorPaleta[];
  tom_de_voz: string | null;
  termos_proibidos: string | null;
  nivel_formalidade: NivelFormalidade | null;
  linhas_editoriais: LinhaEditorial[];
  personas: Persona[];
}

/** The compact payload the persistent sidebar renders. */
export interface Repertorio {
  cliente_nome: string | null;
  marca_nome: string | null;
  logo_url: string | null;
  paleta: CorPaleta[];
  tom_de_voz: string | null;
  termos_proibidos: string | null;
  nivel_formalidade: string | null;
  linhas_editoriais: LinhaEditorial[];
}

/** A vault entry. There is no password field — by design, server-side. */
export interface Acesso {
  id: string;
  cliente_id: string;
  rotulo: string;
  plataforma: string | null;
  url: string | null;
  usuario: string | null;
  observacoes: string | null;
  tem_senha: boolean;
}

export const MARCA_QUERY_KEY = ["igig", "marcas"] as const;
export const COFRE_QUERY_KEY = ["igig", "cofre"] as const;

export function useMarcas(clienteId?: string) {
  const query = useQuery({
    queryKey: [...MARCA_QUERY_KEY, clienteId ?? ""],
    queryFn: () =>
      api.get<Marca[]>("/api/marcas", clienteId ? { cliente_id: clienteId } : {}),
  });
  return {
    ...query,
    marcas: query.data ?? [],
    loading: query.isPending && !query.data,
  };
}

/**
 * The persistent brand sidebar's data.
 *
 * A client with no brand yet returns an empty repertório with 200, so this
 * hook has no "not found" state — the sidebar degrades to showing just the
 * client's name rather than an error over someone's work.
 */
export function useRepertorio(clienteId: string | undefined) {
  const query = useQuery({
    queryKey: ["igig", "repertorio", clienteId],
    queryFn: () => api.get<Repertorio>(`/api/marcas/repertorio/${clienteId}`),
    enabled: Boolean(clienteId),
  });
  return {
    ...query,
    repertorio: query.data ?? null,
    loading: query.isPending && !query.data,
  };
}

export function useCriarMarca() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<Marca> & { cliente_id: string; nome: string }) =>
      api.post<Marca>("/api/marcas", payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: MARCA_QUERY_KEY });
      // Same reason as `useAtualizarMarca`: the Módulo 2 sidebar reads the
      // repertório, which is a DIFFERENT query key. Without this the sidebar
      // keeps saying "este cliente ainda não tem marca cadastrada" while the
      // brand editor is open right next to it.
      qc.invalidateQueries({ queryKey: ["igig", "repertorio"] });
    },
  });
}

export function useAtualizarMarca() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...patch }: Partial<Marca> & { id: string }) =>
      api.patch<Marca>(`/api/marcas/${id}`, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: MARCA_QUERY_KEY });
      // The sidebar reads the same brand — refresh it too, or a designer keeps
      // working against the palette that was just replaced.
      qc.invalidateQueries({ queryKey: ["igig", "repertorio"] });
    },
  });
}

// ─── Cofre de Acessos ──────────────────────────────────────────────────
/** Mirror of backend `AcessosOut` — the vault entries PLUS whether a new
 * password can be stored. Wrapped (rather than a flag on each `Acesso`,
 * as `IntegracaoStatus` does) because `itens` can legitimately be empty,
 * and an empty list must not be read as "cofre configured, no entries yet"
 * when it's actually "cofre not configured at all". */
export interface AcessosResponse {
  cofre_configurado: boolean;
  itens: Acesso[];
}

export function useAcessos(clienteId: string | undefined) {
  const query = useQuery({
    queryKey: [...COFRE_QUERY_KEY, clienteId],
    queryFn: () => api.get<AcessosResponse>(`/api/marcas/acessos/${clienteId}`),
    enabled: Boolean(clienteId),
  });
  return {
    ...query,
    acessos: query.data?.itens ?? [],
    loading: query.isPending && !query.data,
    // `null` while unknown (not yet loaded / no client selected) so the
    // page can tell that apart from a real "not configured" — and never
    // flash a false warning before the first response arrives.
    cofreConfigurado: query.data ? query.data.cofre_configurado : null,
  };
}

export function useCriarAcesso() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      cliente_id: string;
      rotulo: string;
      plataforma?: string;
      url?: string;
      usuario?: string;
      senha?: string;
    }) => api.post<Acesso>("/api/marcas/acessos", payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: COFRE_QUERY_KEY }),
  });
}

/**
 * Edit an existing vault entry. Backend mirror: `marca_router.atualizar_acesso`
 * (PATCH `/api/marcas/acessos/{id}`) — open to any org member, same as
 * creating one; only REVEALING a stored password is admin-gated. `senha` is
 * optional here too: omitting it edits the other fields without touching the
 * stored password, matching `AcessoUpdate`'s `exclude_none` semantics
 * server-side.
 */
export function useAtualizarAcesso() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...patch }: {
      id: string;
      rotulo?: string;
      plataforma?: string;
      url?: string;
      usuario?: string;
      senha?: string;
      observacoes?: string;
    }) => api.patch<Acesso>(`/api/marcas/acessos/${id}`, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: COFRE_QUERY_KEY }),
  });
}

/**
 * Reveal ONE password. Admin/owner only; the server logs every call.
 *
 * A mutation rather than a query on purpose: caching a decrypted credential
 * in the query client would keep it in memory long after the user finished
 * with it, and would let a re-render surface it without another audited call.
 */
export function useRevelarSenha() {
  return useMutation({
    mutationFn: (acessoId: string) =>
      api.post<{ senha: string }>(`/api/marcas/acessos/${acessoId}/revelar`, {}),
  });
}

export function useRemoverAcesso() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (acessoId: string) =>
      api.delete<{ ok: boolean }>(`/api/marcas/acessos/${acessoId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: COFRE_QUERY_KEY }),
  });
}
