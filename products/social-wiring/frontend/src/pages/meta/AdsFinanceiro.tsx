/**
 * AdsFinanceiro — "Financeiro" subtab: the money view.
 *
 * Account totals (gasto histórico / saldo / limite), budget-vs-actual
 * pacing per active campaign (daily budget vs the latest day's spend →
 * over/under delivery), and a cost-metric trend (CPC/CPM/CTR) over the
 * selected window for a chosen campaign. All BRL-formatted from the
 * account currency.
 */
import { useEffect, useMemo, useState } from "react";
import { DollarSign, Landmark, TrendingUp, Wallet } from "lucide-react";
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
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { MetricCard } from "@/components/MetricCard";
import { formatCents } from "@/lib/formatCurrency";
import {
  useAdsAccount,
  useAdsCampaigns,
  useAdsInsightsSeries,
} from "@/hooks/useMetaAds";
import {
  AdsLoading,
  AdsNotConfigured,
  DateRangeSelect,
  ExportButtons,
  useDateRange,
} from "./adsShared";

export default function AdsFinanceiro() {
  const accountQ = useAdsAccount();
  const account = accountQ.data?.data?.[0] ?? null;
  const currency = account?.currency ?? "BRL";

  const { preset, setPreset, range } = useDateRange("28d");
  const campaignsQ = useAdsCampaigns();
  const campaigns = campaignsQ.data?.data ?? [];

  const [campaignId, setCampaignId] = useState<string>("");
  useEffect(() => {
    if (!campaignId && campaigns.length) setCampaignId(campaigns[0].object_id);
  }, [campaigns, campaignId]);

  const seriesQ = useAdsInsightsSeries(campaignId || null, "campaign", range.since, range.until);

  const costTrend = useMemo(
    () =>
      (seriesQ.data?.rows ?? []).map((r) => ({
        label: r.date.slice(5),
        cpc: r.cpc_cents != null ? r.cpc_cents / 100 : null,
        cpm: r.cpm_cents != null ? r.cpm_cents / 100 : null,
        ctr: r.ctr ?? null,
      })),
    [seriesQ.data],
  );

  // Budget vs actual pacing — active campaigns with a daily budget.
  const pacing = useMemo(
    () =>
      campaigns
        .filter((c) => c.daily_budget_cents && c.effective_status === "ACTIVE")
        .map((c) => {
          const budget = c.daily_budget_cents ?? 0;
          const spent = c.latest?.spend_cents ?? 0;
          const ratio = budget ? spent / budget : 0;
          return { id: c.object_id, name: c.name ?? c.object_id, budget, spent, ratio };
        })
        .sort((a, b) => b.ratio - a.ratio),
    [campaigns],
  );

  if (accountQ.isPending || accountQ.isFetching) return <AdsLoading />;
  if (accountQ.isError || !account) return <AdsNotConfigured detail={(accountQ.error as Error)?.message} />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Financeiro</h2>
        <ExportButtons since={range.since} until={range.until} />
      </div>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <MetricCard icon={DollarSign} label="Gasto (histórico)"
          value={formatCents(account.amount_spent_cents, currency)} />
        <MetricCard icon={Wallet} label="Saldo"
          value={formatCents(account.balance_cents, currency)} />
        <MetricCard icon={Landmark} label="Limite de gasto"
          value={formatCents(account.spend_cap_cents, currency)} />
        <MetricCard icon={TrendingUp} label="Moeda" value={currency} />
      </div>

      {/* Budget vs actual pacing */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Ritmo de orçamento</CardTitle>
          <CardDescription>
            Orçamento diário vs. gasto do último dia (campanhas ativas)
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!pacing.length ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Nenhuma campanha ativa com orçamento diário definido.
            </p>
          ) : (
            <div className="space-y-4">
              {pacing.map((p) => {
                const pctOfBudget = Math.min(100, Math.round(p.ratio * 100));
                const over = p.ratio > 1;
                return (
                  <div key={p.id}>
                    <div className="mb-1 flex items-center justify-between text-sm">
                      <span className="truncate pr-2">{p.name}</span>
                      <span className="flex items-center gap-2 tabular-nums">
                        {formatCents(p.spent, currency)} / {formatCents(p.budget, currency)}
                        <Badge variant="outline"
                          className={over
                            ? "border-amber-500/30 bg-amber-500/15 text-amber-600"
                            : "border-emerald-500/30 bg-emerald-500/15 text-emerald-600"}>
                          {over ? "acima" : `${pctOfBudget}%`}
                        </Badge>
                      </span>
                    </div>
                    <div className="h-2.5 w-full rounded bg-muted">
                      <div
                        className={`h-2.5 rounded ${over ? "bg-amber-500" : "bg-primary"}`}
                        style={{ width: `${Math.min(100, p.ratio * 100)}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Cost-metric trend */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0">
          <div>
            <CardTitle className="text-base">Tendência de custos</CardTitle>
            <CardDescription>CPC e CPM ao longo do período</CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Select value={campaignId} onValueChange={setCampaignId}>
              <SelectTrigger className="w-[220px]"><SelectValue placeholder="Campanha" /></SelectTrigger>
              <SelectContent>
                {campaigns.map((c) => (
                  <SelectItem key={c.object_id} value={c.object_id}>{c.name ?? c.object_id}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <DateRangeSelect preset={preset} onChange={setPreset} />
          </div>
        </CardHeader>
        <CardContent>
          {seriesQ.isPending || seriesQ.isFetching ? (
            <AdsLoading label="Carregando…" />
          ) : !costTrend.length ? (
            <p className="py-8 text-center text-sm text-muted-foreground">Sem dados no período.</p>
          ) : (
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={costTrend} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="label" fontSize={11} tickMargin={8} />
                  <YAxis fontSize={11} width={64}
                    tickFormatter={(v) => formatCents(Math.round(v * 100), currency)} />
                  <Tooltip formatter={(v: number) => formatCents(Math.round(v * 100), currency)} />
                  <Line type="monotone" dataKey="cpc" name="CPC" stroke="hsl(var(--primary))" strokeWidth={2} dot={false} connectNulls />
                  <Line type="monotone" dataKey="cpm" name="CPM" stroke="hsl(330 81% 60%)" strokeWidth={2} dot={false} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
