/**
 * Headlines (P7 Gerar/histórico, P8 Favoritas, P9 Sugeridas) over
 * `/api/media-creation/headlines` (contract §4.4 #20–#31). Edit / favoritar /
 * excluir live in `useHeadlineMutations` (FE-0).
 *
 * Loading rule (lying-loading-state.md): `showSkeleton = isPending && !data`,
 * `isRefreshing = isFetching && !!data`, `placeholderData` on key changes —
 * never `isLoading`. The batch status is REAL: lists and the detail poll every
 * 3 s only while a visible batch is `criando`/`processando` (contract §3.2).
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import { emAndamento } from "@/components/geracao/labels";
import type { Criatividade, Headline, HeadlineLote, HeadlineLoteDetalhe } from "@/types/geracao";
import { GERACAO_KEY } from "./useHeadlineMutations";

interface Envelope<T> {
  success?: boolean;
  data: T;
}
const unwrap = <T>(res: Envelope<T>): T => res.data;

const BASE = "/api/media-creation/headlines";
export const HEADLINES_POLL_MS = 3000;
export const HEADLINES_PAGE_SIZE = 20;
const HEAD_KEY = [...GERACAO_KEY, "headlines"] as const;

function useInvalidateGeracao() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: GERACAO_KEY });
}

/** True while any visible batch is still being produced (drives the poll). */
export function algumLoteEmAndamento(items: Pick<HeadlineLote, "status">[] | undefined): boolean {
  return !!items?.some((l) => emAndamento(l.status));
}

// ─── Lotes ──────────────────────────────────────────────────────────────────

export function useLotes(marcaId: string | null, q = "", offset = 0) {
  const query = useQuery({
    queryKey: [...HEAD_KEY, marcaId, "lotes", q, offset],
    enabled: !!marcaId,
    queryFn: async () => {
      const p = new URLSearchParams({
        marca_id: marcaId as string,
        limit: String(HEADLINES_PAGE_SIZE),
        offset: String(offset),
      });
      if (q.trim()) p.set("q", q.trim());
      return unwrap(await api.get<Envelope<{ items: HeadlineLote[]; total: number }>>(`${BASE}/lotes?${p}`));
    },
    refetchInterval: (s) => (algumLoteEmAndamento(s.state.data?.items) ? HEADLINES_POLL_MS : false),
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    showSkeleton: !!marcaId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

/** Batches generated from one Esteira post (`GET /lotes?post_id=`, contract §5.3). Polls while one runs. */
export function useLotesDoPost(marcaId: string | null, postId: string | null) {
  const query = useQuery({
    queryKey: [...HEAD_KEY, marcaId, "lotes", "post", postId],
    enabled: !!marcaId && !!postId,
    queryFn: async () => {
      const p = new URLSearchParams({
        marca_id: marcaId as string,
        post_id: postId as string,
        limit: String(HEADLINES_PAGE_SIZE),
      });
      return unwrap(await api.get<Envelope<{ items: HeadlineLote[]; total: number }>>(`${BASE}/lotes?${p}`));
    },
    refetchInterval: (s) => (algumLoteEmAndamento(s.state.data?.items) ? HEADLINES_POLL_MS : false),
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    showSkeleton: !!marcaId && !!postId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export function useLote(id: string | null) {
  const query = useQuery({
    queryKey: [...HEAD_KEY, "lote", id],
    enabled: !!id,
    queryFn: async () =>
      unwrap(await api.get<Envelope<HeadlineLoteDetalhe>>(`${BASE}/lotes/${encodeURIComponent(id as string)}`)),
    refetchInterval: (s) => (s.state.data && emAndamento(s.state.data.status) ? HEADLINES_POLL_MS : false),
    placeholderData: (prev) => (prev && prev.id === id ? prev : undefined),
  });
  return {
    ...query,
    showSkeleton: !!id && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export type ReferenciaLote =
  | { tipo: "perfil"; perfil_ids: string[] }
  | { tipo: "formato"; formato_ids: number[] }
  | { tipo: "gatilho"; gatilhos: string[] };

export type LoteCreate =
  | {
      marca_id: string;
      origem: "form_me" | "form_public";
      variaveis: string[];
      valores?: Record<string, string[]>;
      assunto?: string;
      referencia?: ReferenciaLote;
      somente_pesquisa: boolean;
      criatividade: Criatividade;
      /** Batch generated from inside an Esteira post (contract §5.3 `LoteParams.post_id`). */
      post_id?: string;
    }
  | {
      marca_id: string;
      origem: "form_viral";
      assunto_ids?: string[];
      assunto_livre?: string;
      tom?: number;
      referencia?: Exclude<ReferenciaLote, { tipo: "gatilho" }>;
      criatividade: Criatividade;
      post_id?: string;
    };

export function useCriarLote() {
  const invalidate = useInvalidateGeracao();
  return useMutation({
    mutationFn: async (body: LoteCreate) => unwrap(await api.post<Envelope<HeadlineLote>>(`${BASE}/lotes`, body)),
    onSuccess: invalidate,
  });
}

export function useReprocessarLote() {
  const invalidate = useInvalidateGeracao();
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(await api.post<Envelope<HeadlineLote>>(`${BASE}/lotes/${encodeURIComponent(id)}/reprocessar`)),
    onSuccess: invalidate,
  });
}

export function useExcluirLotes() {
  const invalidate = useInvalidateGeracao();
  return useMutation({
    mutationFn: async (ids: string[]) =>
      unwrap(await api.post<Envelope<{ excluidos: number }>>(`${BASE}/lotes/excluir`, { ids })),
    onSuccess: invalidate,
  });
}

// ─── Form helpers ───────────────────────────────────────────────────────────

export interface Contagem {
  compativeis: number;
  por_perfil: { perfil_id: string; n: number }[];
}

/** Compatible structures for the selected variables (`estruturas/contagem`). */
export function useContagemEstruturas(marcaId: string | null, variaveis: string[]) {
  const query = useQuery({
    queryKey: [...HEAD_KEY, marcaId, "contagem", variaveis],
    enabled: !!marcaId && variaveis.length > 0,
    queryFn: async () => {
      const p = new URLSearchParams({ marca_id: marcaId as string });
      variaveis.forEach((v) => p.append("variaveis[]", v));
      return unwrap(await api.get<Envelope<Contagem>>(`${BASE}/estruturas/contagem?${p}`));
    },
    placeholderData: keepPreviousData,
  });
  return { ...query, isRefreshing: query.isFetching && !!query.data };
}

export interface ItemAprovado {
  id: string;
  content: string;
}

/** Approved research items of one variable (`GET /pesquisa/items?status=approved`). */
export function useItensAprovados(marcaId: string | null, slug: string | null) {
  const query = useQuery({
    queryKey: [...GERACAO_KEY, "pesquisa-aprovados", marcaId, slug],
    enabled: !!marcaId && !!slug,
    queryFn: async () => {
      const p = new URLSearchParams({
        marca_id: marcaId as string,
        status: "approved",
        variable_slug: slug as string,
        limit: "100",
        offset: "0",
      });
      const d = unwrap(
        await api.get<Envelope<{ items: ItemAprovado[]; total: number }>>(`/api/media-creation/pesquisa/items?${p}`),
      );
      return d.items;
    },
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    showSkeleton: !!marcaId && !!slug && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

// ─── Favoritas / Sugeridas ──────────────────────────────────────────────────

export type ListaHeadlines = "favoritas" | "sugeridas";

export function useHeadlinesLista(
  marcaId: string | null,
  lista: ListaHeadlines,
  opts: { q?: string; modo?: "manual" | "automatico" | ""; offset?: number } = {},
) {
  const { q = "", modo = "", offset = 0 } = opts;
  const query = useQuery({
    queryKey: [...HEAD_KEY, marcaId, "lista", lista, modo, q, offset],
    enabled: !!marcaId,
    queryFn: async () => {
      const p = new URLSearchParams({
        marca_id: marcaId as string,
        lista,
        limit: String(HEADLINES_PAGE_SIZE),
        offset: String(offset),
      });
      if (q.trim()) p.set("q", q.trim());
      if (modo && lista === "sugeridas") p.set("modo", modo);
      return unwrap(await api.get<Envelope<{ items: Headline[]; total: number }>>(`${BASE}?${p}`));
    },
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    showSkeleton: !!marcaId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

/** One headline by id — backs the `?hid=` deep link when it is not on the current page. */
export function useHeadline(id: string | null) {
  const query = useQuery({
    queryKey: [...HEAD_KEY, "um", id],
    enabled: !!id,
    queryFn: async () => unwrap(await api.get<Envelope<Headline>>(`${BASE}/${encodeURIComponent(id as string)}`)),
    retry: false,
  });
  return { ...query, showSkeleton: !!id && query.isPending && !query.data };
}

export function useGerarSugestoesAgora() {
  const invalidate = useInvalidateGeracao();
  return useMutation({
    mutationFn: async (marcaId: string) =>
      unwrap(await api.post<Envelope<HeadlineLote>>(`${BASE}/sugestoes/gerar-agora`, { marca_id: marcaId })),
    onSuccess: invalidate,
  });
}
