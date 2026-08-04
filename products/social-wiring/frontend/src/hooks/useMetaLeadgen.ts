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
import { useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { useRealtimeStream } from "@noctusai/lib";

import type { LeadRecord, LeadRecords } from "./useMetaAds";

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

// ─── Live delivery (SSE) ───────────────────────────────────────────────────

/**
 * The event vocabulary the leads stream emits. Mirrors
 * `app/services/meta_leads_realtime.py::META_LEAD_EVENTS`.
 *
 * 🔴 Passed to `useRealtimeStream` rather than appended to the seed's
 * defaults: `EventSource` only delivers a named event to a listener
 * registered for that exact name, and a seed constant that grows once per
 * product is a hand-maintained list nobody fails to update loudly.
 */
export const LEADGEN_EVENTS = ["lead.new"] as const;

/** The projection the server puts on the wire. Deliberately NOT the whole
 *  `meta_ads_leads` row — `answers`/`raw` are free-text PII the list never
 *  renders, so they are not broadcast to every open tab. */
export interface LiveLead {
  id: string;
  full_name: string | null;
  email: string | null;
  phone: string | null;
  form_id: string | null;
  form_name: string | null;
  campaign_name: string | null;
  platform: string | null;
  created_time: string | null;
}

/** Map the wire projection onto the `LeadRecord` shape the list renders, so
 *  a live-arrived lead is indistinguishable from a fetched one. The answer
 *  fields are absent by design (see `LiveLead`); a refetch fills them in. */
function toLeadRecord(lead: LiveLead): LeadRecord {
  return {
    id: lead.id,
    created_time: lead.created_time,
    ad_id: null,
    ad_name: null,
    campaign_id: null,
    campaign_name: lead.campaign_name,
    platform: lead.platform,
    is_organic: null,
    field_data: [
      ...(lead.full_name ? [{ name: "full_name", values: [lead.full_name] }] : []),
      ...(lead.email ? [{ name: "email", values: [lead.email] }] : []),
      ...(lead.phone ? [{ name: "phone_number", values: [lead.phone] }] : []),
    ],
  };
}

/**
 * Subscribe to this org's live lead stream and PREPEND arrivals into the
 * already-cached lead list.
 *
 * WHY `setQueryData` AND NOT `invalidateQueries`
 * ─────────────────────────────────────────────
 * An invalidate would trigger a refetch — reintroducing exactly the network
 * round trip this removes, and flashing the list's loading state on every
 * arrival. The requirement was a background update that adds the row to the
 * list, with no refresh and no polling; patching the cache in place is what
 * that means.
 *
 * Prepending (rather than appending) matches the list's newest-first order.
 * The de-dup guard is not optional: a resumed connection may redeliver an
 * event the client already applied, and the same lead can arrive twice if the
 * server retried a publish — the seed's own contract says to keep handlers
 * idempotent.
 *
 * Every cached `lead-records` page is patched, not just the visible one: the
 * key is per (formId, pageId), and a lead belongs to exactly one form. Rows
 * for other forms are left untouched.
 */
export function useLiveLeads(enabled = true) {
  const qc = useQueryClient();

  const onEvent = useCallback(
    (message: { event: string; payload: Record<string, unknown> }) => {
      if (message.event !== "lead.new") return;
      const lead = message.payload as unknown as LiveLead;
      if (!lead?.id) return;

      qc.setQueriesData<LeadRecords>(
        { queryKey: ["meta-ads", "lead-records"] },
        (prev) => {
          if (!prev) return prev;
          // Only the form this lead belongs to; an unknown form_id means the
          // list for it is not cached yet and will fetch fresh anyway.
          if (lead.form_id && prev.form_id && lead.form_id !== prev.form_id) {
            return prev;
          }
          if (prev.data.some((r) => r.id === lead.id)) return prev;
          return { ...prev, data: [toLeadRecord(lead), ...prev.data] };
        },
      );

      // The delivery-health panel counts arrivals; keep its badge honest
      // without refetching the list itself.
      qc.invalidateQueries({ queryKey: ["meta-leadgen", "events"] });
    },
    [qc],
  );

  return useRealtimeStream(enabled ? "/api/meta/leadgen/stream" : null, {
    onEvent,
    events: LEADGEN_EVENTS,
  });
}
