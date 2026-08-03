/**
 * Meta Lead-Ads WEBHOOK management hooks — TanStack Query wrappers over the
 * `/api/meta/leadgen/*` router (slice `meta-leadgen-ui`).
 *
 * Distinct from `useMetaAds`'s `/api/meta/ads/leads/*` (the forms/records
 * READ surface): this hook set drives the two-part SUBSCRIPTION handshake
 * that makes lead delivery happen at all —
 *
 *   1. App-level  — ticked in the Meta App Dashboard. No code can do this;
 *      `verify_token_configured` only reports whether OUR side of the GET
 *      handshake (`META_WEBHOOK_VERIFY_TOKEN`) is ready for that click.
 *   2. Page-level — `POST /{page_id}/subscribed_apps`, automated here.
 *
 * Either alone delivers NOTHING, silently — the whole card exists to make
 * that invisible failure visible.
 *
 * Responses are BARE typed models (`response_model=<Pydantic>` directly on
 * this router), NOT the `{data: ...}` envelope `useMetaAds` reads elsewhere
 * in this same product — do not wrap these in `.data`.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

// ─── Types (mirror leadgen_router.py's Out DTOs verbatim) ──────────────────

export interface LeadgenPageSubscription {
  page_id: string;
  page_name: string;
  subscribed: boolean;
  subscribed_fields: string[];
  app_id: string | null;
}

export interface LeadgenSubscriptions {
  pages: LeadgenPageSubscription[];
  callback_url: string;
  verify_token_configured: boolean;
  gated: boolean;
  reason: string | null;
}

export interface LeadgenSubscribeResult {
  page_id: string;
  ok: boolean;
  error: string | null;
}

export interface LeadgenSubscribeResponse {
  results: LeadgenSubscribeResult[];
}

export interface LeadgenEvent {
  id: string;
  page_id: string | null;
  form_id: string | null;
  status: string;
  error: string | null;
  received_at: string | null;
  processed_at: string | null;
}

export interface LeadgenEvents {
  counts: Record<string, number>;
  last_received_at: string | null;
  events: LeadgenEvent[];
}

// ─── Query keys ─────────────────────────────────────────────────────────────

const SUBSCRIPTIONS_KEY = ["meta-leadgen", "subscriptions"] as const;
const eventsKey = (limit: number) => ["meta-leadgen", "events", limit] as const;

// ─── Hooks ──────────────────────────────────────────────────────────────────

/** Which Pages are subscribed to `leadgen`, plus the callback URL + whether
 *  our side of the GET handshake is ready. Always resolves to a real
 *  object (never `undefined`) — an org with zero connected Pages still
 *  returns `{pages: [], ...}`. */
export function useLeadgenSubscriptions() {
  return useQuery<LeadgenSubscriptions>({
    queryKey: SUBSCRIPTIONS_KEY,
    queryFn: () =>
      api
        .get<LeadgenSubscriptions>("/api/meta/leadgen/subscriptions")
        .then(
          (r) =>
            r ?? {
              pages: [],
              callback_url: "",
              verify_token_configured: false,
              gated: false,
              reason: null,
            },
        ),
  });
}

/** Subscribe Pages to `leadgen`. `pageIds: null` ⇒ all Pages (the "Assinar
 *  todas as páginas" action); a single-element array ⇒ one Page's row
 *  button. Per-page results — the caller must render PARTIAL failure, never
 *  collapse it to a blanket success/error. Invalidates the subscriptions
 *  query so every row reflects the new state without a manual refetch. */
export function useSubscribeLeadgenPages() {
  const qc = useQueryClient();
  return useMutation<LeadgenSubscribeResponse, Error, string[] | null>({
    mutationFn: (pageIds) =>
      api
        .post<LeadgenSubscribeResponse>("/api/meta/leadgen/subscriptions", {
          page_ids: pageIds,
        })
        .then((r) => r ?? { results: [] }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SUBSCRIPTIONS_KEY });
    },
  });
}

/** Undo one Page's subscription. */
export function useUnsubscribeLeadgenPage() {
  const qc = useQueryClient();
  return useMutation<LeadgenSubscribeResult, Error, string>({
    mutationFn: (pageId) =>
      api
        .delete<LeadgenSubscribeResult>(
          `/api/meta/leadgen/subscriptions/${encodeURIComponent(pageId)}`,
        )
        .then(
          (r) =>
            r ?? {
              page_id: pageId,
              ok: false,
              error: "resposta vazia do servidor",
            },
        ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SUBSCRIPTIONS_KEY });
    },
  });
}

/** Delivery health — `last_received_at === null` is the most diagnostic
 *  state in the whole feature: Meta has NEVER called our webhook, i.e. the
 *  App-Dashboard half of the handshake isn't configured. Distinguishing
 *  that from "configured but no leads yet" is the entire point of this
 *  query. */
export function useLeadgenEvents(limit = 20) {
  return useQuery<LeadgenEvents>({
    queryKey: eventsKey(limit),
    queryFn: () =>
      api
        .get<LeadgenEvents>(`/api/meta/leadgen/events?limit=${limit}`)
        .then((r) => r ?? { counts: {}, last_received_at: null, events: [] }),
  });
}
