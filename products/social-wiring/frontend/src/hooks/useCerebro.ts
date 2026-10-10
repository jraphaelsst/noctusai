/**
 * Segundo Cérebro (list + editor + bio) — TanStack Query hooks over
 * `/api/media-creation/cerebro` (build contract:
 * projects/core-studio/specs/cerebro-contract.md §4).
 *
 * Responses arrive wrapped in `success_response` ({success, data}); we unwrap
 * at the boundary. Loading rule (lying-loading-state.md): every query hook
 * returns `showSkeleton = isPending && !data` and `isRefreshing = isFetching
 * && !!data`, never `isLoading`. Every mutation invalidates the whole
 * `["sw","cerebro"]` family. The editor polls every 3 s while a synthesis or
 * import is non-terminal (contract §6).
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

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
    refetchInterval: (q) => (brainEmAndamento(q.state.data) ? POLL_MS : false),
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

function useInvalidateCerebro() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: CEREBRO_KEY });
}

export function useCriarBrain() {
  const invalidate = useInvalidateCerebro();
  return useMutation({
    mutationFn: async (v: { marca_id: string; name: string }) =>
      unwrap(await api.post<Envelope<BrainSummary>>(`${BASE}/brains`, v)),
    onSuccess: invalidate,
  });
}

export function useRenomearBrain() {
  const invalidate = useInvalidateCerebro();
  return useMutation({
    mutationFn: async (v: { id: string; name: string }) =>
      unwrap(await api.patch<Envelope<BrainSummary>>(`${BASE}/brains/${encodeURIComponent(v.id)}`, { name: v.name })),
    onSuccess: invalidate,
  });
}

export function useExcluirBrain() {
  const invalidate = useInvalidateCerebro();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`${BASE}/brains/${encodeURIComponent(id)}`);
    },
    onSuccess: invalidate,
  });
}

export function useSalvarConteudo() {
  const invalidate = useInvalidateCerebro();
  return useMutation({
    mutationFn: async (v: { id: string; content: string; expected_version: number }) =>
      unwrap(
        await api.put<Envelope<BrainSummary>>(`${BASE}/brains/${encodeURIComponent(v.id)}/content`, {
          content: v.content,
          expected_version: v.expected_version,
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useEnviarArquivo() {
  const invalidate = useInvalidateCerebro();
  return useMutation({
    mutationFn: async (v: { id: string; file: File }) => {
      const form = new FormData();
      form.append("file", v.file, v.file.name);
      return uploadMultipart<Envelope<unknown>>(`${BASE}/brains/${encodeURIComponent(v.id)}/imports/file`, form);
    },
    onSuccess: invalidate,
  });
}

export function useSalvarPerfil() {
  const invalidate = useInvalidateCerebro();
  return useMutation({
    mutationFn: async (v: { marca_id: string; bio: string }) =>
      unwrap(await api.put<Envelope<Perfil>>(`${BASE}/perfil`, v)),
    onSuccess: invalidate,
  });
}
