/**
 * useLeadsFilters — the single owner of the Leads module's shared filter
 * state (§5.1 of leads-module-PROJECT.md), mirrored to the URL query string
 * so a filtered view is linkable and survives reload.
 *
 * Every subtab of the Leads page reads the SAME filters from this one hook
 * and every analytics/list hook (useLeads*.ts) accepts a `LeadsFilters`
 * object built here — one filter set drives every chart + the table.
 *
 * Multi-value dimensions (`ano`, `mes`, `origem_id`, `corretor_id`, `tipo`,
 * `tier`, `empreendimento`, `regiao`) are OR-within-dimension, AND-across-
 * dimensions per the contract — encoded as repeated query params
 * (`?ano=2025&ano=2026`), never comma-joined, so the wire shape matches
 * §5.1 exactly.
 */
import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

// ─── Types ───────────────────────────────────────────────────────────────────

export type LeadsMultiKey =
  | "ano"
  | "mes"
  | "origem_id"
  | "corretor_id"
  | "tipo"
  | "tier"
  | "empreendimento"
  | "regiao";

export interface LeadsFilters {
  de: string | null;
  ate: string | null;
  ano: string[];
  mes: string[];
  origem_id: string[];
  corretor_id: string[];
  tipo: string[];
  tier: string[];
  empreendimento: string[];
  regiao: string[];
  needs_review: boolean | null;
  q: string | null;
}

const MULTI_KEYS: LeadsMultiKey[] = [
  "ano",
  "mes",
  "origem_id",
  "corretor_id",
  "tipo",
  "tier",
  "empreendimento",
  "regiao",
];

export const EMPTY_FILTERS: LeadsFilters = {
  de: null,
  ate: null,
  ano: [],
  mes: [],
  origem_id: [],
  corretor_id: [],
  tipo: [],
  tier: [],
  empreendimento: [],
  regiao: [],
  needs_review: null,
  q: null,
};

// ─── Pure helpers (also used directly by hooks that don't need URL sync) ───

export function parseLeadsFilters(params: URLSearchParams): LeadsFilters {
  return {
    de: params.get("de"),
    ate: params.get("ate"),
    ano: params.getAll("ano"),
    mes: params.getAll("mes"),
    origem_id: params.getAll("origem_id"),
    corretor_id: params.getAll("corretor_id"),
    tipo: params.getAll("tipo"),
    tier: params.getAll("tier"),
    empreendimento: params.getAll("empreendimento"),
    regiao: params.getAll("regiao"),
    needs_review: params.has("needs_review") ? params.get("needs_review") === "true" : null,
    q: params.get("q") || null,
  };
}

/**
 * Build a `URLSearchParams` for the canonical filter set (§5.1) — the shape
 * every `useLeads*` query hook appends to its own endpoint-specific params.
 * Absent/empty = no constraint (never sends an empty param).
 */
export function buildLeadsQueryParams(filters: LeadsFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.de) params.set("de", filters.de);
  if (filters.ate) params.set("ate", filters.ate);
  for (const key of MULTI_KEYS) {
    for (const value of filters[key]) {
      if (value) params.append(key, value);
    }
  }
  if (filters.needs_review !== null) {
    params.set("needs_review", String(filters.needs_review));
  }
  if (filters.q) params.set("q", filters.q);
  return params;
}

/** Stable serialization for use as a TanStack Query key fragment. */
export function leadsFiltersQueryKey(filters: LeadsFilters): string {
  return buildLeadsQueryParams(filters).toString();
}

function countActive(filters: LeadsFilters): number {
  let n = 0;
  if (filters.de) n += 1;
  if (filters.ate) n += 1;
  for (const key of MULTI_KEYS) n += filters[key].length;
  if (filters.needs_review !== null) n += 1;
  if (filters.q) n += 1;
  return n;
}

// ─── Hook ────────────────────────────────────────────────────────────────────

export function useLeadsFilters() {
  const [searchParams, setSearchParams] = useSearchParams();

  const filters = useMemo(() => parseLeadsFilters(searchParams), [searchParams]);

  const writeFilters = useCallback(
    (next: LeadsFilters) => {
      const params = buildLeadsQueryParams(next);
      setSearchParams(params, { replace: true });
    },
    [setSearchParams],
  );

  const setDateRange = useCallback(
    (de: string | null, ate: string | null) => {
      writeFilters({ ...filters, de, ate });
    },
    [filters, writeFilters],
  );

  const setSingle = useCallback(
    (key: "q", value: string | null) => {
      writeFilters({ ...filters, [key]: value || null });
    },
    [filters, writeFilters],
  );

  const setNeedsReview = useCallback(
    (value: boolean | null) => {
      writeFilters({ ...filters, needs_review: value });
    },
    [filters, writeFilters],
  );

  /** Toggle one value in/out of a multi-value dimension. */
  const toggleMulti = useCallback(
    (key: LeadsMultiKey, value: string) => {
      const current = filters[key];
      const next = current.includes(value)
        ? current.filter((v) => v !== value)
        : [...current, value];
      writeFilters({ ...filters, [key]: next });
    },
    [filters, writeFilters],
  );

  const clearKey = useCallback(
    (key: keyof LeadsFilters) => {
      const cleared: LeadsFilters = {
        ...filters,
        [key]: Array.isArray(filters[key]) ? [] : null,
      } as LeadsFilters;
      writeFilters(cleared);
    },
    [filters, writeFilters],
  );

  const clearAll = useCallback(() => {
    setSearchParams(new URLSearchParams(), { replace: true });
  }, [setSearchParams]);

  const queryString = useMemo(() => buildLeadsQueryParams(filters).toString(), [filters]);
  const activeCount = useMemo(() => countActive(filters), [filters]);

  return {
    filters,
    setDateRange,
    setSingle,
    setNeedsReview,
    toggleMulti,
    clearKey,
    clearAll,
    queryString,
    activeCount,
    isActive: activeCount > 0,
  };
}
