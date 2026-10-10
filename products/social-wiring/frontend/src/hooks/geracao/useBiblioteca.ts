/**
 * Biblioteca (virais) + Minha Biblioteca hooks over
 * `/api/media-creation/biblioteca/*` (contract §4.3 #7–19) and the
 * `origem:'biblioteca'` headline batch (§4.4 #20).
 *
 * Loading rule (lying-loading-state.md): every query hook returns
 * `showSkeleton = isPending && !data` and `isRefreshing = isFetching && !!data`,
 * with `placeholderData` on key changes — never `isLoading`. Mutations
 * invalidate the whole `["sw","geracao"]` family.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import type { FiltrosViral } from "@/components/geracao/biblioteca/filtros";
import type {
  HeadlineLote,
  PerfilMonitorado,
  Referencia,
  Taxonomias,
  ViralCard,
  ViralDetalhe,
} from "@/types/geracao";
import { GERACAO_KEY } from "./useHeadlineMutations";

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
}

function viraisParams(marcaId: string, f: FiltrosViral): string {
  const p = new URLSearchParams({ marca_id: marcaId, ordem: f.ordem, page: String(f.page) });
  f.nichos.forEach((n) => p.append("nichos", String(n)));
  f.profissoes.forEach((n) => p.append("profissoes", String(n)));
  // A profile view never auto-filters (page-map-v2 §10.4).
  if (f.verTodos || f.perfilId) p.set("ver_todos", "true");
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

/**
 * Static taxonomies (#1). Same query key as FE-1's `useTaxonomias`, so both
 * share one cache entry; kept local because FE-1 owns that file.
 */
export function useTaxonomiasBiblioteca() {
  return useQuery({
    queryKey: [...GERACAO_KEY, "taxonomias"],
    staleTime: 60 * 60 * 1000,
    queryFn: async () =>
      unwrap(await api.get<Envelope<Taxonomias>>("/api/media-creation/taxonomias")),
  });
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
export function useVerificarPerfil(handle: string) {
  return useQuery({
    queryKey: [...BIB_KEY, "verificar", handle],
    enabled: handle.length > 0,
    queryFn: async () =>
      unwrap(
        await api.get<Envelope<VerificacaoPerfil>>(
          `${BASE}/perfis/verificar?handle=${encodeURIComponent(handle)}`,
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

function useInvalidar() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: GERACAO_KEY });
}

export function useSolicitarPerfil() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: async (v: { marca_id: string; handle: string; conta_descoberta_id?: string }) =>
      unwrap(await api.post<Envelope<PerfilMonitorado>>(`${BASE}/perfis`, v)),
    onSuccess: invalidar,
  });
}

export function useSincronizarPerfil() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: async (id: string) =>
      api.post(`${BASE}/perfis/${encodeURIComponent(id)}/sincronizar`),
    onSuccess: invalidar,
  });
}

export function useAtualizarPerfil() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: async (v: { id: string; status: "ativo" | "pausado" }) =>
      unwrap(
        await api.patch<Envelope<PerfilMonitorado>>(
          `${BASE}/perfis/${encodeURIComponent(v.id)}`,
          { status: v.status },
        ),
      ),
    onSuccess: invalidar,
  });
}

export function useRemoverPerfil() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: async (id: string) => api.delete(`${BASE}/perfis/${encodeURIComponent(id)}`),
    onSuccess: invalidar,
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
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: async (v: NovaReferencia) =>
      unwrap(
        await api.post<Envelope<{ criadas: number; ja_existentes: number }>>(
          `${BASE}/referencias`,
          v,
        ),
      ),
    onSuccess: invalidar,
  });
}

export function useRemoverReferencia() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: async (id: string) =>
      api.delete(`${BASE}/referencias/${encodeURIComponent(id)}`),
    onSuccess: invalidar,
  });
}

/** "Gerar headline" from a viral (#20, origem 'biblioteca'). */
export function useGerarHeadlineViral() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: async (v: {
      marca_id: string;
      viral_id: string;
      assunto_ids?: string[];
      assunto_livre?: string;
    }) =>
      unwrap(
        await api.post<Envelope<HeadlineLote>>("/api/media-creation/headlines/lotes", {
          ...v,
          origem: "biblioteca",
        }),
      ),
    onSuccess: invalidar,
  });
}

export type { ViralCard };
