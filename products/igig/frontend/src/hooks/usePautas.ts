/**
 * Calendário editorial e copywriting hooks — Módulo 3.
 *
 * Backend mirror: `app/routers/pauta_router.py`.
 *
 * `caracteres_copy` comes FROM the server rather than being computed here on
 * every keystroke: the counter's definition lives in one place, and the
 * calendar list can flag an over-long legenda without re-deriving the rule.
 * The editor still counts locally while you type — that is presentation, and
 * it reconciles with the server value on save.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type Formato = "feed" | "carrossel" | "reels" | "story" | "artigo" | "video";
export type Funil = "topo" | "meio" | "fundo";

export const FORMATOS: Formato[] = ["feed", "carrossel", "reels", "story", "artigo", "video"];
export const FUNIS: Funil[] = ["topo", "meio", "fundo"];

/** Nível de consciência, in the spec's own words. */
export const FUNIL_LABEL: Record<Funil, string> = {
  topo: "Topo de funil",
  meio: "Meio de funil",
  fundo: "Fundo de funil",
};

export interface Pauta {
  id: string;
  org_id: string;
  cliente_id: string;
  marca_id: string | null;
  titulo: string;
  formato: Formato | null;
  funil: Funil | null;
  linha_editorial: string | null;
  copy_texto: string | null;
  direcao_video: string | null;
  canal: string | null;
  data_publicacao: string | null;
  caracteres_copy: number;
}

export interface Calendario {
  inicio: string;
  fim: string;
  itens: Pauta[];
}

export interface Peca {
  id: string;
  pauta_id: string;
  storage_key: string;
  nome_arquivo: string | null;
  mime_type: string | null;
  ordem: number;
}

export const PAUTAS_QUERY_KEY = ["igig", "pautas"] as const;

export function useCalendario(inicio: string, fim: string) {
  const query = useQuery({
    queryKey: [...PAUTAS_QUERY_KEY, "calendario", inicio, fim],
    queryFn: () => api.get<Calendario>("/api/pautas/calendario", { inicio, fim }),
    // `inicio`/`fim` ride in the key — paging to another month is a brand
    // new key. Without this the whole grid would go back to a skeleton on
    // every page; with it, the previous month's pautas stay on screen until
    // the new month lands.
    placeholderData: (prev) => prev,
  });
  return {
    ...query,
    itens: query.data?.itens ?? [],
    loading: query.isPending && !query.data,
  };
}

/** Every pauta, including unscheduled ones — which the calendar excludes. */
export function usePautas(clienteId?: string) {
  const query = useQuery({
    queryKey: [...PAUTAS_QUERY_KEY, "lista", clienteId ?? ""],
    queryFn: () => api.get<Pauta[]>("/api/pautas", clienteId ? { cliente_id: clienteId } : {}),
  });
  return {
    ...query,
    pautas: query.data ?? [],
    loading: query.isPending && !query.data,
  };
}

export function useCriarPauta() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { cliente_id: string; titulo: string } & Partial<Pauta>) =>
      api.post<Pauta>("/api/pautas", payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: PAUTAS_QUERY_KEY }),
  });
}

export function useAtualizarPauta() {
  const qc = useQueryClient();
  return useMutation({
    /**
     * `patch` is sent as-is — including explicit `null`s. Stripping them
     * would make unscheduling a pauta impossible, since "clear this date"
     * and "don't touch this field" would become indistinguishable.
     */
    mutationFn: ({ id, ...patch }: { id: string } & Partial<Pauta>) =>
      api.patch<Pauta>(`/api/pautas/${id}`, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: PAUTAS_QUERY_KEY }),
  });
}

export function useRemoverPauta() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<{ ok: boolean }>(`/api/pautas/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: PAUTAS_QUERY_KEY }),
  });
}

/**
 * Upload the visual asset (peça) the client reviews beside the legenda.
 *
 * Without this, a pauta could never carry the artwork the Módulo 4 approval
 * portal is supposed to show — the endpoint existed and had no consumer.
 */
export function useEnviarPeca() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ pautaId, arquivo }: { pautaId: string; arquivo: File }) => {
      const form = new FormData();
      form.append("arquivo", arquivo);
      return api.upload<Peca>(`/api/pautas/${pautaId}/pecas`, form);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: PAUTAS_QUERY_KEY }),
  });
}

export function usePecas(pautaId: string | undefined) {
  const query = useQuery({
    queryKey: [...PAUTAS_QUERY_KEY, "pecas", pautaId],
    queryFn: () => api.get<Peca[]>(`/api/pautas/${pautaId}/pecas`),
    enabled: Boolean(pautaId),
  });
  // Two signals, never `isLoading` — an empty state gated on `isLoading`
  // renders over data that is merely refetching after an upload.
  // → KB § PATTERNS/frontend/lying-loading-state.md
  return {
    ...query,
    pecas: query.data ?? [],
    loading: query.isPending && !query.data,
  };
}
