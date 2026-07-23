/**
 * Shared building blocks for the Anúncios (Meta Ads) console subtabs —
 * date-range control, not-configured/empty/error state guards, the
 * objective-aware KPI model, and client-side account-period aggregation.
 *
 * NOTE on the aggregation: the `/api/meta/ads/*` contract is object-scoped
 * (campaign/adset/ad) — there is NO account-level insights aggregate
 * endpoint. So an account overview sums each campaign's `/insights/series`
 * for the window client-side (via `useAccountPeriodTotals`). Flagged as a
 * backend follow-up (an `/insights/account` aggregate would remove the N
 * fan-out); until then this is correct, just chattier.
 */
import { useMemo, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { CircleAlert, Loader2, SlidersHorizontal } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type {
  AdsActivity,
  AdsCampaign,
  AdsInsightsRow,
  AdsInsightsSeries,
} from "@/hooks/useMetaAds";

// ─── activity change-log label ──────────────────────────────────────────────

const EVENT_LABELS: Record<string, string> = {
  update_ad_run_status: "Status alterado",
  ad_account_billing_charge: "Cobrança",
  update_campaign_budget: "Orçamento alterado",
  update_ad_set_budget: "Orçamento do conjunto alterado",
  first_delivery_event: "Primeira veiculação",
  create_campaign: "Campanha criada",
  update_campaign_run_status: "Status da campanha alterado",
};

/** Human, pt-BR label for a change-log event (old → new, actor). */
export function activityLabel(a: AdsActivity): string {
  const base = EVENT_LABELS[a.event_type ?? ""] ?? a.event_type ?? "Mudança";
  const change =
    a.old_value && a.new_value ? `: ${a.old_value} → ${a.new_value}` : "";
  const who = a.actor_name ? ` (${a.actor_name})` : "";
  return `${base}${change}${who}`;
}

// ─── Date range ─────────────────────────────────────────────────────────────

export type RangePreset = "7d" | "28d" | "this_month" | "last_month";

export interface DateRange {
  since: string; // YYYY-MM-DD
  until: string; // YYYY-MM-DD
}

function iso(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function rangeForPreset(preset: RangePreset, now = new Date()): DateRange {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  if (preset === "7d") {
    const since = new Date(today);
    since.setDate(today.getDate() - 6);
    return { since: iso(since), until: iso(today) };
  }
  if (preset === "28d") {
    const since = new Date(today);
    since.setDate(today.getDate() - 27);
    return { since: iso(since), until: iso(today) };
  }
  if (preset === "this_month") {
    const since = new Date(today.getFullYear(), today.getMonth(), 1);
    return { since: iso(since), until: iso(today) };
  }
  // last_month
  const firstThis = new Date(today.getFullYear(), today.getMonth(), 1);
  const lastPrevEnd = new Date(firstThis);
  lastPrevEnd.setDate(0); // last day of previous month
  const lastPrevStart = new Date(lastPrevEnd.getFullYear(), lastPrevEnd.getMonth(), 1);
  return { since: iso(lastPrevStart), until: iso(lastPrevEnd) };
}

const PRESET_LABELS: Record<RangePreset, string> = {
  "7d": "Últimos 7 dias",
  "28d": "Últimos 28 dias",
  this_month: "Este mês",
  last_month: "Mês passado",
};

export function useDateRange(initial: RangePreset = "28d") {
  const [preset, setPreset] = useState<RangePreset>(initial);
  const range = useMemo(() => rangeForPreset(preset), [preset]);
  return { preset, setPreset, range };
}

export function DateRangeSelect({
  preset,
  onChange,
}: {
  preset: RangePreset;
  onChange: (p: RangePreset) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <SlidersHorizontal className="h-4 w-4 text-muted-foreground" />
      <Select value={preset} onValueChange={(v) => onChange(v as RangePreset)}>
        <SelectTrigger className="w-[180px]">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {(Object.keys(PRESET_LABELS) as RangePreset[]).map((p) => (
            <SelectItem key={p} value={p}>
              {PRESET_LABELS[p]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

// ─── State guards (never a zeros dashboard) ─────────────────────────────────

export function AdsLoading({ label = "Carregando…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
      <Loader2 className="h-5 w-5 animate-spin" />
      <span className="text-sm">{label}</span>
    </div>
  );
}

export function AdsNotConfigured({ detail }: { detail?: string | null }) {
  return (
    <Card className="border-dashed">
      <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
        <CircleAlert className="h-8 w-8 text-muted-foreground" />
        <div className="text-lg font-medium">Anúncios não configurado</div>
        <p className="max-w-md text-sm text-muted-foreground">
          {detail ??
            "Nenhuma conta de anúncios do Meta está conectada. Configure o token de Usuário do Sistema e a conta de anúncios (META_AD_ACCOUNT_ID) para ver suas campanhas aqui."}
        </p>
      </CardContent>
    </Card>
  );
}

export function AdsError({
  message,
  onRetry,
}: {
  message?: string | null;
  onRetry?: () => void;
}) {
  return (
    <Card className="border-destructive/40">
      <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
        <CircleAlert className="h-7 w-7 text-destructive" />
        <div className="font-medium">Não foi possível carregar os anúncios</div>
        <p className="max-w-md text-sm text-muted-foreground">
          {message ??
            "O Meta retornou um erro (possível limite de requisições). Tente novamente em alguns minutos."}
        </p>
        {onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            Tentar de novo
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

// ─── actions helpers ────────────────────────────────────────────────────────

/** Leads for a row — Meta's `actions["lead"]` (this account is lead-gen). */
export function rowLeads(row: AdsInsightsRow): number {
  return row.actions?.["lead"] ?? row.actions?.["onsite_conversion.lead"] ?? 0;
}

export function rowAction(row: AdsInsightsRow, key: string): number {
  return row.actions?.[key] ?? 0;
}

/** True when ANY row carries a purchase value → a ROAS tile is meaningful.
 *  On the pilot (lead-gen) account this is always false, so no dead ROAS. */
export function seriesHasPurchaseValue(rows: AdsInsightsRow[]): boolean {
  return rows.some((r) => Object.keys(r.action_values ?? {}).length > 0);
}

// ─── Objective-aware KPI model ──────────────────────────────────────────────

export type Objective =
  | "OUTCOME_LEADS"
  | "OUTCOME_TRAFFIC"
  | "OUTCOME_ENGAGEMENT"
  | "OUTCOME_AWARENESS"
  | "OUTCOME_SALES"
  | string;

/** The dominant objective across campaigns (most frequent). Drives which
 *  objective-specific KPI tiles the overview renders. */
export function dominantObjective(campaigns: AdsCampaign[]): Objective | null {
  const counts = new Map<string, number>();
  for (const c of campaigns) {
    if (!c.objective) continue;
    counts.set(c.objective, (counts.get(c.objective) ?? 0) + 1);
  }
  let best: string | null = null;
  let bestN = 0;
  for (const [obj, n] of counts) {
    if (n > bestN) {
      best = obj;
      bestN = n;
    }
  }
  return best;
}

// ─── Client-side account-period aggregation ─────────────────────────────────

export interface PeriodTotals {
  spend_cents: number;
  impressions: number;
  reach: number;
  clicks: number;
  leads: number;
  link_clicks: number;
  landing_page_views: number;
  messaging_started: number;
  days: number;
  rows: AdsInsightsRow[]; // merged daily rows (summed across campaigns)
}

function emptyTotals(): PeriodTotals {
  return {
    spend_cents: 0,
    impressions: 0,
    reach: 0,
    clicks: 0,
    leads: 0,
    link_clicks: 0,
    landing_page_views: 0,
    messaging_started: 0,
    days: 0,
    rows: [],
  };
}

/**
 * Sum every campaign's series for the window into one account-level total,
 * plus a merged per-day series (rows summed by date) for the overview
 * spend chart. Runs one query per campaign (see file header note).
 */
export function useAccountPeriodTotals(
  campaigns: AdsCampaign[],
  range: DateRange,
) {
  const queries = useQueries({
    queries: campaigns.map((c) => ({
      queryKey: [
        "meta-ads",
        "series",
        c.object_id,
        "campaign",
        range.since,
        range.until,
        "",
      ] as const,
      queryFn: () =>
        api.get<AdsInsightsSeries>(
          `/api/meta/ads/insights/series?object_id=${encodeURIComponent(
            c.object_id,
          )}&level=campaign&since=${range.since}&until=${range.until}`,
        ),
      enabled: !!c.object_id && !!range.since && !!range.until,
    })),
  });

  const isPending = queries.some((q) => q.isPending || q.isFetching);
  const isError = queries.some((q) => q.isError);

  const totals = useMemo(() => {
    const t = emptyTotals();
    const byDate = new Map<string, AdsInsightsRow>();
    for (const q of queries) {
      const rows = q.data?.rows ?? [];
      for (const r of rows) {
        t.spend_cents += r.spend_cents ?? 0;
        t.impressions += r.impressions ?? 0;
        t.reach += r.reach ?? 0;
        t.clicks += r.clicks ?? 0;
        t.leads += rowLeads(r);
        t.link_clicks += rowAction(r, "link_click");
        t.landing_page_views += rowAction(r, "landing_page_view");
        t.messaging_started += rowAction(
          r,
          "onsite_conversion.messaging_conversation_started_7d",
        );
        const acc = byDate.get(r.date);
        if (acc) {
          acc.spend_cents = (acc.spend_cents ?? 0) + (r.spend_cents ?? 0);
          acc.impressions = (acc.impressions ?? 0) + (r.impressions ?? 0);
          acc.reach = (acc.reach ?? 0) + (r.reach ?? 0);
          acc.clicks = (acc.clicks ?? 0) + (r.clicks ?? 0);
        } else {
          byDate.set(r.date, { ...r });
        }
      }
    }
    t.rows = Array.from(byDate.values()).sort((a, b) =>
      a.date.localeCompare(b.date),
    );
    t.days = t.rows.length;
    return t;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queries.map((q) => q.dataUpdatedAt).join(","), range.since, range.until]);

  return { totals, isPending, isError };
}
