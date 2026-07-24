/**
 * AdsHistorico — "Histórico" subtab: the evolution charts.
 *
 * 1. Spend-over-time WITH change-log markers — the differentiator: vertical
 *    ReferenceLines at each activity event (status flip / budget edit), so
 *    the shape of the spend curve is explained ("who changed what, when",
 *    incl. same-day pause→resume as two markers). Meta's own UI does this
 *    badly; it is the whole point of storing the activity log.
 * 2. Placement split (publisher_platform breakdown).
 * 3. Funnel: impressões → alcance → cliques → leads.
 *
 * Everything is per selected campaign (the insights/activity endpoints are
 * object-scoped).
 */
import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ReferenceLine,
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { formatNumber } from "@/lib/formatNumber";
import { formatCents } from "@/lib/formatCurrency";
import {
  useAdsAccount,
  useAdsActivities,
  useAdsCampaigns,
  useAdsInsightsSeries,
} from "@/hooks/useMetaAds";
import {
  activityLabel,
  AdsError,
  AdsLoading,
  AdsNotConfigured,
  DateRangeSelect,
  rowAction,
  rowLeads,
  useDateRange,
} from "./adsShared";

const PLACEMENT_COLORS: Record<string, string> = {
  facebook: "hsl(221 83% 53%)",
  instagram: "hsl(330 81% 60%)",
  audience_network: "hsl(142 71% 45%)",
  messenger: "hsl(199 89% 48%)",
  unknown: "hsl(var(--muted-foreground))",
};

export default function AdsHistorico() {
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
  const placementQ = useAdsInsightsSeries(
    campaignId || null, "campaign", range.since, range.until, "publisher_platform",
  );
  const activitiesQ = useAdsActivities(range.since, range.until, campaignId || null);

  const spendData = useMemo(
    () =>
      (seriesQ.data?.rows ?? []).map((r) => ({
        date: r.date,
        label: r.date.slice(5),
        spend: (r.spend_cents ?? 0) / 100,
      })),
    [seriesQ.data],
  );

  // Activity markers keyed to the chart's date axis (day granularity).
  const markers = useMemo(() => {
    const days = new Set(spendData.map((d) => d.date));
    return (activitiesQ.data?.data ?? [])
      .map((a) => ({
        day: a.occurred_at.slice(0, 10),
        label: activityLabel(a),
      }))
      .filter((m) => days.has(m.day));
  }, [activitiesQ.data, spendData]);

  // Placement split needs the `breakdown` dimension (publisher_platform) on
  // each row. The current AdsInsightsRow DTO does not carry it (backend
  // follow-up: echo `breakdown` on the row), so `placementAvailable` is
  // false and we show an honest note instead of a misleading single bar.
  const placementData = useMemo(() => {
    const byPlat = new Map<string, number>();
    for (const r of placementQ.data?.rows ?? []) {
      const bd = r.breakdown ?? {};
      const key = bd.publisher_platform ?? bd.platform_position ?? null;
      if (!key) continue;
      byPlat.set(key, (byPlat.get(key) ?? 0) + (r.spend_cents ?? 0));
    }
    return Array.from(byPlat.entries()).map(([platform, cents]) => ({
      platform,
      spend: cents / 100,
    }));
  }, [placementQ.data]);
  const placementAvailable = placementData.length > 0;

  const funnel = useMemo(() => {
    const rows = seriesQ.data?.rows ?? [];
    const sum = (f: (r: (typeof rows)[number]) => number) => rows.reduce((a, r) => a + f(r), 0);
    return [
      { stage: "Impressões", value: sum((r) => r.impressions ?? 0) },
      { stage: "Alcance", value: sum((r) => r.reach ?? 0) },
      { stage: "Cliques no link", value: sum((r) => rowAction(r, "link_click")) },
      { stage: "Leads", value: sum((r) => rowLeads(r)) },
    ];
  }, [seriesQ.data]);

  if (accountQ.isPending || accountQ.isFetching) return <AdsLoading />;
  if (accountQ.isError || !account) return <AdsNotConfigured detail={(accountQ.error as Error)?.message} />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Select value={campaignId} onValueChange={setCampaignId}>
          <SelectTrigger className="w-[280px]"><SelectValue placeholder="Selecione a campanha" /></SelectTrigger>
          <SelectContent>
            {campaigns.map((c) => (
              <SelectItem key={c.object_id} value={c.object_id}>{c.name ?? c.object_id}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <DateRangeSelect preset={preset} onChange={setPreset} />
      </div>

      {/* 1 — spend with change markers */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Gasto e mudanças</CardTitle>
          <CardDescription>
            Linhas verticais marcam mudanças na campanha (status/orçamento) — o que explica a curva.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {seriesQ.isPending || seriesQ.isFetching ? (
            <AdsLoading label="Carregando série…" />
          ) : seriesQ.isError ? (
            <AdsError onRetry={() => seriesQ.refetch()} />
          ) : !spendData.length ? (
            <p className="py-10 text-center text-sm text-muted-foreground">Sem dados no período.</p>
          ) : (
            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={spendData} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="label" fontSize={11} tickMargin={8} />
                  <YAxis fontSize={11} width={64}
                    tickFormatter={(v) => formatCents(Math.round(v * 100), currency)} />
                  <Tooltip formatter={(v: number) => formatCents(Math.round(v * 100), currency)} />
                  {markers.map((m, i) => (
                    <ReferenceLine key={i} x={m.day.slice(5)} stroke="hsl(var(--destructive))"
                      strokeDasharray="4 3" label={{ value: "•", position: "top" }} />
                  ))}
                  <Line type="monotone" dataKey="spend" stroke="hsl(var(--primary))" strokeWidth={2} dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}
          {markers.length > 0 && (
            <ul className="mt-3 space-y-1 text-xs text-muted-foreground">
              {markers.slice(0, 6).map((m, i) => (
                <li key={i}>
                  <span className="font-medium text-foreground">{m.day}</span> — {m.label}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* 2 — placement split */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Distribuição por posicionamento</CardTitle>
            <CardDescription>Gasto por plataforma (IG / FB / …)</CardDescription>
          </CardHeader>
          <CardContent>
            {placementQ.isPending || placementQ.isFetching ? (
              <AdsLoading label="Carregando…" />
            ) : !placementAvailable ? (
              <p className="py-10 text-center text-sm text-muted-foreground">
                Sem dados de posicionamento para esta campanha no período.
              </p>
            ) : (
              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={placementData} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                    <XAxis dataKey="platform" fontSize={11} />
                    <YAxis fontSize={11} width={64}
                      tickFormatter={(v) => formatCents(Math.round(v * 100), currency)} />
                    <Tooltip formatter={(v: number) => formatCents(Math.round(v * 100), currency)} />
                    <Bar dataKey="spend">
                      {placementData.map((d, i) => (
                        <Cell key={i} fill={PLACEMENT_COLORS[d.platform] ?? PLACEMENT_COLORS.unknown} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>

        {/* 3 — funnel */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Funil</CardTitle>
            <CardDescription>Impressões → alcance → cliques → leads</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3 py-2">
              {funnel.map((f, i) => {
                const max = funnel[0].value || 1;
                const w = Math.max(4, (f.value / max) * 100);
                return (
                  <div key={f.stage}>
                    <div className="mb-1 flex items-center justify-between text-sm">
                      <span>{f.stage}</span>
                      <span className="tabular-nums font-medium">{formatNumber(f.value)}</span>
                    </div>
                    <div className="h-3 w-full rounded bg-muted">
                      <div className="h-3 rounded bg-primary" style={{ width: `${w}%`, opacity: 1 - i * 0.15 }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
