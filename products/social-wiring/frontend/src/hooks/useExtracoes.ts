/**
 * Minhas extrações — TanStack Query hooks over `/api/media-creation/cerebro/extracoes`
 * (contract cerebro-contract.md §4 endpoints 19-24). v1 is pasted-text only (§10).
 *
 * Loading rule (lying-loading-state.md): `showSkeleton = isPending && !data`,
 * `isRefreshing = isFetching && !!data`, never `isLoading`. "Carregar mais" grows
 * `limit` (server page size 1-100) and keeps the previous page on screen via
 * `placeholderData`. Mutations invalidate the whole `["sw","cerebro"]` family
 * (an apply changes brain content/size too).
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import { CEREBRO_KEY, POLL_MS } from "@/hooks/useCerebro";
import type { ExtractionDetail, ExtractionSummary } from "@/types/cerebro";

const BASE = "/api/media-creation/cerebro/extracoes";
export const PAGE_SIZE = 20;

interface Envelope<T> {
  success?: boolean;
  data: T;
}
const unwrap = <T>(res: Envelope<T>): T => res.data;

export interface ExtracoesPage {
  items: ExtractionSummary[];
  total: number;
}

const listKey = (marcaId: string | null, q: string, limit: number) =>
  [...CEREBRO_KEY, marcaId, "extracoes", { q, limit }] as const;
const detailKey = (id: string | null) => [...CEREBRO_KEY, "extracao", id] as const;

export const extracaoEmAndamento = (e: { status: string } | undefined | null) => e?.status === "transcribing";

export function useExtracoes(marcaId: string | null, q: string, limit: number = PAGE_SIZE) {
  const query = useQuery({
    queryKey: listKey(marcaId, q, limit),
    enabled: !!marcaId,
    queryFn: async () => {
      const p = new URLSearchParams({ marca_id: marcaId as string, limit: String(limit), offset: "0" });
      if (q.trim()) p.set("q", q.trim());
      return unwrap(await api.get<Envelope<ExtracoesPage>>(`${BASE}?${p.toString()}`));
    },
    refetchInterval: (s) => (s.state.data?.items.some(extracaoEmAndamento) ? POLL_MS : false),
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    showSkeleton: !!marcaId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export function useExtracao(id: string | null) {
  const query = useQuery({
    queryKey: detailKey(id),
    enabled: !!id,
    queryFn: async () =>
      unwrap(await api.get<Envelope<ExtractionDetail>>(`${BASE}/${encodeURIComponent(id as string)}`)),
    refetchInterval: (s) => (extracaoEmAndamento(s.state.data) ? POLL_MS : false),
    placeholderData: (prev) => (prev && prev.id === id ? prev : undefined),
  });
  return {
    ...query,
    showSkeleton: !!id && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

function useInvalidateCerebro() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: CEREBRO_KEY });
}

export function useCriarExtracao() {
  const invalidate = useInvalidateCerebro();
  return useMutation({
    mutationFn: async (v: { marca_id: string; name: string; brain_ids: string[]; text: string }) =>
      unwrap(await api.post<Envelope<ExtractionDetail>>(BASE, v)),
    onSuccess: invalidate,
  });
}

export function useAtualizarExtracao() {
  const invalidate = useInvalidateCerebro();
  return useMutation({
    mutationFn: async (v: { id: string; name?: string; transcript?: string; brain_ids?: string[] }) => {
      const { id, ...body } = v;
      return unwrap(await api.patch<Envelope<ExtractionDetail>>(`${BASE}/${encodeURIComponent(id)}`, body));
    },
    onSuccess: invalidate,
  });
}

export function useAplicarExtracao() {
  const invalidate = useInvalidateCerebro();
  return useMutation({
    mutationFn: async (v: { id: string; brain_ids?: string[] }) =>
      unwrap(
        await api.post<Envelope<{ applied: string[]; skipped: string[] }>>(
          `${BASE}/${encodeURIComponent(v.id)}/apply`,
          v.brain_ids ? { brain_ids: v.brain_ids } : {},
        ),
      ),
    onSuccess: invalidate,
  });
}

export function useExcluirExtracao() {
  const invalidate = useInvalidateCerebro();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`${BASE}/${encodeURIComponent(id)}`);
    },
    onSuccess: invalidate,
  });
}
