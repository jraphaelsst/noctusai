/**
 * Supervisão (Maya) — maya-blocks CONTRACT §4.3 / §4.4 / §4.5.
 *
 *   GET/PUT /api/supervisao/config                → SupervisaoConfig   (owner only)
 *   GET     /api/supervisao/scorecards?dia=…      → ScorecardsDia      (owner only)
 *   GET     /api/supervisao/handoffs?status=…     → HandoffsPagina     (owner/admin)
 *
 * Bodies are not wrapped in `{data}`. Ratios are FRACTIONS; a metric that is
 * `null` or absent means "no data" and is never coerced to 0 here.
 *
 * Loading = two signals off `data` (never `isLoading`), computed in the hook.
 */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface SupervisaoConfig {
  supervisao_ativa: boolean;
  horas_para_assumir: number;
  updated_at: string | null;
  updated_by: string | null;
}

export type ValorMetrica = number | Record<string, number> | null;

export interface Scorecard {
  bloco: string;
  agent_key: string | null;
  rubrica_versao: string;
  calculado_at: string;
  metricas: Record<string, ValorMetrica>;
}

export interface ScorecardsDia {
  dia: string;
  supervisao_ativa: boolean;
  scorecards: Scorecard[];
}

export type StatusHandoff = "emitido" | "assumido" | "expirado";

export interface Handoff {
  id: string;
  de_bloco: string;
  para_bloco: string;
  gatilho: "novo_lead" | "movimento_etapa";
  status: StatusHandoff;
  atrasado: boolean;
  created_at: string;
  assumido_at: string | null;
  expirado_at: string | null;
  de_agent_key: string | null;
  para_agent_key: string | null;
  referencias: Record<string, string | null>;
  card: { titulo: string; link: string } | null;
}

export interface HandoffsPagina {
  itens: Handoff[];
  proximo_cursor: string | null;
}

export const SUPERVISAO_KEY = ["sw", "supervisao"] as const;
export const HORAS_MIN = 1;
export const HORAS_MAX = 168;

export function useSupervisaoConfig() {
  const q = useQuery({
    queryKey: [...SUPERVISAO_KEY, "config"] as const,
    queryFn: () => api.get<SupervisaoConfig>("/api/supervisao/config"),
    // A 403 (not the owner) is an answer, not a blip — don't retry it.
    retry: (n, err) => statusDe(err) !== 403 && n < 2,
  });
  return { ...q, showSkeleton: q.isPending && !q.data, isRefreshing: q.isFetching && !!q.data };
}

export function useSalvarSupervisaoConfig() {
  const qc = useQueryClient();
  return useMutation<SupervisaoConfig, unknown, { supervisao_ativa: boolean; horas_para_assumir: number }>({
    mutationFn: (body) => api.put<SupervisaoConfig>("/api/supervisao/config", body),
    onSuccess: (estado) => {
      qc.setQueryData([...SUPERVISAO_KEY, "config"], estado);
      // Scorecards / handoffs echo `supervisao_ativa` — refetch them.
      void qc.invalidateQueries({ queryKey: [...SUPERVISAO_KEY, "scorecards"] });
      void qc.invalidateQueries({ queryKey: [...SUPERVISAO_KEY, "handoffs"] });
    },
  });
}

/**
 * The scorecards of one SP calendar day. `placeholderData` keeps the previous
 * day on screen while the next one loads (day switch = key change). The data
 * is org-level counts for the owner — no per-user personal data — so showing
 * the previous day during the switch leaks nothing.
 */
export function useScorecards(dia: string, enabled = true) {
  const q = useQuery({
    queryKey: [...SUPERVISAO_KEY, "scorecards", dia] as const,
    queryFn: () => api.get<ScorecardsDia>(`/api/supervisao/scorecards?dia=${encodeURIComponent(dia)}`),
    placeholderData: (prev) => prev,
    enabled,
  });
  return { ...q, showSkeleton: q.isPending && !q.data, isRefreshing: q.isFetching && !!q.data };
}

/** Handoffs still `emitido` (not taken over), newest first, cursor-paged. */
export function useHandoffsPendentes(enabled = true) {
  const q = useInfiniteQuery({
    queryKey: [...SUPERVISAO_KEY, "handoffs", "emitido"] as const,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ status: "emitido", limit: "50" });
      if (pageParam) params.set("cursor", pageParam);
      return api.get<HandoffsPagina>(`/api/supervisao/handoffs?${params.toString()}`);
    },
    getNextPageParam: (ultima) => ultima.proximo_cursor,
    enabled,
  });
  return { ...q, showSkeleton: q.isPending && !q.data, isRefreshing: q.isFetching && !!q.data };
}

export function statusDe(err: unknown): number | null {
  const s = (err as { status?: unknown } | null)?.status;
  return typeof s === "number" ? s : null;
}

// ── SP calendar days (contract §3.1: `dia` is America/Sao_Paulo) ──────────

/** Today as `YYYY-MM-DD` in America/Sao_Paulo. */
export function hojeSP(agora: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Sao_Paulo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(agora);
}

/** The calendar day before `dia` (`YYYY-MM-DD` arithmetic, timezone-free). */
export function diaAnterior(dia: string): string {
  const d = new Date(`${dia}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

/** Yesterday in SP — the default and the latest day the API accepts. */
export function ontemSP(agora: Date = new Date()): string {
  return diaAnterior(hojeSP(agora));
}

export const DIA_RE = /^\d{4}-\d{2}-\d{2}$/;

/** `YYYY-MM-DD` → `DD/MM/AAAA`. */
export function formatarDia(dia: string): string {
  const [a, m, d] = dia.split("-");
  return `${d}/${m}/${a}`;
}
