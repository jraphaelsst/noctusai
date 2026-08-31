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
    onSuccess: () => qc.invalidateQueries({ queryKey: MARCA_QUERY_KEY }),
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
export function useAcessos(clienteId: string | undefined) {
  const query = useQuery({
    queryKey: [...COFRE_QUERY_KEY, clienteId],
    queryFn: () => api.get<Acesso[]>(`/api/marcas/acessos/${clienteId}`),
    enabled: Boolean(clienteId),
  });
  return {
    ...query,
    acessos: query.data ?? [],
    loading: query.isPending && !query.data,
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
