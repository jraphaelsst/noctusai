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
 *
 * URL→state hydration is VALIDATED (see "Validators" below). `origem_id` /
 * `corretor_id` are typed `list[UUID]` server-side — a stale/bookmarked/
 * shared URL carrying a non-UUID value (e.g. a slug a previous bug wrote,
 * `?origem_id=senseys`) 422s every Leads endpoint at once, because all six
 * share `get_lead_filters`. A malformed value is dropped from state AND
 * scrubbed from the URL (via `replace`, never `push`) so the page loads
 * normally instead of bricking — self-healing, no user action required.
 * Unknown/unrelated query params are left untouched.
 */
import { useCallback, useEffect, useMemo, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

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

/**
 * Once a bad value has been sanitized + surfaced for a given raw
 * `?a=b&c=d` search string, don't re-notify — `LeadsFilterBar` AND the
 * active subtab both mount `useLeadsFilters()` in the same render tree, so
 * without this guard the SAME hydration event fires the toast (and the
 * URL-rewrite) once per mounted hook instance. Module-scope by design: the
 * question is "has THIS exact raw querystring already been handled", not
 * per-component state.
 */
let lastSanitizedRawSearch: string | null = null;

// ─── Validators (pure — the source of truth for "well-formed") ─────────────

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** RFC-4122-shaped UUID (any version/variant) — matches the backend's `UUID` type. */
export function isValidUuid(value: string): boolean {
  return UUID_RE.test(value);
}

const YEAR_RE = /^\d{4}$/;
const MIN_YEAR = 2000;
const MAX_YEAR = 2100;

/** Plausible 4-digit calendar year. */
export function isValidYear(value: string): boolean {
  if (!YEAR_RE.test(value)) return false;
  const n = Number(value);
  return n >= MIN_YEAR && n <= MAX_YEAR;
}

const MONTH_RE = /^(?:[1-9]|1[0-2])$/;

/** 1..12, no leading zero required (matches how `MultiSelectPopover` writes it). */
export function isValidMonth(value: string): boolean {
  return MONTH_RE.test(value);
}

const TIPO_VALUES = new Set(["novo", "retorno", "desconhecido"]);

/** One of the backend `tipo_lead` enum values. */
export function isValidTipo(value: string): boolean {
  return TIPO_VALUES.has(value);
}

const TIER_VALUES = new Set(["simples", "destaque", "super_destaque"]);

/** One of the backend lead-tier enum values. */
export function isValidTier(value: string): boolean {
  return TIER_VALUES.has(value);
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Strict `YYYY-MM-DD` — regex shape AND a real calendar date (rejects e.g. `2026-02-30`). */
export function isValidDateStr(value: string): boolean {
  if (!DATE_RE.test(value)) return false;
  const [y, m, d] = value.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  return date.getUTCFullYear() === y && date.getUTCMonth() === m - 1 && date.getUTCDate() === d;
}

/**
 * Per-multi-key validator. `null` = no format constraint (free-text facets
 * — `empreendimento` / `regiao` are untyped strings server-side, nothing to
 * reject).
 */
const MULTI_VALIDATORS: Record<LeadsMultiKey, ((value: string) => boolean) | null> = {
  ano: isValidYear,
  mes: isValidMonth,
  origem_id: isValidUuid,
  corretor_id: isValidUuid,
  tipo: isValidTipo,
  tier: isValidTier,
  empreendimento: null,
  regiao: null,
};

// ─── Pure helpers (also used directly by hooks that don't need URL sync) ───

export interface LeadsFiltersParseResult {
  filters: LeadsFilters;
  /** Keys that had ≥1 value dropped during hydration — empty when the URL was clean. */
  invalidKeys: string[];
}

/**
 * Parse + VALIDATE the URL query string into `LeadsFilters`. Anything that
 * fails its validator (see above) is silently dropped from the returned
 * state — never forwarded to a request. Also reports which keys had
 * something dropped, so callers can decide whether to scrub the URL / notify.
 */
export function parseLeadsFiltersDetailed(params: URLSearchParams): LeadsFiltersParseResult {
  const invalidKeys: string[] = [];

  function singleDate(key: "de" | "ate"): string | null {
    const raw = params.get(key);
    if (raw === null) return null;
    if (isValidDateStr(raw)) return raw;
    invalidKeys.push(key);
    return null;
  }

  function multi(key: LeadsMultiKey): string[] {
    const raw = params.getAll(key);
    const validator = MULTI_VALIDATORS[key];
    if (!validator) return raw;
    const valid = raw.filter(validator);
    if (valid.length !== raw.length) invalidKeys.push(key);
    return valid;
  }

  const filters: LeadsFilters = {
    de: singleDate("de"),
    ate: singleDate("ate"),
    ano: multi("ano"),
    mes: multi("mes"),
    origem_id: multi("origem_id"),
    corretor_id: multi("corretor_id"),
    tipo: multi("tipo"),
    tier: multi("tier"),
    empreendimento: multi("empreendimento"),
    regiao: multi("regiao"),
    needs_review: params.has("needs_review") ? params.get("needs_review") === "true" : null,
    q: params.get("q") || null,
  };

  return { filters, invalidKeys };
}

/** Parse the URL query string into `LeadsFilters` — malformed values silently dropped. */
export function parseLeadsFilters(params: URLSearchParams): LeadsFilters {
  return parseLeadsFiltersDetailed(params).filters;
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

/**
 * Rewrite ONLY the known Leads filter keys on top of `original`, replacing
 * each with its validated value (or dropping it entirely if invalid).
 * Anything else in the URL (unrelated / unknown params) passes through
 * byte-for-byte — this is what makes the scrub surgical instead of a
 * blanket `buildLeadsQueryParams(filters)` rewrite (which would silently
 * wipe any param this hook doesn't itself own).
 */
function scrubInvalidParams(original: URLSearchParams, sanitized: LeadsFilters): URLSearchParams {
  const next = new URLSearchParams(original);

  next.delete("de");
  if (sanitized.de) next.set("de", sanitized.de);
  next.delete("ate");
  if (sanitized.ate) next.set("ate", sanitized.ate);

  for (const key of MULTI_KEYS) {
    next.delete(key);
    for (const value of sanitized[key]) next.append(key, value);
  }

  return next;
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

  const parsed = useMemo(() => parseLeadsFiltersDetailed(searchParams), [searchParams]);
  const filters = parsed.filters;

  // Self-heal: a malformed value survives the useMemo above as "dropped from
  // state", but the URL itself still carries it until we rewrite it — leave
  // it and the NEXT reload/share/bookmark re-triggers the exact same 422
  // storm. Runs once per distinct raw querystring (see `lastSanitizedRawSearch`).
  const setSearchParamsRef = useRef(setSearchParams);
  setSearchParamsRef.current = setSearchParams;

  useEffect(() => {
    if (parsed.invalidKeys.length === 0) return;

    const rawSearch = searchParams.toString();
    if (lastSanitizedRawSearch === rawSearch) return;
    lastSanitizedRawSearch = rawSearch;

    const clean = scrubInvalidParams(searchParams, parsed.filters);
    setSearchParamsRef.current(clean, { replace: true });

    toast.warning("Alguns filtros do link eram inválidos e foram ignorados.");
  }, [parsed, searchParams]);

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
