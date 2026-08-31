/**
 * AdsVisaoGeral — "Visão geral" subtab of the Anúncios (Meta Ads) network.
 *
 * Objective-aware KPI row: universal tiles always, plus objective-specific
 * tiles that swap on the account's dominant campaign objective — so a
 * lead-gen account leads with Leads + Custo por lead and NEVER shows a dead
 * ROAS tile (a ROAS tile appears only when purchase values exist, which on
 * this account they don't). Every tile shows Δ% vs. the preceding equal
 * window. Below: account totals + a spend-over-time chart.
 */
import { useMemo } from "react";
import {
  BarChart3,
  DollarSign,
  Eye,
  Loader2,
  MessagesSquare,
  MousePointerClick,
  RefreshCw,
  Target,
  TrendingDown,
  TrendingUp,
  Users,
} from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { MetricCard } from "@/components/MetricCard";
import { formatNumber } from "@/lib/formatNumber";
import { formatCents, formatDelta } from "@/lib/formatCurrency";
import {
  useAdsAccount,
  useAdsAccountInsights,
  useAdsCampaigns,
  useAdsSync,
  type AdsAccountInsights,
} from "@/hooks/useMetaAds";
import {
  AdsError,
  AdsLoading,
  AdsNotConfigured,
  DateRangeSelect,
  ExportButtons,
  SavedViewsControl,
  dominantObjective,
  useDateRange,
  type DateRange,
} from "./adsShared";

/** Normalized period totals the KPI builder consumes — derived from the
 *  account aggregate (totals + summed actions map). */
interface PeriodTotals {
  spend_cents: number;
  impressions: number;
  reach: number;
  clicks: number;
  leads: number;
  link_clicks: number;
  landing_page_views: number;
  messaging_started: number;
}

function normTotals(ins: AdsAccountInsights | undefined): PeriodTotals {
  const t = ins?.totals;
  const a = ins?.actions ?? {};
  return {
    spend_cents: t?.spend_cents ?? 0,
    impressions: t?.impressions ?? 0,
    reach: t?.reach ?? 0,
    clicks: t?.clicks ?? 0,
    leads: t?.leads ?? 0,
    link_clicks: a["link_click"] ?? 0,
    landing_page_views: a["landing_page_view"] ?? 0,
    messaging_started: a["onsite_conversion.messaging_conversation_started_7d"] ?? 0,
  };
}

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

function pct(curr: number, prev: number): number | null {
  if (!prev) return null;
  return ((curr - prev) / prev) * 100;
}

function deltaHint(curr: number, prev: number): string | undefined {
  const d = formatDelta(pct(curr, prev));
  return d ? `${d.label} vs. período anterior` : undefined;
}

interface Tile {
  key: string;
  icon: typeof BarChart3;
  label: string;
  value: string;
  hint?: string;
}

function buildTiles(
  objective: string | null,
  cur: PeriodTotals,
  prev: PeriodTotals,
  currency: string,
): Tile[] {
  const cpl = cur.leads > 0 ? Math.round(cur.spend_cents / cur.leads) : null;
  const prevCpl = prev.leads > 0 ? Math.round(prev.spend_cents / prev.leads) : null;
  const cpc = cur.link_clicks > 0 ? Math.round(cur.spend_cents / cur.link_clicks) : null;
  const cpm = cur.impressions > 0 ? Math.round((cur.spend_cents / cur.impressions) * 1000) : null;
  const costPerConv =
    cur.messaging_started > 0 ? Math.round(cur.spend_cents / cur.messaging_started) : null;

  // Universal tiles — always shown.
  const tiles: Tile[] = [
    {
      key: "spend",
      icon: DollarSign,
      label: "Gasto",
      value: formatCents(cur.spend_cents, currency),
      hint: deltaHint(cur.spend_cents, prev.spend_cents),
    },
    {
      key: "impressions",
      icon: Eye,
      label: "Impressões",
      value: formatNumber(cur.impressions),
      hint: deltaHint(cur.impressions, prev.impressions),
    },
    {
      key: "reach",
      icon: Users,
      label: "Alcance",
      value: formatNumber(cur.reach),
      hint: deltaHint(cur.reach, prev.reach),
    },
    {
      key: "cpm",
      icon: BarChart3,
      label: "CPM",
      value: cpm !== null ? formatCents(cpm, currency) : "—",
    },
  ];

  // Objective-specific tiles.
  if (objective === "OUTCOME_LEADS") {
    tiles.push(
      {
        key: "leads",
        icon: Target,
        label: "Leads",
        value: formatNumber(cur.leads),
        hint: deltaHint(cur.leads, prev.leads),
      },
      {
        key: "cpl",
        icon: DollarSign,
        label: "Custo por lead",
        value: cpl !== null ? formatCents(cpl, currency) : "—",
        hint:
          cpl !== null && prevCpl !== null
            ? deltaHint(cpl, prevCpl)
            : undefined,
      },
    );
  } else if (objective === "OUTCOME_TRAFFIC") {
    tiles.push(
      {
        key: "link_clicks",
        icon: MousePointerClick,
        label: "Cliques no link",
        value: formatNumber(cur.link_clicks),
        hint: deltaHint(cur.link_clicks, prev.link_clicks),
      },
      {
        key: "cpc",
        icon: DollarSign,
        label: "Custo por clique",
        value: cpc !== null ? formatCents(cpc, currency) : "—",
      },
    );
  } else if (objective === "OUTCOME_ENGAGEMENT") {
    tiles.push({
      key: "clicks",
      icon: MousePointerClick,
      label: "Cliques",
      value: formatNumber(cur.clicks),
      hint: deltaHint(cur.clicks, prev.clicks),
    });
  } else {
    tiles.push({
      key: "clicks",
      icon: MousePointerClick,
      label: "Cliques",
      value: formatNumber(cur.clicks),
      hint: deltaHint(cur.clicks, prev.clicks),
    });
  }

  // Messaging tile — always useful for this business (leads via DM).
  if (cur.messaging_started > 0) {
    tiles.push({
      key: "messaging",
      icon: MessagesSquare,
      label: "Conversas iniciadas",
      value: formatNumber(cur.messaging_started),
      hint:
        costPerConv !== null
          ? `${formatCents(costPerConv, currency)} por conversa`
          : undefined,
    });
  }

  return tiles;
}

function SpendChart({
  daily,
  currency,
}: {
  daily: AdsAccountInsights["daily"];
  currency: string;
}) {
  const data = useMemo(
    () =>
      daily.map((r) => ({
        date: r.date.slice(5), // MM-DD
        spend: (r.spend_cents ?? 0) / 100,
      })),
    [daily],
  );
  if (!data.length) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Gasto ao longo do tempo</CardTitle>
        <CardDescription>Soma diária de todas as campanhas</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis dataKey="date" fontSize={11} tickMargin={8} />
              <YAxis fontSize={11} width={64}
                tickFormatter={(v) => formatCents(Math.round(v * 100), currency)} />
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
      </CardContent>
    </Card>
  );
}

export default function AdsVisaoGeral() {
  const { preset, setPreset, range } = useDateRange("28d");
  const prev = useMemo(() => prevRange(range), [range]);

  const accountQ = useAdsAccount();
  const campaignsQ = useAdsCampaigns();

  const account = accountQ.data?.data?.[0] ?? null;
  const currency = account?.currency ?? "BRL";
  const campaigns = campaignsQ.data?.data ?? [];

  const objective = useMemo(() => dominantObjective(campaigns), [campaigns]);
  const curQ = useAdsAccountInsights(range.since, range.until);
  const prevQ = useAdsAccountInsights(prev.since, prev.until);
  const sync = useAdsSync();

  // Account resolution gates first — never a zeros dashboard. `&& !account`
  // (not `|| isFetching`) — this account query isn't filter-keyed, but
  // "Sincronizar agora" invalidates the whole `meta-ads` namespace, so the
  // old gate blanked this ENTIRE page, including the very sync button the
  // user just clicked, on every sync.
  if (accountQ.isPending && !account) return <AdsLoading />;
  if (accountQ.isError || !account) {
    return <AdsNotConfigured detail={(accountQ.error as Error)?.message} />;
  }

  const curTotals = normTotals(curQ.data);
  const prevTotals = normTotals(prevQ.data);
  const tiles = buildTiles(objective, curTotals, prevTotals, currency);
  const loadingTotals =
    (campaignsQ.isPending && !campaignsQ.data) || (curQ.isPending && !curQ.data);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{account.name ?? "Conta de anúncios"}</h2>
          <p className="text-sm text-muted-foreground">
            {account.act_id} · {currency}
            {objective ? ` · objetivo predominante: ${objective.replace("OUTCOME_", "")}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SavedViewsControl preset={preset} onApply={setPreset} />
          <DateRangeSelect preset={preset} onChange={setPreset} />
          <ExportButtons since={range.since} until={range.until} />
          <Button
            variant="outline"
            size="sm"
            onClick={() => sync.mutate("incremental")}
            disabled={sync.isPending}
          >
            {sync.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            Sincronizar agora
          </Button>
        </div>
      </div>

      {curQ.isError ? (
        <AdsError message="Não foi possível carregar o resumo do período." onRetry={() => curQ.refetch()} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
            {tiles.map((t) => (
              <MetricCard
                key={t.key}
                icon={t.icon}
                label={t.label}
                value={t.value}
                hint={t.hint}
                loading={loadingTotals}
              />
            ))}
          </div>

          {/* Account financial snapshot */}
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <MetricCard
              icon={DollarSign}
              label="Gasto (histórico)"
              value={formatCents(account.amount_spent_cents, currency)}
            />
            <MetricCard
              icon={DollarSign}
              label="Saldo"
              value={formatCents(account.balance_cents, currency)}
            />
            <MetricCard
              icon={TrendingUp}
              label="Limite de gasto"
              value={formatCents(account.spend_cap_cents, currency)}
            />
            <MetricCard
              icon={account.account_status === 1 ? TrendingUp : TrendingDown}
              label="Status da conta"
              value={account.account_status === 1 ? "Ativa" : String(account.account_status ?? "—")}
            />
          </div>

          <SpendChart daily={curQ.data?.daily ?? []} currency={currency} />
        </>
      )}
    </div>
  );
}
