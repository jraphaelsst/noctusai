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

import type { FiltrosViral } from "@/components/geracao/biblioteca/filtros";
import type {
  HeadlineLote,
  PerfilMonitorado,
  Referencia,
  Taxonomias,
  ViralCard,
  ViralDetalhe,
} from "@/types/geracao";
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
        await api.get<Envelope<ViralDetalhe>>(
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

/** Org-wide monitored profiles (#9). */
export function usePerfisMonitorados(q = "") {
  const query = useQuery({
    queryKey: [...BIB_KEY, "perfis", q],
    queryFn: async () =>
      unwrap(
        await api.get<Envelope<PerfilMonitorado[]>>(
          `${BASE}/perfis${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ""}`,
        ),
      ),
    placeholderData: (prev) => prev,
    // No in-progress marker on a profile: it polls only while a sync hand-off is pending.
    ...jobPolling<PerfilMonitorado[]>(() => false, PERFIS_POLL_MS),
  });
  return {
    ...query,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export type VerificacaoPerfil = {
  status: "disponivel" | "ja_monitorado" | "na_minha_biblioteca" | "sem_conta_descoberta";
  perfil?: PerfilMonitorado;
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
const REFS_KEY = [...BIB_KEY, "referencias"] as const;
const OPTOUTS_KEY = [...BIB_KEY, "optouts"] as const;

export function useSolicitarPerfil() {
  return useCacheWriteMutation<PerfilMonitorado, { marca_id: string; handle: string; conta_descoberta_id?: string }>({
    mutationFn: async (v) => unwrap(await api.post<Envelope<PerfilMonitorado>>(`${BASE}/perfis`, v)),
    // The unfiltered profile list gets the new profile at once; filtered ones converge on the settle.
    targets: [
      {
        queryKey: [...PERFIS_KEY, ""],
        commit: (old: PerfilMonitorado[] | undefined, saved) => listOps.replace(old, saved.id, saved),
      },
    ],
    invalidate: [GERACAO_KEY],
  });
}

export const PERFIS_POLL_MS = 4000;

/** The profile's `ultima_sync_em` moved past what was cached at hand-off: the queued sync landed. */
const syncDoPerfilAterrissou = (id: string) => (data: unknown, before: unknown) => {
  const at = (l: unknown) => (Array.isArray(l) ? (l as PerfilMonitorado[]).find((p) => p.id === id)?.ultima_sync_em : undefined);
  return at(data) !== at(before);
};

export function useSincronizarPerfil() {
  const qc = useQueryClient();
  return useMutation({ // noc-allow: invalidate-only — a sync trigger: the POST starts a background job and returns no row to commit
    mutationFn: async (id: string) =>
      api.post(`${BASE}/perfis/${encodeURIComponent(id)}/sincronizar`),
    onSuccess: (_r, id) => {
      // 202 + a queued job: follow the profile list until its sync lands (F87), then the rest.
      void handOffToPolling(qc, [...BIB_KEY, "perfis"], { until: syncDoPerfilAterrissou(id) });
      void qc.invalidateQueries({ queryKey: GERACAO_KEY });
    },
  });
}

export function useAtualizarPerfil() {
  return useCacheWriteMutation<PerfilMonitorado, { id: string; status: "ativo" | "pausado" }>({
    mutationFn: async (v) =>
      unwrap(
        await api.patch<Envelope<PerfilMonitorado>>(
          `${BASE}/perfis/${encodeURIComponent(v.id)}`,
          { status: v.status },
        ),
      ),
    targets: (v) => [
      {
        queryKey: PERFIS_KEY,
        match: "prefix",
        optimistic: (old: PerfilMonitorado[] | undefined, vars) => listOps.patch(old, vars.id, { status: vars.status }),
        commit: (old: PerfilMonitorado[] | undefined, saved) => listOps.patch(old, v.id, saved),
      },
    ],
    invalidate: [GERACAO_KEY],
  });
}

export function useRemoverPerfil() {
  return useCacheWriteMutation<unknown, { id: string; marca_id: string | null }>({
    // marca_id resolves the 409 "used by another marca" (BE: delete_perfil).
    mutationFn: async (v) =>
      api.delete(
        `${BASE}/perfis/${encodeURIComponent(v.id)}${v.marca_id ? `?marca_id=${encodeURIComponent(v.marca_id)}` : ""}`,
      ),
    targets: [
      {
        queryKey: PERFIS_KEY,
        match: "prefix",
        optimistic: (old: PerfilMonitorado[] | undefined, vars) => listOps.remove(old, vars.id),
      },
    ],
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
    { marca_id: string; viral_id: string; assunto_ids?: string[]; assunto_livre?: string }
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
