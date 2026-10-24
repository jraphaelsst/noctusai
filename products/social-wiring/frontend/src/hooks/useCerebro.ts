/**
 * Segundo Cérebro (list + editor + bio) — TanStack Query hooks over
 * `/api/media-creation/cerebro` (build contract:
 * projects/core-studio-build/specs/cerebro-contract.md §4).
 *
 * Responses arrive wrapped in `success_response` ({success, data}); we unwrap
 * at the boundary. Loading rule (lying-loading-state.md): every query hook
 * returns `showSkeleton = isPending && !data` and `isRefreshing = isFetching
 * && !!data`, never `isLoading`. Every mutation invalidates the whole
 * `["sw","cerebro"]` family. The editor polls every 3 s while a synthesis or
 * import is non-terminal (contract §6).
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@noctusai/seed/infra";
import { jobPolling, handOffToPolling } from "@noctusai/lib";

import { INSTAGRAM_PROVIDER, useInstagramProfile } from "@/hooks/useInstagramInsights";
import { useIntegrationAccounts } from "@/hooks/useIntegrationAccounts";
import { uploadMultipart } from "@/hooks/useCardHub";
import type { BrainDetail, BrainSummary, Perfil } from "@/types/cerebro";

const BASE = "/api/media-creation/cerebro";
export const CEREBRO_KEY = ["sw", "cerebro"] as const;
const brainsKey = (marcaId: string | null) => [...CEREBRO_KEY, marcaId, "brains"] as const;
const brainKey = (id: string | null) => [...CEREBRO_KEY, "brain", id] as const;
const perfilKey = (marcaId: string | null) => [...CEREBRO_KEY, marcaId, "perfil"] as const;

export const POLL_MS = 3000;

interface Envelope<T> {
  success?: boolean;
  data: T;
}
const unwrap = <T>(res: Envelope<T>): T => res.data;

/** True while a synthesis or an import is still running (drives the 3 s poll). */
export function brainEmAndamento(b: BrainDetail | undefined): boolean {
  if (!b) return false;
  return b.synthesis_status === "processing" || b.imports.some((i) => i.status === "processing");
}

// ─── Queries ────────────────────────────────────────────────────────────────

export function useCerebroBrains(marcaId: string | null) {
  const query = useQuery({
    queryKey: brainsKey(marcaId),
    enabled: !!marcaId,
    queryFn: async () =>
      unwrap(
        await api.get<Envelope<BrainSummary[]>>(`${BASE}/brains?marca_id=${encodeURIComponent(marcaId as string)}`),
      ) ?? [],
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    showSkeleton: !!marcaId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export function useCerebroBrain(id: string | null) {
  const query = useQuery({
    queryKey: brainKey(id),
    enabled: !!id,
    queryFn: async () =>
      unwrap(await api.get<Envelope<BrainDetail>>(`${BASE}/brains/${encodeURIComponent(id as string)}`)),
    ...jobPolling(brainEmAndamento, POLL_MS),
    placeholderData: (prev) => (prev && prev.id === id ? prev : undefined),
  });
  return {
    ...query,
    showSkeleton: !!id && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export function useCerebroPerfil(marcaId: string | null) {
  const query = useQuery({
    queryKey: perfilKey(marcaId),
    enabled: !!marcaId,
    queryFn: async () =>
      unwrap(await api.get<Envelope<Perfil>>(`${BASE}/perfil?marca_id=${encodeURIComponent(marcaId as string)}`)),
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    showSkeleton: !!marcaId && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

/**
 * Biography of the marca's connected Instagram account, or null when the marca
 * has none (the bio card then omits "Usar a bio do Instagram"). Reads the
 * existing integration-accounts + Instagram profile hooks; no new endpoint.
 */
export function useBioInstagram(marcaId: string | null) {
  const accounts = useIntegrationAccounts({ provider: INSTAGRAM_PROVIDER, marcaId: marcaId ?? undefined });
  const conectada = (accounts.data ?? []).find((a) => a.status !== "disconnected") ?? null;
  const profile = useInstagramProfile(marcaId ? (conectada?.id ?? null) : null);
  const bio = profile.data?.biography?.trim() || null;
  return { temConta: !!marcaId && !!conectada, bio };
}

// ─── Mutations ──────────────────────────────────────────────────────────────

/** A brain's summary fields, committed into every cached brains list (prefix) and the open brain's detail. */
function brainTargets(id: string) {
  return [
    {
      queryKey: CEREBRO_KEY,
      match: "prefix" as const,
      commit: (old: BrainSummary[] | undefined, saved: BrainSummary) => listOps.patch(old, id, saved),
    },
    {
      queryKey: brainKey(id),
      commit: (old: BrainDetail | undefined, saved: BrainSummary) => listOps.merge(old, saved),
    },
  ];
}

export function useCriarBrain() {
  return useCacheWriteMutation<BrainSummary, { marca_id: string; name: string }>({
    mutationFn: async (v) => unwrap(await api.post<Envelope<BrainSummary>>(`${BASE}/brains`, v)),
    targets: (v) => [
      { queryKey: brainsKey(v.marca_id), commit: (old, saved) => listOps.replace(old, saved.id, saved) },
    ],
    invalidate: [CEREBRO_KEY],
  });
}

export function useRenomearBrain() {
  return useCacheWriteMutation<BrainSummary, { id: string; name: string }>({
    mutationFn: async (v) =>
      unwrap(await api.patch<Envelope<BrainSummary>>(`${BASE}/brains/${encodeURIComponent(v.id)}`, { name: v.name })),
    targets: (v) => [
      {
        queryKey: CEREBRO_KEY,
        match: "prefix",
        optimistic: (old: BrainSummary[] | undefined) => listOps.patch(old, v.id, { name: v.name }),
      },
      ...brainTargets(v.id),
    ],
  });
}

export function useExcluirBrain() {
  return useCacheWriteMutation<void, string>({
    mutationFn: async (id) => {
      await api.delete(`${BASE}/brains/${encodeURIComponent(id)}`);
    },
    targets: (id) => [
      {
        queryKey: CEREBRO_KEY,
        match: "prefix",
        optimistic: (old: BrainSummary[] | undefined) => listOps.remove(old, id),
      },
    ],
  });
}

export function useSalvarConteudo() {
  return useCacheWriteMutation<BrainSummary, { id: string; content: string; expected_version: number }>({
    mutationFn: async (v) =>
      unwrap(
        await api.put<Envelope<BrainSummary>>(`${BASE}/brains/${encodeURIComponent(v.id)}/content`, {
          content: v.content,
          expected_version: v.expected_version,
        }),
      ),
    targets: (v) => brainTargets(v.id),
  });
}

export function useEnviarArquivo() {
  const qc = useQueryClient();
  return useMutation({ // noc-allow: invalidate-only — the upload starts a server-side import job; the answer is not the brain, whose imports/synthesis arrive via the polled detail
    mutationFn: async (v: { id: string; file: File }) => {
      const form = new FormData();
      form.append("file", v.file, v.file.name);
      return uploadMultipart<Envelope<unknown>>(`${BASE}/brains/${encodeURIComponent(v.id)}/imports/file`, form);
    },
    // The import runs on the server: hand the polled detail off until it has run (F87).
    onSuccess: () => handOffToPolling(qc, CEREBRO_KEY),
  });
}

export function useSalvarPerfil() {
  return useCacheWriteMutation<Perfil, { marca_id: string; bio: string }>({
    mutationFn: async (v) => unwrap(await api.put<Envelope<Perfil>>(`${BASE}/perfil`, v)),
    targets: (v) => [{ queryKey: perfilKey(v.marca_id), commit: (_old, saved) => saved }],
    invalidate: [CEREBRO_KEY],
  });
}
