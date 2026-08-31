/**
 * Leads analytics hooks — `/api/leads/analytics/*` + `/api/leads/facets`.
 *
 * Every hook here accepts the shared `LeadsFilters` (§5.1) so every chart on
 * every subtab reacts to the same filter set. Analytics + facets responses
 * are `success_response` → `{ data: T }` (not paginated).
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import {
  buildLeadsQueryParams,
  leadsFiltersQueryKey,
  type LeadsFilters,
} from "./useLeadsFilters";
import type {
  ByDimensionOut,
  HeatmapOut,
  LeadsSummary,
  TimeseriesOut,
} from "@/pages/leads/types";

interface SuccessEnvelope<T> {
  data: T;
}

const BASE = "/api/leads/analytics";
const FAMILY_KEY = ["leads", "analytics"] as const;

// ─── Summary ─────────────────────────────────────────────────────────────────

export function useLeadsSummary(filters: LeadsFilters) {
  const qs = buildLeadsQueryParams(filters).toString();
  return useQuery<LeadsSummary>({
    queryKey: [...FAMILY_KEY, "summary", leadsFiltersQueryKey(filters)],
    queryFn: async () => {
      const res = await api.get<SuccessEnvelope<LeadsSummary>>(
        qs ? `${BASE}/summary?${qs}` : `${BASE}/summary`,
      );
      return res.data;
    },
    // `filters` (dates/origem/etc.) drives the queryKey — every filter
    // tweak swaps the summary to a fresh key with no cached data, so
    // without this the whole card blanks to undefined for one round trip.
    // Keep last summary on screen until the new one lands.
    placeholderData: (prev) => prev,
  });
}

// ─── Timeseries ──────────────────────────────────────────────────────────────

export type TimeseriesGrain = "dia" | "mes" | "ano";
export type TimeseriesSplit = "origem" | "corretor" | "tipo" | "tier";

export interface TimeseriesParams {
  grain?: TimeseriesGrain;
  split?: TimeseriesSplit;
}

export function useLeadsTimeseries(filters: LeadsFilters, params?: TimeseriesParams) {
  const search = buildLeadsQueryParams(filters);
  search.set("grain", params?.grain ?? "mes");
  if (params?.split) search.set("split", params.split);
  const qs = search.toString();

  return useQuery<TimeseriesOut>({
    queryKey: [...FAMILY_KEY, "timeseries", leadsFiltersQueryKey(filters), params],
    queryFn: async () => {
      const res = await api.get<SuccessEnvelope<TimeseriesOut>>(`${BASE}/timeseries?${qs}`);
      return res.data;
    },
    // `filters`/`params` (grain, split) drive the queryKey — keep the
    // previous chart on screen through a filter/grain change instead of
    // blanking it while the new series loads.
    placeholderData: (prev) => prev,
  });
}

// ─── By dimension ────────────────────────────────────────────────────────────

export type LeadsDimension =
  | "origem"
  | "corretor"
  | "empreendimento"
  | "regiao"
  | "tier"
  | "tipo";

export interface ByDimensionParams {
  dim: LeadsDimension;
  limit?: number;
}

export function useLeadsByDimension(filters: LeadsFilters, params: ByDimensionParams) {
  const search = buildLeadsQueryParams(filters);
  search.set("dim", params.dim);
  if (params.limit != null) search.set("limit", String(params.limit));
  const qs = search.toString();

  return useQuery<ByDimensionOut>({
    queryKey: [...FAMILY_KEY, "by-dimension", leadsFiltersQueryKey(filters), params],
    queryFn: async () => {
      const res = await api.get<SuccessEnvelope<ByDimensionOut>>(`${BASE}/by-dimension?${qs}`);
      return res.data;
    },
    // Same reasoning — `filters`/`params.dim` drive the queryKey.
    placeholderData: (prev) => prev,
  });
}

// ─── Heatmap ─────────────────────────────────────────────────────────────────

export function useLeadsHeatmap(filters: LeadsFilters) {
  const qs = buildLeadsQueryParams(filters).toString();
  return useQuery<HeatmapOut>({
    queryKey: [...FAMILY_KEY, "heatmap", leadsFiltersQueryKey(filters)],
    queryFn: async () => {
      const res = await api.get<SuccessEnvelope<HeatmapOut>>(
        qs ? `${BASE}/heatmap?${qs}` : `${BASE}/heatmap`,
      );
      return res.data;
    },
    // `filters` drives the queryKey — keep the previous heatmap on screen
    // through a filter change instead of blanking it for one round trip.
    placeholderData: (prev) => prev,
  });
}

// ─── Facets (filter dropdown options) ───────────────────────────────────────

export interface FacetValue {
  value: string;
  count: number;
}

export interface LeadsFacets {
  empreendimentos: FacetValue[];
  regioes: FacetValue[];
  anos: number[];
}

export function useLeadsFacets() {
  return useQuery<LeadsFacets>({
    queryKey: ["leads", "facets"],
    queryFn: async () => {
      const res = await api.get<SuccessEnvelope<LeadsFacets>>("/api/leads/facets");
      return res.data;
    },
  });
}
