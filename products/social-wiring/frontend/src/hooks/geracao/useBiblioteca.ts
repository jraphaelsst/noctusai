/**
 * Biblioteca (virais) + Minha Biblioteca hooks over
 * `/api/media-creation/biblioteca/*` (contract §4.3 #7–19) and the
 * `origem:'biblioteca'` headline batch (§4.4 #20).
 *
 * Loading rule (lying-loading-state.md): every query hook returns
 * `showSkeleton = isPending && !data` and `isRefreshing = isFetching && !!data`,
 * with `placeholderData` on key changes — never `isLoading`. Mutations
 * write the server row into the cached reads and settle by invalidating the
 * whole `["sw","geracao"]` family.
 */
import { handOffToPolling, jobPolling } from "@noctusai/lib";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { listOps, pageOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { useMemo } from "react";

import type { FiltrosViral } from "@/components/geracao/biblioteca/filtros";
import type { HeadlineLote, Referencia, ViralCard } from "@/types/geracao";
import type {
  PerfilBiblioteca,
  PerfisPage,
  ViralDetalheBiblioteca,
} from "@/types/bibliotecaPlataforma";
import { GERACAO_KEY } from "@/lib/geracaoKeys";

interface Envelope<T> {
  success?: boolean;
  data: T;
}
const unwrap = <T>(res: Envelope<T>): T => res.data;

const BASE = "/api/media-creation/biblioteca";
const BIB_KEY = [...GERACAO_KEY, "biblioteca"] as const;
export const VIRAIS_POR_PAGINA = 24;

export interface ViraisPage {
  items: ViralCard[];
  total: number;
  page: number;
  filtro_automatico: boolean;
  /** Kill-switch state of the library ingestion. */
  ingestao_ativa: boolean;
}

export function viraisParams(marcaId: string, f: FiltrosViral): string {
  const p = new URLSearchParams({ marca_id: marcaId, ordem: f.ordem, page: String(f.page) });
  f.nichos.forEach((n) => p.append("nichos", String(n)));
  f.profissoes.forEach((n) => p.append("profissoes", String(n)));
  // A profile view never auto-filters (page-map-v2 §10.4).
  if (f.pool) p.set("pool", f.pool);
  else if (f.verTodos || f.perfilId) p.set("ver_todos", "true");
  if (f.q.trim()) {
    p.set("q", f.q.trim());
    p.set("buscar_em", f.buscarEm);
  }
  if (f.dataDe) p.set("data_de", f.dataDe);
  if (f.dataAte) p.set("data_ate", f.dataAte);
  if (f.viewsMin != null) p.set("views_min", String(f.viewsMin));
  if (f.likesMin != null) p.set("likes_min", String(f.likesMin));
  if (f.commentsMin != null) p.set("comments_min", String(f.commentsMin));
  if (f.perfilId) p.set("perfil_id", f.perfilId);
  if (f.formatoId != null) p.set("formato_id", String(f.formatoId));
  if (f.codigo != null) p.set("codigo", String(f.codigo));
  p.set("somente_virais", f.somenteVirais ? "true" : "false");
  return p.toString();
}

/** Library grid (#7). */
export function useViraisBiblioteca(marcaId: string | null, filtros: FiltrosViral) {
  const query = useQuery({
    queryKey: [...BIB_KEY, "virais", marcaId, filtros],
    enabled: !!marcaId,
    queryFn: async () =>
      unwrap(
        await api.get<Envelope<ViraisPage>>(
          `${BASE}/virais?${viraisParams(marcaId as string, filtros)}`,
        ),
      ),
    placeholderData: (prev) => prev,
  });
  return {
    ...query,
    showSkeleton: !!marcaId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

/** One viral with transcript and badges (#8). */
export function useViralDetalhe(marcaId: string | null, viralId: string | null) {
  const query = useQuery({
    queryKey: [...BIB_KEY, "viral", marcaId, viralId],
    enabled: !!marcaId && !!viralId,
    queryFn: async () =>
      unwrap(
        await api.get<Envelope<ViralDetalheBiblioteca>>(
          `${BASE}/virais/${encodeURIComponent(viralId as string)}?marca_id=${encodeURIComponent(marcaId as string)}`,
        ),
      ),
    placeholderData: (prev) => prev,
  });
  return {
    ...query,
    showSkeleton: !!viralId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export interface PerfisParams {
  marcaId?: string | null;
  q?: string;
  limit?: number;
  offset?: number;
}

export const PERFIS_POR_PAGINA = 30;

export function perfisQuery(p: PerfisParams): string {
  const qs = new URLSearchParams();
  if (p.marcaId) qs.set("marca_id", p.marcaId);
  if (p.q?.trim()) qs.set("q", p.q.trim());
  qs.set("limit", String(p.limit ?? PERFIS_POR_PAGINA));
  qs.set("offset", String(p.offset ?? 0));
  return qs.toString();
}

/** Platform library profiles, paged (contract §4.2: `{items,total}`, ≤ 50 per page). */
export function usePerfisBiblioteca(params: PerfisParams = {}) {
  const query = useQuery({
    queryKey: [...BIB_KEY, "perfis", params.marcaId ?? null, params.q?.trim() ?? "", params.limit ?? PERFIS_POR_PAGINA, params.offset ?? 0],
    queryFn: async () =>
      unwrap(await api.get<Envelope<PerfisPage>>(`${BASE}/perfis?${perfisQuery(params)}`)),
    placeholderData: (prev) => prev,
    // No in-progress marker on a profile: it polls only while a sync hand-off is pending.
    ...jobPolling<PerfisPage>(() => false, PERFIS_POLL_MS),
  });
  return {
    ...query,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

/**
 * The profile list as a bare array (first 50 of the library) for the pickers/filters that only need to
 * choose one. Same cache entry shape as `usePerfisBiblioteca`; the page-level totals live there.
 */
export function usePerfisMonitorados(q = "") {
  const query = usePerfisBiblioteca({ q, limit: 50 });
  const data = useMemo(() => query.data?.items, [query.data]);
  return { ...query, data };
}

/** One library profile + its Estruturas count (contract §4.2 `GET /biblioteca/perfis/{id}`). */
export function usePerfilBiblioteca(id: string | null, marcaId?: string | null) {
  const query = useQuery({
    queryKey: [...BIB_KEY, "perfil", id, marcaId ?? null],
    enabled: !!id,
    queryFn: async () =>
      unwrap(
        await api.get<Envelope<PerfilBiblioteca>>(
          `${BASE}/perfis/${encodeURIComponent(id as string)}${marcaId ? `?marca_id=${encodeURIComponent(marcaId)}` : ""}`,
        ),
      ),
    ...jobPolling<PerfilBiblioteca>(() => false, PERFIS_POLL_MS),
  });
  return {
    ...query,
    showSkeleton: !!id && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export type VerificacaoPerfil = {
  status: "disponivel" | "ja_monitorado" | "na_minha_biblioteca" | "sem_conta_descoberta";
  perfil?: PerfilBiblioteca;
};

/** Live handle check (#10); the caller debounces and passes a normalized handle or "". */
export function useVerificarPerfil(handle: string, marcaId?: string | null) {
  return useQuery({
    queryKey: [...BIB_KEY, "verificar", handle, marcaId ?? null],
    enabled: handle.length > 0,
    queryFn: async () =>
      unwrap(
        await api.get<Envelope<VerificacaoPerfil>>(
          `${BASE}/perfis/verificar?handle=${encodeURIComponent(handle)}${marcaId ? `&marca_id=${encodeURIComponent(marcaId)}` : ""}`,
        ),
      ),
    placeholderData: (prev) => prev,
  });
}

export interface ContaDescoberta {
  id: string;
  nome: string;
  ig_username: string | null;
}

export function useContasDescoberta() {
  return useQuery({
    queryKey: [...BIB_KEY, "contas"],
    queryFn: async () =>
      unwrap(await api.get<Envelope<ContaDescoberta[]>>(`${BASE}/contas-descoberta`)),
  });
}

const PERFIS_KEY = [...BIB_KEY, "perfis"] as const;
const PERFIL_KEY = [...BIB_KEY, "perfil"] as const;
const REFS_KEY = [...BIB_KEY, "referencias"] as const;
const OPTOUTS_KEY = [...BIB_KEY, "optouts"] as const;

/** Patch a cached single-object entry (the profile detail); anything else passes through. */
const patchObjeto = <T extends { id: string }>(old: T | undefined, id: string, changes: Partial<T>) =>
  old && typeof old === "object" && !Array.isArray(old) && old.id === id ? { ...old, ...changes } : old;

/** `[...PERFIS_KEY, marcaId, q, limit, offset]`: no brand filter, no search, offset 0. */
const ehPrimeiraPaginaSemFiltro = (key: readonly unknown[]) => {
  const [marcaId, q, , offset] = key.slice(PERFIS_KEY.length);
  return marcaId == null && q === "" && offset === 0;
};

/** Add a library profile — a platform-admin write (contract §4.2; `marca_id` is ignored by the server). */
export function useSolicitarPerfil() {
  return useCacheWriteMutation<
    PerfilBiblioteca,
    { marca_id?: string; handle: string; conta_descoberta_id?: string; monitorar?: boolean }
  >({
    mutationFn: async ({ marca_id: _ignorado, ...corpo }) =>
      unwrap(await api.post<Envelope<PerfilBiblioteca>>(`${BASE}/perfis`, corpo)),
    // A brand-new profile heads the unfiltered first page; filtered/other pages converge on the settle.
    targets: [
      {
        queryKey: PERFIS_KEY,
        match: "prefix",
        predicate: ehPrimeiraPaginaSemFiltro,
        commit: (old: PerfisPage | undefined, saved) => pageOps.prependNewest(old, saved),
      },
    ],
    invalidate: [GERACAO_KEY],
  });
}

export const PERFIS_POLL_MS = 4000;

/** The profile's `ultima_sync_em` moved past what was cached at hand-off: the queued sync landed. */
const syncDoPerfilAterrissou = (id: string) => (data: unknown, before: unknown) => {
  const at = (l: unknown) => {
    const page = l as { items?: PerfilBiblioteca[] } | undefined;
    if (Array.isArray(page?.items)) return page.items.find((p) => p.id === id)?.ultima_sync_em;
    return (l as PerfilBiblioteca | undefined)?.id === id ? (l as PerfilBiblioteca).ultima_sync_em : undefined;
  };
  return at(data) !== at(before);
};

export function useSincronizarPerfil() {
  const qc = useQueryClient();
  return useMutation({ // noc-allow: invalidate-only — a sync trigger: the POST starts a background job and returns no row to commit
    mutationFn: async (id: string) =>
      api.post(`${BASE}/perfis/${encodeURIComponent(id)}/sincronizar`),
    onSuccess: (_r, id) => {
      // 202 + a queued job: follow the profile list AND the profile page until its sync lands (F87), then the rest.
      void handOffToPolling(qc, PERFIS_KEY, { until: syncDoPerfilAterrissou(id) });
      void handOffToPolling(qc, [...PERFIL_KEY, id], { until: syncDoPerfilAterrissou(id) });
      void qc.invalidateQueries({ queryKey: GERACAO_KEY });
    },
  });
}

export type AtualizarPerfilVars = {
  id: string;
  status?: "ativo" | "pausado";
  /** Library-only profiles (false) are imported without ingestion (contract §3.2). */
  monitorar?: boolean;
  /** Display-name override. */
  nome?: string;
};

export function useAtualizarPerfil() {
  return useCacheWriteMutation<PerfilBiblioteca, AtualizarPerfilVars>({
    mutationFn: async ({ id, ...corpo }) =>
      unwrap(await api.patch<Envelope<PerfilBiblioteca>>(`${BASE}/perfis/${encodeURIComponent(id)}`, corpo)),
    targets: (v) => {
      const { id, ...mudancas } = v;
      return [
        {
          queryKey: PERFIS_KEY,
          match: "prefix",
          optimistic: (old: PerfisPage | undefined) => pageOps.patch(old, id, mudancas),
          commit: (old: PerfisPage | undefined, saved) => pageOps.patch(old, id, saved),
        },
        {
          queryKey: PERFIL_KEY,
          match: "prefix",
          optimistic: (old: PerfilBiblioteca | undefined) => patchObjeto(old, id, mudancas),
          commit: (old: PerfilBiblioteca | undefined, saved) => patchObjeto(old, id, saved),
        },
      ];
    },
    invalidate: [GERACAO_KEY],
  });
}

export function useRemoverPerfil() {
  const qc = useQueryClient();
  return useCacheWriteMutation<unknown, { id: string; marca_id?: string | null; apagar_estruturas?: boolean }>({
    // Admin write (contract §4.2). Without `apagar_estruturas` the server answers 409 `perfil_com_estruturas`
    // (+ `estruturas_total`) when the profile still has Estruturas; the caller confirms and re-sends with it.
    mutationFn: async (v) =>
      api.delete(
        `${BASE}/perfis/${encodeURIComponent(v.id)}${v.apagar_estruturas ? "?apagar_estruturas=true" : ""}`,
      ),
    targets: (v) => [
      {
        queryKey: PERFIS_KEY,
        match: "prefix",
        optimistic: (old: PerfisPage | undefined) => pageOps.remove(old, v.id),
      },
    ],
    // The cascade removed the profile's Estruturas: every Estrutura list/detail is stale too.
    onSuccess: (_r, v) => {
      qc.removeQueries({ queryKey: [...PERFIL_KEY, v.id] });
      void qc.invalidateQueries({ queryKey: [...GERACAO_KEY, "estruturas"] });
    },
    invalidate: [GERACAO_KEY],
  });
}

/** The marca's allow-list (#16). */
export function useReferencias(marcaId: string | null, q = "") {
  const query = useQuery({
    queryKey: [...BIB_KEY, "referencias", marcaId, q],
    enabled: !!marcaId,
    queryFn: async () => {
      const p = new URLSearchParams({ marca_id: marcaId as string });
      if (q.trim()) p.set("q", q.trim());
      return unwrap(await api.get<Envelope<Referencia[]>>(`${BASE}/referencias?${p.toString()}`));
    },
    placeholderData: (prev) => prev,
  });
  return {
    ...query,
    showSkeleton: !!marcaId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export type NovaReferencia =
  | { marca_id: string; modo: "perfil"; perfil_ids: string[]; auto_atualizar: boolean }
  | { marca_id: string; modo: "video"; viral_ids: string[] };

export function useCriarReferencias() {
  const qc = useQueryClient();
  return useMutation({ // noc-allow: invalidate-only — the answer is {criadas, ja_existentes} counts, not the Referencia rows (the server expands perfil → videos)
    mutationFn: async (v: NovaReferencia) =>
      unwrap(
        await api.post<Envelope<{ criadas: number; ja_existentes: number }>>(
          `${BASE}/referencias`,
          v,
        ),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: GERACAO_KEY }),
  });
}

export function useRemoverReferencia() {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: async (id) => api.delete(`${BASE}/referencias/${encodeURIComponent(id)}`),
    targets: (id) => [
      {
        queryKey: REFS_KEY,
        match: "prefix",
        optimistic: (old: Referencia[] | undefined) => listOps.remove(old as (Referencia & { id: string })[] | undefined, id),
      },
    ],
    invalidate: [GERACAO_KEY],
  });
}

/** "Gerar headline" from a viral (#20, origem 'biblioteca'). */
export function useGerarHeadlineViral() {
  return useCacheWriteMutation<
    HeadlineLote,
    // Exactly one of `viral_id` | `estrutura_id` (contract §6.6 `LoteBiblioteca`).
    { marca_id: string; viral_id?: string; estrutura_id?: string; assunto_ids?: string[]; assunto_livre?: string }
  >({
    mutationFn: async (v) =>
      unwrap(
        await api.post<Envelope<HeadlineLote>>("/api/media-creation/headlines/lotes", {
          ...v,
          origem: "biblioteca",
        }),
      ),
    // The new batch heads the marca's default lotes list (server sorts newest first).
    targets: (v) => [
      {
        queryKey: [...GERACAO_KEY, "headlines", v.marca_id, "lotes", "", 0],
        commit: (old: unknown, saved) => pageOps.prependNewest(old, saved),
      },
    ],
    invalidate: [GERACAO_KEY],
  });
}

export type { ViralCard };

/* ---- Opt-out registry (platform admin; spec biblioteca-lia §5) ---- */

export type OptoutOrigem = "email" | "dpo" | "admin";

export interface PerfilOptout {
  id: string;
  handle: string;
  motivo: string | null;
  origem: OptoutOrigem;
  solicitado_em: string | null;
  registrado_por: string | null;
  created_at: string;
}

export interface RegistrarOptoutResultado {
  optout: PerfilOptout;
  criado: boolean;
  purgados: { perfis: number; virais: number; blobs_falhos: number };
}

/** Opt-out list (admin-only; the caller gates with `useTreinamentosAdmin`). */
export function useOptoutsAdmin(enabled = true) {
  const query = useQuery({
    queryKey: [...BIB_KEY, "optouts"],
    enabled,
    queryFn: async () => unwrap(await api.get<Envelope<PerfilOptout[]>>(`${BASE}/admin/optouts`)),
    placeholderData: (prev) => prev,
  });
  return {
    ...query,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

/** Register an opt-out: purges the handle's data in every org NOW. */
export function useRegistrarOptout() {
  return useCacheWriteMutation<RegistrarOptoutResultado, { handle: string; motivo?: string; origem: OptoutOrigem }>({
    mutationFn: async (v) =>
      unwrap(await api.post<Envelope<RegistrarOptoutResultado>>(`${BASE}/admin/optouts`, v)),
    targets: [
      {
        queryKey: OPTOUTS_KEY,
        commit: (old: PerfilOptout[] | undefined, res) => listOps.replace(old, res.optout.id, res.optout, "prepend"),
      },
    ],
    // The purge removes profiles/virais across the whole family.
    invalidate: [GERACAO_KEY],
  });
}

export function useRemoverOptout() {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: async (id) => api.delete(`${BASE}/admin/optouts/${encodeURIComponent(id)}`),
    targets: (id) => [
      {
        queryKey: OPTOUTS_KEY,
        optimistic: (old: PerfilOptout[] | undefined) => listOps.remove(old, id),
      },
    ],
  });
}
