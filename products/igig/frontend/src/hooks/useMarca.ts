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
import { useMutation, useQuery } from "@tanstack/react-query";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { api } from "@/lib/api";
import { addTo, patchById, removeById, rowOps } from "@/lib/cacheOps";

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
  /** Which marca this actually is — lets the sidebar pre-select the right
   * chip in its switcher (roadmap R9: a cliente can carry N marcas). */
  marca_id: string | null;
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
 *
 * `marcaId`, when known (a pauta's own `marca_id`), picks THAT brand instead
 * of the server's "first alphabetically" fallback — a cliente with N marcas
 * has no single obvious "the" brand otherwise (achado 2).
 */
export function useRepertorio(clienteId: string | undefined, marcaId?: string | null) {
  const query = useQuery({
    queryKey: ["igig", "repertorio", clienteId, marcaId ?? ""],
    queryFn: () =>
      api.get<Repertorio>(
        `/api/marcas/repertorio/${clienteId}`,
        marcaId ? { marca_id: marcaId } : {},
      ),
    enabled: Boolean(clienteId),
  });
  return {
    ...query,
    repertorio: query.data ?? null,
    loading: query.isPending && !query.data,
  };
}

/**
 * The Módulo 2 sidebar reads the repertório — a DIFFERENT query key derived
 * from the marca. It refreshes in the background after every marca write, or a
 * designer keeps working against the palette that was just replaced.
 */
const REPERTORIO = [["igig", "repertorio"]];

export function useCriarMarca() {
  type Vars = Partial<Marca> & { cliente_id: string; nome: string };
  return useCacheWriteMutation<Marca, Vars>({
    mutationFn: (payload) => api.post<Marca>("/api/marcas", payload),
    // Into the everyone list and its cliente's list.
    targets: (v) => [
      addTo<Marca, Vars>([...MARCA_QUERY_KEY, ""]),
      addTo<Marca, Vars>([...MARCA_QUERY_KEY, v.cliente_id]),
    ],
    invalidate: REPERTORIO,
  });
}

export function useAtualizarMarca() {
  type Vars = Partial<Marca> & { id: string };
  return useCacheWriteMutation<Marca, Vars>({
    mutationFn: ({ id, ...patch }) => api.patch<Marca>(`/api/marcas/${id}`, patch),
    targets: [patchById<Marca, Vars>(MARCA_QUERY_KEY, (v) => v.id, ({ id: _id, ...changes }) => changes)],
    invalidate: REPERTORIO,
  });
}

/**
 * Delete a marca. Backend: `DELETE /api/marcas/{id}` → `{ok: true}`. Pautas
 * that pointed at it keep existing (`pauta.marca_id` is ON DELETE SET NULL);
 * the cofre is per CLIENTE and is untouched.
 */
export function useRemoverMarca() {
  return useCacheWriteMutation<{ ok: boolean }, string>({
    mutationFn: (id) => api.delete<{ ok: boolean }>(`/api/marcas/${id}`),
    targets: [removeById<{ ok: boolean }, string>(MARCA_QUERY_KEY, (id) => id)],
    invalidate: REPERTORIO,
  });
}

/**
 * Upload a brand logo (Módulo 2's "campos de upload de logotipos PNG/SVG").
 *
 * `api.upload`, never `api.post` — the latter JSON.stringify's its body, and
 * `JSON.stringify(new FormData())` is `"{}"`, which reaches a multipart
 * endpoint as an empty JSON object and 422s as if the backend were broken.
 *
 * The new logo is written onto the marca as soon as the server answers; the
 * repertório (the sidebar renders the logo) refreshes in the background.
 */
export function useEnviarLogo() {
  type Vars = { marcaId: string; arquivo: File };
  return useCacheWriteMutation<{ storage_key: string; url: string | null }, Vars>({
    mutationFn: ({ marcaId, arquivo }) => {
      const form = new FormData();
      form.append("arquivo", arquivo);
      return api.upload<{ storage_key: string; url: string | null }>(
        `/api/marcas/${marcaId}/logo`,
        form,
      );
    },
    targets: (v) => [
      {
        queryKey: MARCA_QUERY_KEY,
        match: "prefix",
        commit: (old, saved) => (saved.url ? rowOps.patch(old, v.marcaId, { logo_url: saved.url }) : old),
      },
    ],
    invalidate: REPERTORIO,
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
  type Vars = { cliente_id: string; rotulo: string; plataforma?: string; url?: string; usuario?: string; senha?: string };
  return useCacheWriteMutation<Acesso, Vars>({
    mutationFn: (payload) => api.post<Acesso>("/api/marcas/acessos", payload),
    // The entry (never the password) joins the cliente's cofre as soon as the server answers.
    targets: (v) => [addTo<Acesso, Vars>([...COFRE_QUERY_KEY, v.cliente_id])],
  });
}

/**
 * Edit an existing vault entry. Backend mirror: `marca_router.atualizar_acesso`
 * (PATCH `/api/marcas/acessos/{id}`) — open to any org member, same as
 * creating one; only REVEALING a stored password is admin-gated.
 *
 * `rotulo`/`plataforma`/`url`/`usuario`/`observacoes` accept explicit `null`
 * to CLEAR the field — the backend moved to `exclude_unset` so a field only
 * changes when the key is actually present in the body (omit it entirely to
 * leave it untouched). `senha` stays the one deliberate exception: omitted
 * OR blank means "keep the current password", never a way to clear it.
 */
export function useAtualizarAcesso() {
  type Vars = {
    id: string;
    rotulo?: string | null;
    plataforma?: string | null;
    url?: string | null;
    usuario?: string | null;
    senha?: string;
    observacoes?: string | null;
  };
  return useCacheWriteMutation<Acesso, Vars>({
    mutationFn: ({ id, ...patch }) => api.patch<Acesso>(`/api/marcas/acessos/${id}`, patch),
    // `senha` never enters the cache (the API never returns one; `tem_senha` comes from the answer).
    targets: [patchById<Acesso, Vars>(COFRE_QUERY_KEY, (v) => v.id, ({ id: _id, senha: _senha, ...changes }) => changes)],
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
  return useMutation({ // noc-allow: invalidate-only — an audited admin-only reveal, deliberately never cached (a decrypted credential must not sit in the query client)
    mutationFn: (acessoId: string) =>
      api.post<{ senha: string }>(`/api/marcas/acessos/${acessoId}/revelar`, {}),
  });
}

export function useRemoverAcesso() {
  return useCacheWriteMutation<{ ok: boolean }, string>({
    mutationFn: (acessoId) => api.delete<{ ok: boolean }>(`/api/marcas/acessos/${acessoId}`),
    targets: [removeById<{ ok: boolean }, string>(COFRE_QUERY_KEY, (id) => id)],
  });
}
