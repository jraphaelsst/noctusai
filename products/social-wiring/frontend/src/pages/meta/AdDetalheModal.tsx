/**
 * AdDetalheModal — one AD's own live Meta metrics, opened by clicking an
 * ad row in AdsCampanhas. Everything here is scoped to THAT ad's
 * `object_id` at `level="ad"` — never the campaign's or ad-set's numbers —
 * because `/insights/*` for level="ad" always pulls LIVE from Meta
 * server-side (never a persisted snapshot), so what's shown is the ad's
 * own current investment + performance, not a rollup.
 *
 * Consumes the product's canonical Radix Dialog (`@/components/ui/dialog`,
 * the same organ every other social-wiring modal — ConnectionDetailDialog,
 * MarcaModal, etc. — is built on) rather than re-implementing a modal
 * shell.
 *
 * Leads are summed client-side via `rowLeads()` over the `/insights/series`
 * rows (current AND the preceding equal window, for the Δ%) rather than
 * read off `/insights/compare`'s `current.leads`/`previous.leads` — the
 * backend's `_sum_totals` only counts `actions["lead"]`, so an account
 * using `onsite_conversion.lead` (this one does, per `rowLeads`'s own
 * doc-comment) would under-report leads and Custo/lead here. Spend /
 * impressions / reach / clicks come straight off `/insights/compare`,
 * which already computes those four deltas server-side.
 */
import { useMemo } from "react";
import { DollarSign, Eye, Loader2, MousePointerClick, Target, Users } from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { MetricCard } from "@/components/MetricCard";
import { formatCents, formatDelta } from "@/lib/formatCurrency";
import { formatNumber } from "@/lib/formatNumber";
import {
  useAdsInsightsCompare,
  useAdsInsightsSeries,
  type AdsObject,
} from "@/hooks/useMetaAds";
import {
  AdsError,
  DateRangeSelect,
  pct,
  rowLeads,
  statusVariant,
  useDateRange,
  type DateRange,
} from "./adsShared";

// ─── local helpers ───────────────────────────────────────────────────────

/** The equally-long window immediately preceding `range` — same shape as
 *  AdsVisaoGeral's local `prevRange` (not yet lifted to adsShared; N=2,
 *  triage-level recurrence per the DRY rule, flagged in the delivery
 *  note rather than formalized here to keep this change file-scoped). */
function prevRange(range: DateRange): DateRange {
  const since = new Date(range.since);
  const until = new Date(range.until);
  const days = Math.round((until.getTime() - since.getTime()) / 86_400_000) + 1;
  const prevUntil = new Date(since);
  prevUntil.setDate(since.getDate() - 1);
  const prevSince = new Date(prevUntil);
  prevSince.setDate(prevUntil.getDate() - (days - 1));
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  return { since: iso(prevSince), until: iso(prevUntil) };
}

function deltaHint(curr: number, prev: number): string | undefined {
  const d = formatDelta(pct(curr, prev));
  return d ? `${d.label} vs. período anterior` : undefined;
}

interface Tile {
  key: string;
  icon: typeof DollarSign;
  label: string;
  value: string;
  hint?: string;
}

const ZERO_TOTALS = { spend_cents: 0, impressions: 0, reach: 0, clicks: 0 };

function buildTiles(
  cur: { spend_cents: number; impressions: number; reach: number; clicks: number },
  previous: { spend_cents: number; impressions: number; reach: number; clicks: number },
  curLeads: number,
  prevLeads: number,
  currency: string,
): Tile[] {
  const cpl = curLeads > 0 ? Math.round(cur.spend_cents / curLeads) : null;
  const prevCpl = prevLeads > 0 ? Math.round(previous.spend_cents / prevLeads) : null;
  const cpc = cur.clicks > 0 ? Math.round(cur.spend_cents / cur.clicks) : null;
  const prevCpc = previous.clicks > 0 ? Math.round(previous.spend_cents / previous.clicks) : null;
  const cpm = cur.impressions > 0 ? Math.round((cur.spend_cents / cur.impressions) * 1000) : null;
  const prevCpm =
    previous.impressions > 0 ? Math.round((previous.spend_cents / previous.impressions) * 1000) : null;
  const ctr = cur.impressions > 0 ? (cur.clicks / cur.impressions) * 100 : null;
  const prevCtr = previous.impressions > 0 ? (previous.clicks / previous.impressions) * 100 : null;

  const tiles: Tile[] = [
    {
      key: "spend",
      icon: DollarSign,
      label: "Gasto",
      value: formatCents(cur.spend_cents, currency),
      hint: deltaHint(cur.spend_cents, previous.spend_cents),
    },
    {
      key: "impressions",
      icon: Eye,
      label: "Impressões",
      value: formatNumber(cur.impressions),
      hint: deltaHint(cur.impressions, previous.impressions),
    },
    {
      key: "reach",
      icon: Users,
      label: "Alcance",
      value: formatNumber(cur.reach),
      hint: deltaHint(cur.reach, previous.reach),
    },
    {
      key: "clicks",
      icon: MousePointerClick,
      label: "Cliques",
      value: formatNumber(cur.clicks),
      hint: deltaHint(cur.clicks, previous.clicks),
    },
    {
      key: "leads",
      icon: Target,
      label: "Leads",
      value: formatNumber(curLeads),
      hint: deltaHint(curLeads, prevLeads),
    },
  ];

  // Derived tiles — only when the underlying data makes them meaningful
  // (same "no dead tiles" precedent as seriesHasPurchaseValue/ROAS).
  if (cpl !== null) {
    tiles.push({
      key: "cpl",
      icon: DollarSign,
      label: "Custo/lead",
      value: formatCents(cpl, currency),
      hint: prevCpl !== null ? deltaHint(cpl, prevCpl) : undefined,
    });
  }
  if (cpc !== null) {
    tiles.push({
      key: "cpc",
      icon: DollarSign,
      label: "Custo por clique",
      value: formatCents(cpc, currency),
      hint: prevCpc !== null ? deltaHint(cpc, prevCpc) : undefined,
    });
  }
  if (cpm !== null) {
    tiles.push({
      key: "cpm",
      icon: DollarSign,
      label: "CPM",
      value: formatCents(cpm, currency),
      hint: prevCpm !== null ? deltaHint(cpm, prevCpm) : undefined,
    });
  }
  if (ctr !== null) {
    tiles.push({
      key: "ctr",
      icon: MousePointerClick,
      label: "CTR",
      value: `${ctr.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`,
      hint: prevCtr !== null ? deltaHint(ctr, prevCtr) : undefined,
    });
  }

  return tiles;
}

// ─── component ───────────────────────────────────────────────────────────

export function AdDetalheModal({
  ad,
  currency,
  onClose,
}: {
  ad: AdsObject;
  currency: string;
  onClose: () => void;
}) {
  const { preset, setPreset, range } = useDateRange("28d");
  const prev = useMemo(() => prevRange(range), [range]);

  const compareQ = useAdsInsightsCompare(ad.object_id, "ad", range.since, range.until);
  const seriesQ = useAdsInsightsSeries(ad.object_id, "ad", range.since, range.until);
  const prevSeriesQ = useAdsInsightsSeries(ad.object_id, "ad", prev.since, prev.until);

  // Two signals, never a bare `isFetching` reaching a render gate. The OLD
  // `isPending || isFetching` here was Mode B: TRUE on every background
  // refetch (switching the date-range preset re-fetches all three
  // queries), so `loadingChart` unmounted the chart to "Carregando…" and
  // `loadingKpis` blanked every KPI tile to "—" on every preset change —
  // even though the previous numbers were still valid to show.
  // `showSkeleton*` gates on `!data` DIRECTLY (not `isPending && !data`) —
  // "nothing to render yet" IS "no data," full stop, and this stays
  // correct even in the defensive case where a query's `data` has been
  // cleared without `isPending` having flipped back (a key-change with no
  // `placeholderData`, or a reset mid-refetch). It can never mask real
  // data: `!data` is false the instant data exists, refetch or not.
  // `isRefreshing*` is an indicator only, never an early return / ternary
  // unmount. → KB § PATTERNS/frontend/lying-loading-state.md
  const showSkeletonKpis = !compareQ.data || !prevSeriesQ.data;
  const isRefreshingKpis =
    (compareQ.isFetching && !!compareQ.data) || (prevSeriesQ.isFetching && !!prevSeriesQ.data);
  // `&& !seriesQ.isError` — the ternary below checks the skeleton BEFORE
  // `seriesQ.isError` (mirrors the original branch order), so a resolved
  // error with no data must not be swallowed by the skeleton branch.
  const showSkeletonChart = !seriesQ.data && !seriesQ.isError;
  const isRefreshingChart = seriesQ.isFetching && !!seriesQ.data;
  const isRefreshing = isRefreshingKpis || isRefreshingChart;

  const curLeads = useMemo(
    () => (seriesQ.data?.rows ?? []).reduce((sum, r) => sum + rowLeads(r), 0),
    [seriesQ.data],
  );
  const prevLeads = useMemo(
    () => (prevSeriesQ.data?.rows ?? []).reduce((sum, r) => sum + rowLeads(r), 0),
    [prevSeriesQ.data],
  );

  const cur = compareQ.data?.current ?? ZERO_TOTALS;
  const previous = compareQ.data?.previous ?? ZERO_TOTALS;
  const tiles = useMemo(
    () => buildTiles(cur, previous, curLeads, prevLeads, currency),
    [cur, previous, curLeads, prevLeads, currency],
  );

  const chartData = useMemo(
    () =>
      (seriesQ.data?.rows ?? []).map((r) => ({
        date: r.date.slice(5),
        spend: (r.spend_cents ?? 0) / 100,
      })),
    [seriesQ.data],
  );

  const sv = statusVariant(ad.effective_status);

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <div className="flex items-center gap-3">
            {ad.creative_thumbnail_url && (
              <img
                src={ad.creative_thumbnail_url}
                alt=""
                className="h-12 w-12 shrink-0 rounded object-cover"
              />
            )}
            <div className="min-w-0">
              <DialogTitle className="truncate">{ad.name ?? ad.object_id}</DialogTitle>
              <div className="mt-1 flex items-center gap-2">
                <Badge variant="outline" className={sv.cls}>{sv.label}</Badge>
                <span className="truncate text-xs text-muted-foreground">{ad.object_id}</span>
              </div>
            </div>
          </div>
          <DialogDescription>
            Investimento e desempenho deste anúncio, direto do Meta.
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center justify-end gap-2">
          {isRefreshing && (
            <Loader2
              className="h-3.5 w-3.5 animate-spin text-muted-foreground"
              data-testid="ad-detalhe-refreshing"
            />
          )}
          <DateRangeSelect preset={preset} onChange={setPreset} />
        </div>

        {compareQ.isError ? (
          <AdsError
            message="Não foi possível carregar as métricas deste anúncio (limite do Meta?)."
            onRetry={() => compareQ.refetch()}
          />
        ) : (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
            {tiles.map((t) => (
              <MetricCard
                key={t.key}
                icon={t.icon}
                label={t.label}
                value={t.value}
                hint={t.hint}
                loading={showSkeletonKpis}
              />
            ))}
          </div>
        )}

        <div>
          <h3 className="mb-2 text-sm font-medium">Gasto ao longo do tempo</h3>
          {showSkeletonChart ? (
            <div className="flex h-56 items-center justify-center text-sm text-muted-foreground">
              Carregando…
            </div>
          ) : seriesQ.isError ? (
            <AdsError
              message="Não foi possível carregar a série deste anúncio."
              onRetry={() => seriesQ.refetch()}
            />
          ) : !chartData.length ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Nenhum dado no período.
            </p>
          ) : (
            <div className="h-56 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="date" fontSize={11} tickMargin={8} />
                  <YAxis
                    fontSize={11}
                    width={64}
                    tickFormatter={(v) => formatCents(Math.round(v * 100), currency)}
                  />
                  <Tooltip
                    formatter={(v: number) => formatCents(Math.round(v * 100), currency)}
                    labelFormatter={(l) => `Dia ${l}`}
                  />
                  <Line
                    type="monotone"
                    dataKey="spend"
                    stroke="hsl(var(--primary))"
                    strokeWidth={2}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
