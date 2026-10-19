/**
 * useSimec — TanStack Query wrappers for the SIMEC API (`/api/simec/*`).
 *
 * Contract: products/social-wiring/projects/marketing-intelligence/specs/simec-api-contract.md
 *
 * Loading signals are computed HERE, off `data`, never `isLoading`:
 *   showSkeleton = isPending && !data      (first load only)
 *   isRefreshing = isFetching && !!data    (indicator only, never an early return)
 * → KB § PATTERNS/frontend/lying-loading-state.md
 *
 * `GET` never recomputes a readout; `POST …/readouts` does (and stores it).
 */
import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import type {
  Overrides,
  SimecAccountsResponse,
  SimecConfigResponse,
  SimecReadout,
  SimecReadoutSummary,
} from "@/lib/simec";

export const SIMEC_PLATFORM = "instagram";

const FAMILY = ["sw", "simec"] as const;
export const simecKeys = {
  all: FAMILY,
  accounts: () => [...FAMILY, "accounts"] as const,
  defaults: () => [...FAMILY, "config", "defaults"] as const,
  config: (accountId: string | null) => [...FAMILY, "config", "effective", accountId] as const,
  configFamily: () => [...FAMILY, "config"] as const,
  latest: (accountId: string | null) => [...FAMILY, "latest", accountId] as const,
  readouts: (accountId: string | null, limit: number) => [...FAMILY, "readouts", accountId, limit] as const,
  readout: (id: string | null) => [...FAMILY, "readout", id] as const,
};

export type WithSignals<T> = UseQueryResult<T> & { showSkeleton: boolean; isRefreshing: boolean };

function withSignals<T>(q: UseQueryResult<T>): WithSignals<T> {
  return Object.assign(q, {
    showSkeleton: q.isPending && !q.data,
    isRefreshing: q.isFetching && !!q.data,
  });
}

// ─── Reads ──────────────────────────────────────────────────────────────────

export function useSimecAccounts(): WithSignals<SimecAccountsResponse> {
  return withSignals(
    useQuery<SimecAccountsResponse>({
      queryKey: simecKeys.accounts(),
      queryFn: () => api.get<SimecAccountsResponse>("/api/simec/accounts"),
    }),
  );
}

/** The seed's recommended defaults (no org layer) — the base the org layer edits over. */
export function useSimecDefaults(): WithSignals<SimecConfigResponse> {
  return withSignals(
    useQuery<SimecConfigResponse>({
      queryKey: simecKeys.defaults(),
      queryFn: () => api.get<SimecConfigResponse>(`/api/simec/config/defaults?platform=${SIMEC_PLATFORM}`),
      staleTime: 5 * 60_000,
    }),
  );
}

/**
 * Effective config (defaults ⊕ org [⊕ profile when `accountId`]). Key-change
 * query → `placeholderData: prev`: config is org methodology, not personal
 * data, so keeping the previous one painted during a profile switch is safe;
 * `isPlaceholderData` is exposed so editors can stay disabled until it lands.
 */
export function useSimecConfig(accountId: string | null): WithSignals<SimecConfigResponse> {
  return withSignals(
    useQuery<SimecConfigResponse>({
      queryKey: simecKeys.config(accountId),
      queryFn: () => {
        const qs = new URLSearchParams({ platform: SIMEC_PLATFORM });
        if (accountId) qs.set("account_id", accountId);
        return api.get<SimecConfigResponse>(`/api/simec/config?${qs.toString()}`);
      },
      placeholderData: (prev) => prev,
    }),
  );
}

// No `placeholderData: prev` on the readout queries below: every key embeds a
// profile id and a readout carries that profile's posts (captions, permalinks,
// numbers). Painting profile A's readout under profile B's selector during the
// switch would attribute A's numbers to B — the exact traceability failure
// SIMEC rule 1 forbids. The skeleton shows instead.

export function useSimecLatestReadout(accountId: string | null): WithSignals<{ readout: SimecReadout | null }> {
  return withSignals(
    useQuery<{ readout: SimecReadout | null }>({
      queryKey: simecKeys.latest(accountId),
      queryFn: () =>
        api.get<{ readout: SimecReadout | null }>(`/api/simec/accounts/${accountId}/readouts/latest`),
      enabled: !!accountId,
    }),
  );
}

export function useSimecReadouts(accountId: string | null, limit = 20): WithSignals<{ items: SimecReadoutSummary[] }> {
  return withSignals(
    useQuery<{ items: SimecReadoutSummary[] }>({
      queryKey: simecKeys.readouts(accountId, limit),
      queryFn: () =>
        api.get<{ items: SimecReadoutSummary[] }>(`/api/simec/accounts/${accountId}/readouts?limit=${limit}`),
      enabled: !!accountId,
    }),
  );
}

export function useSimecReadout(readoutId: string | null): WithSignals<SimecReadout> {
  return withSignals(
    useQuery<SimecReadout>({
      queryKey: simecKeys.readout(readoutId),
      queryFn: () => api.get<SimecReadout>(`/api/simec/readouts/${readoutId}`),
      enabled: !!readoutId,
    }),
  );
}

// ─── Writes ─────────────────────────────────────────────────────────────────

export interface ComputeReadoutInput {
  cadence?: string;
  period_start?: string;
  period_end?: string;
}

/** POST …/readouts → 201 full readout; it becomes the profile's latest. */
export function useComputeSimecReadout(accountId: string | null) {
  const qc = useQueryClient();
  return useMutation<SimecReadout, unknown, ComputeReadoutInput>({
    mutationFn: (body) => api.post<SimecReadout>(`/api/simec/accounts/${accountId}/readouts`, body ?? {}),
    onSuccess: (readout) => {
      qc.setQueryData(simecKeys.latest(accountId), { readout });
      qc.setQueryData(simecKeys.readout(readout.id), readout);
      qc.invalidateQueries({ queryKey: simecKeys.accounts() });
      qc.invalidateQueries({ queryKey: [...FAMILY, "readouts", accountId] });
    },
  });
}

export interface SaveSimecConfigInput {
  /** `null` = the org layer; an id = that profile's layer. */
  accountId: string | null;
  /** The WHOLE layer (PUT replaces it). `{}` = no overrides. */
  overrides: Overrides;
}

/** PUT /config/org or /accounts/{id}/config (owner/admin; 403 otherwise). */
export function useSaveSimecConfig() {
  const qc = useQueryClient();
  return useMutation<SimecConfigResponse, unknown, SaveSimecConfigInput>({
    mutationFn: ({ accountId, overrides }) =>
      api.put<SimecConfigResponse>(
        accountId ? `/api/simec/accounts/${accountId}/config` : "/api/simec/config/org",
        { platform: SIMEC_PLATFORM, overrides },
      ),
    onSuccess: (res, { accountId }) => {
      qc.setQueryData(simecKeys.config(accountId), res);
      // An org-layer change moves every profile's effective config.
      qc.invalidateQueries({ queryKey: simecKeys.configFamily() });
    },
  });
}
