/**
 * Extrair Pesquisa — TanStack Query hooks over `/api/media-creation/pesquisa`
 * (build contract: projects/core-studio/specs/pesquisa-wave2-contract.md §3
 * endpoints 11–17, §3.1 types).
 *
 * Loading rule (lying-loading-state.md): query hooks return
 * `showSkeleton = isPending && !data` and `isRefreshing = isFetching && !!data`,
 * with `placeholderData` on key changes — never `isLoading`.
 * Polling: `refetchInterval` is 2 s while the job is queued/running and `false`
 * on any terminal status.
 */
import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import { PESQUISA_KEY } from "@/hooks/usePesquisa";

// ─── Types (contract §3.1) ──────────────────────────────────────────────────

export type FonteKind = "instagram_media" | "youtube_video" | "mc_post";
export type ExtracaoTipo = "pesquisa" | "assuntos_virais";
export type ExtractionStatus =
  | "queued"
  | "running"
  | "completed"
  | "completed_with_errors"
  | "failed"
  | "cancelled";

export interface Fonte {
  kind: FonteKind;
  account_id: string | null;
  label: string;
  total_posts: number;
  last_synced_at: string | null;
}

export interface PostFonte {
  kind: FonteKind;
  account_id: string | null;
  id: string;
  url: string | null;
  thumbnail_url: string | null;
  published_at: string | null;
  texto: string;
  analisavel: boolean;
  plays: number | null;
  likes: number | null;
  comments: number | null;
  extra: Record<string, unknown>;
  extraido: { pesquisa: string | null; assuntos_virais: string | null };
}

export interface PostFontePage {
  posts: PostFonte[];
  next_cursor: string | null;
}

export interface ExtractionJob {
  id: string;
  marca_id: string;
  tipos: ExtracaoTipo[];
  status: ExtractionStatus;
  step: string | null;
  progress: number;
  total_tarefas: number;
  tarefas_processadas: number;
  tarefas_com_erro: number;
  itens_salvos: number;
  itens_ignorados: number;
  itens_descartados: number;
  assuntos_salvos: number;
  assuntos_ignorados: number;
  ja_extraidos_pulados: number;
  erro: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface ExtractionLimits {
  worker_ativo: boolean;
  max_posts_por_job: number;
  extracoes_restantes_hoje: number;
  tarefas_restantes_hoje_org: number;
  extracao_ativa_id: string | null;
}

export interface PostRef {
  kind: FonteKind;
  account_id: string | null;
  id: string;
}

export interface SubmitExtracao {
  marca_id: string;
  tipos: ExtracaoTipo[];
  posts: PostRef[];
  reextrair?: boolean;
}

export const POSTS_PAGE_SIZE = 24;
export const POLL_INTERVAL_MS = 2000;

export const isJobActive = (s: ExtractionStatus | undefined) => s === "queued" || s === "running";

// ─── Keys ───────────────────────────────────────────────────────────────────

const BASE = "/api/media-creation/pesquisa";
export const EXTRACAO_KEY = [...PESQUISA_KEY, "extracao"] as const;
const fontesKey = (marcaId: string | null) => [...EXTRACAO_KEY, "fontes", marcaId] as const;
const postsKey = (marcaId: string | null, f: Fonte | null, busca: string) =>
  [...EXTRACAO_KEY, "posts", marcaId, f?.kind ?? null, f?.account_id ?? null, busca] as const;
const limitesKey = (marcaId: string | null) => [...EXTRACAO_KEY, "limites", marcaId] as const;
const listaKey = (marcaId: string | null) => [...EXTRACAO_KEY, "lista", marcaId] as const;
const jobKey = (id: string | null) => [...EXTRACAO_KEY, "job", id] as const;

interface Envelope<T> {
  success?: boolean;
  ok?: boolean;
  data: T;
}
const unwrap = <T>(res: Envelope<T>): T => res.data;
const enc = encodeURIComponent;

// ─── Queries ────────────────────────────────────────────────────────────────

export function useFontes(marcaId: string | null) {
  const query = useQuery({
    queryKey: fontesKey(marcaId),
    enabled: !!marcaId,
    queryFn: async () =>
      unwrap(await api.get<Envelope<Fonte[]>>(`${BASE}/fontes?marca_id=${enc(marcaId as string)}`)) ?? [],
    placeholderData: (prev) => prev,
  });
  return {
    ...query,
    showSkeleton: !!marcaId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export function usePostsFonte(marcaId: string | null, fonte: Fonte | null, busca: string) {
  const query = useInfiniteQuery({
    queryKey: postsKey(marcaId, fonte, busca),
    enabled: !!marcaId && !!fonte,
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) => {
      const params = new URLSearchParams({
        marca_id: marcaId as string,
        kind: (fonte as Fonte).kind,
        limit: String(POSTS_PAGE_SIZE),
      });
      if (fonte?.account_id) params.set("account_id", fonte.account_id);
      if (pageParam) params.set("cursor", pageParam);
      if (busca.trim()) params.set("busca", busca.trim());
      return unwrap(await api.get<Envelope<PostFontePage>>(`${BASE}/fontes/posts?${params.toString()}`));
    },
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    placeholderData: keepPreviousData,
  });
  const posts = query.data?.pages.flatMap((p) => p.posts) ?? [];
  return {
    ...query,
    posts,
    showSkeleton: !!marcaId && !!fonte && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data && !query.isFetchingNextPage,
  };
}

export function useExtracaoLimites(marcaId: string | null) {
  const query = useQuery({
    queryKey: limitesKey(marcaId),
    enabled: !!marcaId,
    queryFn: async () =>
      unwrap(await api.get<Envelope<ExtractionLimits>>(`${BASE}/extracoes/limites?marca_id=${enc(marcaId as string)}`)),
    placeholderData: (prev) => prev,
  });
  return {
    ...query,
    showSkeleton: !!marcaId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export function useExtracoesRecentes(marcaId: string | null) {
  const query = useQuery({
    queryKey: listaKey(marcaId),
    enabled: !!marcaId,
    queryFn: async () =>
      unwrap(
        await api.get<Envelope<ExtractionJob[]>>(`${BASE}/extracoes?marca_id=${enc(marcaId as string)}&limit=10`),
      ) ?? [],
    placeholderData: (prev) => prev,
  });
  return {
    ...query,
    showSkeleton: !!marcaId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

/** Polls one job every 2 s while queued/running; stops (`false`) on terminal. */
export function useExtracaoJob(id: string | null) {
  const query = useQuery({
    queryKey: jobKey(id),
    enabled: !!id,
    queryFn: async () => unwrap(await api.get<Envelope<ExtractionJob>>(`${BASE}/extracoes/${enc(id as string)}`)),
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      return status && !isJobActive(status) ? false : POLL_INTERVAL_MS;
    },
  });
  return {
    ...query,
    showSkeleton: !!id && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

// ─── Mutations ──────────────────────────────────────────────────────────────

/** Terminal job: refresh lists, counts (whole pesquisa family) and limits. */
export function useInvalidarExtracao() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: PESQUISA_KEY });
}

export function useSubmeterExtracao() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: SubmitExtracao) =>
      unwrap(await api.post<Envelope<ExtractionJob>>(`${BASE}/extracoes`, v)),
    onSuccess: (job) => {
      qc.setQueryData(jobKey(job.id), job);
      qc.invalidateQueries({ queryKey: [...EXTRACAO_KEY, "limites"] });
      qc.invalidateQueries({ queryKey: [...EXTRACAO_KEY, "lista"] });
    },
    // 409/429/503 → the page toasts `detail` and refetches limits.
    onError: () => qc.invalidateQueries({ queryKey: [...EXTRACAO_KEY, "limites"] }),
  });
}

export function useCancelarExtracao() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(await api.post<Envelope<ExtractionJob>>(`${BASE}/extracoes/${enc(id)}/cancel`)),
    onSuccess: (job) => {
      qc.setQueryData(jobKey(job.id), job);
      qc.invalidateQueries({ queryKey: [...EXTRACAO_KEY, "limites"] });
    },
  });
}
