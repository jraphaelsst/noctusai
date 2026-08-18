/**
 * Grupo OLX portal-lead hooks — TanStack Query over `/api/portals/olx`.
 *
 * The card these feed is an operational health panel, not a data table:
 * what it has to answer is "are OLX leads actually arriving, and is any
 * of them stuck?". `unresolved` is the status that matters most — it
 * means a real enquiry arrived and we could not tell which client it
 * belongs to, so it is sitting in the inbox waiting for a human rather
 * than being guessed into someone's CRM.
 *
 * 🔴 Loading is gated on `isPending || isFetching`, never `isLoading`.
 * Under TanStack v5 `isLoading` is false during a background refetch, so
 * an `isEmpty` branch renders "no deliveries yet" over deliveries that
 * exist — which here would read as "the integration is dead" at exactly
 * the moment it is working. Keeper: `check_lying_loading_state`.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

const BASE = "/api/portals/olx";

export const OLX_FAMILY_KEY = ["portals", "olx"] as const;
export const OLX_EVENTS_KEY = [...OLX_FAMILY_KEY, "events"] as const;

/** Mirrors `olx_lead_events.status` (migration 051's CHECK constraint). */
export type OlxEventStatus =
  | "received"
  | "processed"
  | "error"
  | "unresolved"
  | "ignored";

export interface OlxLeadEvent {
  id: string;
  org_id: string | null;
  client_listing_id: string | null;
  lead_origin: string | null;
  lead_type: string | null;
  status: OlxEventStatus;
  error: string | null;
  attempts: number;
  received_at: string;
  processed_at: string | null;
}

export interface OlxEventsResponse {
  events: OlxLeadEvent[];
  counts: Partial<Record<OlxEventStatus, number>>;
}

export interface OlxBackfillResult {
  ingested: number;
  skipped_existing: number;
  errors: Array<{ origin_lead_id: string | null; error: string }>;
}

export function useOlxEvents(limit = 50) {
  const query = useQuery({
    queryKey: [...OLX_EVENTS_KEY, limit],
    queryFn: async () => {
      const res = await api.get<OlxEventsResponse>(
        `${BASE}/events?limit=${encodeURIComponent(String(limit))}`,
      );
      return res;
    },
  });

  // Derived once here rather than in the component, so every consumer
  // agrees on what "stuck" means.
  const events = query.data?.events ?? [];
  const counts = query.data?.counts ?? {};
  const stuck = events.filter(
    (event) => event.status === "unresolved" || event.status === "error",
  );

  return {
    ...query,
    events,
    counts,
    stuck,
    /** See the module header — NOT `isLoading`. */
    loading: query.isPending || query.isFetching,
    isEmpty: !query.isPending && !query.isFetching && events.length === 0,
  };
}

export function useOlxBackfill() {
  const qc = useQueryClient();
  return useMutation<OlxBackfillResult, unknown, void>({
    mutationFn: () => api.post<OlxBackfillResult>(`${BASE}/backfill`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: OLX_FAMILY_KEY });
      // The projection writes into `leads`, so that family is stale too.
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}
