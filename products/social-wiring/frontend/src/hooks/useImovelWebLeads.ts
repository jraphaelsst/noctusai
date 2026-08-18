/**
 * ImovelWeb / OpenNavent portal-lead hooks — TanStack Query over
 * `/api/portals/imovelweb`.
 *
 * A different vendor from Grupo OLX despite the overlapping portal names,
 * and the card these feed has one job the OLX card does not: showing the
 * **callback registration**. That configuration is integrator-wide, so a
 * wrong URL or an empty subscription list stops every agency's leads at
 * once — and neither failure produces an error anywhere. The vendor
 * believes it delivered; we simply stop receiving.
 *
 * So three things are derived here rather than in the component, so every
 * consumer agrees on what they mean:
 *
 *   • `stuck` — `unresolved` / `error`. A real enquiry arrived and nobody
 *     has been told about it.
 *   • `deliversNothing` — registered, but subscribed to no events. Legal
 *     to the vendor, useless to us, and invisible to everything else.
 *   • `reconcileShare` — the fraction of recent deliveries we had to PULL
 *     rather than receive. The vendor allows 1.5 seconds to answer; a
 *     rising share here is the operator-visible symptom of missing that
 *     budget, because the leads still arrive, just by the slow path.
 *
 * 🔴 Loading is gated on `isPending || isFetching`, never `isLoading`.
 * Under TanStack v5 `isLoading` is false during a background refetch, so
 * an `isEmpty` branch renders "no deliveries yet" over deliveries that
 * exist — which here reads as "the integration is dead" at exactly the
 * moment it is working. Keeper: `check_lying_loading_state`.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

const BASE = "/api/portals/imovelweb";

export const IMOVELWEB_FAMILY_KEY = ["portals", "imovelweb"] as const;
export const IMOVELWEB_EVENTS_KEY = [...IMOVELWEB_FAMILY_KEY, "events"] as const;
export const IMOVELWEB_CALLBACK_KEY = [...IMOVELWEB_FAMILY_KEY, "callback"] as const;

/** Mirrors `imovelweb_lead_events.status` (migration 052's CHECK). */
export type ImovelWebEventStatus =
  | "received"
  | "processed"
  | "error"
  | "unresolved"
  | "ignored";

/** How a delivery reached us. `reconcile` means the callback missed it. */
export type ImovelWebEventSource = "callback" | "reconcile";

export interface ImovelWebLeadEvent {
  id: string;
  org_id: string | null;
  event_type: string | null;
  codigo_imobiliaria: string | null;
  client_listing_id: string | null;
  lead_origin: string | null;
  callback_language: string | null;
  source: ImovelWebEventSource;
  status: ImovelWebEventStatus;
  error: string | null;
  attempts: number;
  received_at: string;
  processed_at: string | null;
  // NOTE: `payload` is deliberately absent from this type AND from the
  // API response. It is the lossless vendor body and can contain a CPF.
}

export interface ImovelWebEventsResponse {
  events: ImovelWebLeadEvent[];
  counts: Partial<Record<ImovelWebEventStatus, number>>;
  bySource: Record<ImovelWebEventSource, number>;
}

export interface ImovelWebCallbackConfig {
  url: string;
  authorizationHeaderKey: string;
  /** Always the literal `***REDACTED***` — that header IS the auth. */
  authorizationHeaderValue: string;
  lenguajeCallbackBody: string;
  subscriptions: string[];
}

export interface ImovelWebCallbackResponse {
  config: ImovelWebCallbackConfig | null;
  subscriptions: string[];
  delivers_nothing: boolean;
  problems: string[];
  error?: string;
}

export interface ImovelWebRegisterResult {
  registered: boolean;
  requested: ImovelWebCallbackConfig | null;
  previous: ImovelWebCallbackConfig | null;
  applied: ImovelWebCallbackConfig | null;
  drift: string[];
  warnings: string[];
  error?: string;
}

export interface ImovelWebBackfillResult {
  ingested: number;
  skipped_existing: number;
  errors: Array<{ event_id: string | null; error: string }>;
}

export interface ImovelWebReconcileResult {
  agencies: number;
  recovered: number;
  results: Array<Record<string, unknown>>;
}

export function useImovelWebEvents(limit = 50) {
  const query = useQuery({
    queryKey: [...IMOVELWEB_EVENTS_KEY, limit],
    queryFn: () =>
      api.get<ImovelWebEventsResponse>(
        `${BASE}/events?limit=${encodeURIComponent(String(limit))}`,
      ),
  });

  const events = query.data?.events ?? [];
  const counts = query.data?.counts ?? {};
  const bySource = query.data?.bySource ?? { callback: 0, reconcile: 0 };
  const stuck = events.filter(
    (event) => event.status === "unresolved" || event.status === "error",
  );

  const delivered = (bySource.callback ?? 0) + (bySource.reconcile ?? 0);
  // Zero deliveries is NOT a zero share — it is no data. Reporting 0%
  // would read as "the fast path is working" when nothing has arrived.
  const reconcileShare = delivered > 0 ? (bySource.reconcile ?? 0) / delivered : null;

  return {
    ...query,
    events,
    counts,
    bySource,
    stuck,
    reconcileShare,
    /** See the module header — NOT `isLoading`. */
    loading: query.isPending || query.isFetching,
    isEmpty: !query.isPending && !query.isFetching && events.length === 0,
  };
}

export function useImovelWebCallbackConfig() {
  const query = useQuery({
    queryKey: IMOVELWEB_CALLBACK_KEY,
    queryFn: () => api.get<ImovelWebCallbackResponse>(`${BASE}/callback`),
    // The vendor is upstream of us and may simply be unreachable; a failed
    // read here is a normal state to display, not something to hammer.
    retry: false,
  });

  const config = query.data?.config ?? null;
  const subscriptions = query.data?.subscriptions ?? [];

  return {
    ...query,
    config,
    subscriptions,
    /** Registered, subscribed to nothing: silent, and the likeliest fault. */
    deliversNothing: query.data?.delivers_nothing ?? false,
    problems: query.data?.problems ?? [],
    /** Nothing registered at all — distinct from "registered but empty". */
    isUnregistered: !!query.data && !config?.url,
    loading: query.isPending || query.isFetching,
  };
}

export function useRegisterImovelWebCallback() {
  const qc = useQueryClient();
  return useMutation<
    ImovelWebRegisterResult,
    unknown,
    { publicBaseUrl?: string; language?: string; events?: string[] }
  >({
    // `confirm` is sent by the hook rather than by the caller: the backend
    // requires it, and a component that had to remember it would
    // eventually forget. The confirmation the USER gives is the dialog.
    mutationFn: (vars) =>
      api.post<ImovelWebRegisterResult>(`${BASE}/callback/register`, {
        ...vars,
        confirm: true,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: IMOVELWEB_CALLBACK_KEY });
    },
  });
}

export function useImovelWebBackfill() {
  const qc = useQueryClient();
  return useMutation<ImovelWebBackfillResult, unknown, void>({
    mutationFn: () => api.post<ImovelWebBackfillResult>(`${BASE}/backfill`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: IMOVELWEB_FAMILY_KEY });
      // The projection writes into `leads`, so that family is stale too.
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}

export function useImovelWebReconcile() {
  const qc = useQueryClient();
  return useMutation<ImovelWebReconcileResult, unknown, void>({
    mutationFn: () => api.post<ImovelWebReconcileResult>(`${BASE}/reconcile`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: IMOVELWEB_FAMILY_KEY });
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}
