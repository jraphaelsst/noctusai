/**
 * AI-generated first draft (S3a CONTRACT §2) — the same routes the content-token chat drives:
 *   POST /agents/{key}/geracoes                          -> 202 GeracaoOut
 *   GET  /agents/{key}/geracoes                          -> {items} newest first
 *   GET  /agents/{key}/geracoes/{id}                     -> GeracaoOut (polled while pendente|executando)
 *   POST /agents/{key}/geracoes/{id}/areas/{area}/repetir -> 202 GeracaoOut
 *   POST /agents/{key}/geracoes/{id}/cancelar            -> 200 GeracaoOut
 *
 * Every mutation writes the server's GeracaoOut into both the run's own entry and the list (never
 * invalidate-only); the draft editors are refreshed in the background because a run writes the draft.
 */
import { useEffect, useMemo, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";
import {
  isGeracaoAtiva,
  type GeracaoArea,
  type GeracaoCreateInput,
  type GeracaoOut,
  type GeracoesList,
  type ItemGerado,
} from "@/api/studio/types-geracao";
import { seg, studioKeys, toView } from "./keys";

export const GERACAO_POLL_MS = 2000;

const base = (key: string) => `/api/studio/agents/${seg(key)}/geracoes`;

function upsertInList(old: GeracoesList | undefined, g: GeracaoOut): GeracoesList | undefined {
  if (!old) return { items: [g] };
  const rest = old.items.filter((i) => i.id !== g.id);
  const idx = old.items.findIndex((i) => i.id === g.id);
  if (idx >= 0) return { ...old, items: old.items.map((i) => (i.id === g.id ? g : i)) };
  return { ...old, items: [g, ...rest].slice(0, 20) };
}

/** Run list, newest first. Polls while the newest run is still active (a run may start from chat). */
export function useGeracoes(key: string) {
  const q = useQuery<GeracoesList>({
    queryKey: studioKeys.geracoes(key),
    queryFn: () => api.get<GeracoesList>(base(key)),
    enabled: !!key,
    retry: false,
    placeholderData: (prev) => prev,
    // The list only needs polling to DISCOVER a run; the active run itself is polled by `useGeracao`.
    refetchInterval: false,
  });
  return toView(q);
}

/** One run; polls every 2 s while pendente|executando and STOPS the moment it is terminal. */
export function useGeracao(key: string, id: string | undefined) {
  const q = useQuery<GeracaoOut>({
    queryKey: studioKeys.geracao(key, id ?? ""),
    queryFn: () => api.get<GeracaoOut>(`${base(key)}/${seg(id ?? "")}`),
    enabled: !!key && !!id,
    retry: false,
    placeholderData: (prev) => prev,
    refetchInterval: (query) => (isGeracaoAtiva(query.state.data?.status) ? GERACAO_POLL_MS : false),
  });
  return toView(q);
}

/**
 * The latest run of an agent (the list's head) with its live detail. `geracao` is the polled detail once
 * loaded, else the list's copy. `showSkeleton` = nothing to render yet.
 */
export function useUltimaGeracao(key: string) {
  const lista = useGeracoes(key);
  const head = lista.data?.items[0];
  const detalhe = useGeracao(key, head?.id);
  const geracao = detalhe.data ?? head;
  const qc = useQueryClient();
  const ativaAgora = isGeracaoAtiva(geracao?.status);
  const eraAtiva = useRef(false);
  useEffect(() => {
    // A run that just went terminal wrote the draft: repaint the editors and the completeness signal once.
    if (eraAtiva.current && !ativaAgora) {
      void qc.invalidateQueries({ queryKey: studioKeys.conteudoAll(key) });
      void qc.invalidateQueries({ queryKey: studioKeys.detail(key) });
    }
    eraAtiva.current = ativaAgora;
  }, [ativaAgora, qc, key]);
  return {
    geracao,
    showSkeleton: lista.showSkeleton,
    isRefreshing: lista.isRefreshing || detalhe.isRefreshing,
    isError: lista.isError,
    error: lista.error,
    refetch: lista.refetch,
    ativa: ativaAgora,
  };
}

/** `area -> chave -> estado` of the latest run, for the "Gerado por IA" badges in the draft editors. */
export function useItensGerados(key: string) {
  const { geracao } = useUltimaGeracao(key);
  return useMemo(() => {
    const out: Partial<Record<GeracaoArea, Record<string, ItemGerado["estado"]>>> = {};
    for (const a of geracao?.areas ?? []) {
      out[a.area] = Object.fromEntries(a.itens.map((i) => [i.chave, i.estado]));
    }
    return out;
  }, [geracao]);
}

/** Commit the server's run into the list (target) and its own detail entry (onSuccess — the id is only known then). */
function useWriteRun(key: string) {
  const qc = useQueryClient();
  return {
    targets: [
      {
        queryKey: studioKeys.geracoes(key),
        commit: (old: GeracoesList | undefined, g: GeracaoOut) => upsertInList(old, g),
      },
    ],
    // A run writes the DRAFT: every content editor of the agent refreshes in the background.
    invalidate: [studioKeys.conteudoAll(key), studioKeys.detail(key)],
    onSuccess: (g: GeracaoOut) => {
      qc.setQueryData(studioKeys.geracao(key, g.id), g);
    },
  };
}

export function useCreateGeracao(key: string) {
  const w = useWriteRun(key);
  return useCacheWriteMutation<GeracaoOut, GeracaoCreateInput>({
    mutationFn: (payload) => api.post<GeracaoOut>(base(key), payload),
    ...w,
  });
}

export function useRepetirArea(key: string) {
  const w = useWriteRun(key);
  return useCacheWriteMutation<GeracaoOut, { id: string; area: GeracaoArea; forcar?: boolean }>({
    mutationFn: ({ id, area, forcar }) =>
      api.post<GeracaoOut>(`${base(key)}/${seg(id)}/areas/${seg(area)}/repetir`, { forcar: !!forcar }),
    ...w,
  });
}

export function useCancelarGeracao(key: string) {
  const w = useWriteRun(key);
  return useCacheWriteMutation<GeracaoOut, { id: string }>({
    mutationFn: ({ id }) => api.post<GeracaoOut>(`${base(key)}/${seg(id)}/cancelar`, {}),
    ...w,
  });
}
