/**
 * AdsCampanhas — "Campanhas" subtab: the campaign table with live
 * drill-down (campaign → ad set → ad). Campaigns + their latest snapshot
 * metrics come from `/campaigns`; ad-sets/ads are fetched LIVE on expand
 * (`/campaigns/{id}/children`) — never pre-stored.
 */
import { useMemo, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Loader2,
} from "lucide-react";

import {
  Card,
  CardContent,
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
import { Skeleton } from "@/components/ui/skeleton";
import { formatNumber } from "@/lib/formatNumber";
import { formatCents } from "@/lib/formatCurrency";
import {
  useAdsAccount,
  useAdsCampaigns,
  useAdsChildren,
  type AdsCampaign,
  type AdsObject,
} from "@/hooks/useMetaAds";
import { AdsError, AdsLoading, AdsNotConfigured, statusVariant } from "./adsShared";
import { AdDetalheModal } from "./AdDetalheModal";

function objectiveLabel(obj?: string | null): string {
  if (!obj) return "—";
  return obj.replace("OUTCOME_", "");
}

function cpl(c: AdsCampaign): string {
  const spend = c.latest?.spend_cents ?? null;
  const leads = c.latest?.leads ?? null;
  if (spend === null || !leads) return "—";
  return formatCents(Math.round(spend / leads));
}

// ─── Drill-down rows ─────────────────────────────────────────────────────────

function ChildRows({
  campaignId,
  currency,
}: {
  campaignId: string;
  currency: string;
}) {
  const adsetsQ = useAdsChildren(campaignId, "adset");
  const loading = adsetsQ.isPending || adsetsQ.isFetching;
  if (loading) {
    return (
      <tr>
        <td colSpan={6} className="px-4 py-3">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Carregando conjuntos…
          </div>
        </td>
      </tr>
    );
  }
  if (adsetsQ.isError) {
    return (
      <tr>
        <td colSpan={6} className="px-4 py-3 text-sm text-destructive">
          Não foi possível carregar os conjuntos (limite do Meta?).
        </td>
      </tr>
    );
  }
  const adsets = adsetsQ.data?.data ?? [];
  if (!adsets.length) {
    return (
      <tr>
        <td colSpan={6} className="px-4 py-3 text-sm text-muted-foreground">
          Nenhum conjunto de anúncios.
        </td>
      </tr>
    );
  }
  return (
    <>
      {adsets.map((a) => (
        <AdsetRow key={a.object_id} adsetId={a.object_id} name={a.name}
          status={a.effective_status} budget={a.daily_budget_cents} currency={currency} />
      ))}
    </>
  );
}

function AdsetRow({
  adsetId,
  name,
  status,
  budget,
  currency,
}: {
  adsetId: string;
  name: string | null;
  status: string | null;
  budget: number | null;
  currency: string;
}) {
  const [open, setOpen] = useState(false);
  const [selectedAd, setSelectedAd] = useState<AdsObject | null>(null);
  const adsQ = useAdsChildren(open ? adsetId : null, "ad");
  const sv = statusVariant(status);
  const ads = adsQ.data?.data ?? [];
  return (
    <>
      <tr className="bg-muted/30">
        <td className="py-2 pl-10 pr-4">
          <button
            className="flex items-center gap-1.5 text-left text-sm"
            onClick={() => setOpen((o) => !o)}
          >
            {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            <span className="font-medium">{name ?? adsetId}</span>
          </button>
        </td>
        <td className="px-4 py-2 text-xs text-muted-foreground">Conjunto</td>
        <td className="px-4 py-2">
          <Badge variant="outline" className={sv.cls}>{sv.label}</Badge>
        </td>
        <td className="px-4 py-2 text-sm">{budget !== null ? `${formatCents(budget, currency)}/dia` : "—"}</td>
        <td className="px-4 py-2" />
        <td className="px-4 py-2" />
      </tr>
      {open && (adsQ.isPending || adsQ.isFetching) && (
        <tr><td colSpan={6} className="py-2 pl-16 text-sm text-muted-foreground">
          <Loader2 className="inline h-3.5 w-3.5 animate-spin" /> Carregando anúncios…
        </td></tr>
      )}
      {open && ads.map((ad) => {
        const asv = statusVariant(ad.effective_status);
        return (
          <tr key={ad.object_id}>
            <td className="py-2 pl-16 pr-4">
              {/* A real <button>, same keyboard-activation contract as the
                  ad-set toggle above — clickable AND reachable/activatable
                  via keyboard, never mouse-only. */}
              <button
                type="button"
                className="flex items-center gap-2 rounded text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onClick={() => setSelectedAd(ad)}
              >
                {ad.creative_thumbnail_url && (
                  <img src={ad.creative_thumbnail_url} alt="" className="h-8 w-8 rounded object-cover" />
                )}
                <span className="text-sm underline-offset-2 hover:underline">{ad.name ?? ad.object_id}</span>
              </button>
            </td>
            <td className="px-4 py-2 text-xs text-muted-foreground">Anúncio</td>
            <td className="px-4 py-2"><Badge variant="outline" className={asv.cls}>{asv.label}</Badge></td>
            <td className="px-4 py-2" />
            <td className="px-4 py-2" />
            <td className="px-4 py-2" />
          </tr>
        );
      })}
      {selectedAd && (
        <AdDetalheModal
          ad={selectedAd}
          currency={currency}
          onClose={() => setSelectedAd(null)}
        />
      )}
    </>
  );
}

function CampaignRow({ c, currency }: { c: AdsCampaign; currency: string }) {
  const [open, setOpen] = useState(false);
  const sv = statusVariant(c.effective_status);
  return (
    <>
      <tr className="border-t hover:bg-muted/40">
        <td className="py-3 pl-4 pr-4">
          <button className="flex items-center gap-1.5 text-left" onClick={() => setOpen((o) => !o)}>
            {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            <span className="font-medium">{c.name ?? c.object_id}</span>
          </button>
        </td>
        <td className="px-4 py-3">
          <Badge variant="secondary">{objectiveLabel(c.objective)}</Badge>
        </td>
        <td className="px-4 py-3"><Badge variant="outline" className={sv.cls}>{sv.label}</Badge></td>
        <td className="px-4 py-3 text-sm tabular-nums">{formatCents(c.latest?.spend_cents ?? null, currency)}</td>
        <td className="px-4 py-3 text-sm tabular-nums">{c.latest?.leads != null ? formatNumber(c.latest.leads) : "—"}</td>
        <td className="px-4 py-3 text-sm tabular-nums">{cpl(c)}</td>
      </tr>
      {open && <ChildRows campaignId={c.object_id} currency={currency} />}
    </>
  );
}

export default function AdsCampanhas() {
  const accountQ = useAdsAccount();
  const [status, setStatus] = useState<string>("all");
  const [objective, setObjective] = useState<string>("all");
  const campaignsQ = useAdsCampaigns(
    status === "all" ? undefined : status,
    objective === "all" ? undefined : objective,
  );

  const account = accountQ.data?.data?.[0] ?? null;
  const currency = account?.currency ?? "BRL";
  const campaigns = campaignsQ.data?.data ?? [];

  const objectives = useMemo(
    () => Array.from(new Set(campaigns.map((c) => c.objective).filter(Boolean))) as string[],
    [campaigns],
  );

  if (accountQ.isPending || accountQ.isFetching) return <AdsLoading />;
  if (accountQ.isError || !account) return <AdsNotConfigured detail={(accountQ.error as Error)?.message} />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-[160px]"><SelectValue placeholder="Status" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos os status</SelectItem>
            <SelectItem value="ACTIVE">Ativas</SelectItem>
            <SelectItem value="PAUSED">Pausadas</SelectItem>
          </SelectContent>
        </Select>
        <Select value={objective} onValueChange={setObjective}>
          <SelectTrigger className="w-[200px]"><SelectValue placeholder="Objetivo" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos os objetivos</SelectItem>
            {objectives.map((o) => (
              <SelectItem key={o} value={o}>{objectiveLabel(o)}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Campanhas {campaigns.length ? `(${campaigns.length})` : ""}
          </CardTitle>
        </CardHeader>
        <CardContent className="px-0">
          {campaignsQ.isPending || campaignsQ.isFetching ? (
            <div className="space-y-2 px-4">
              {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
            </div>
          ) : campaignsQ.isError ? (
            <div className="px-4"><AdsError message="Não foi possível listar as campanhas (limite do Meta?)." onRetry={() => campaignsQ.refetch()} /></div>
          ) : !campaigns.length ? (
            <p className="px-4 py-8 text-center text-sm text-muted-foreground">Nenhuma campanha encontrada.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="py-2 pl-4 pr-4 font-medium">Campanha</th>
                    <th className="px-4 py-2 font-medium">Objetivo</th>
                    <th className="px-4 py-2 font-medium">Status</th>
                    <th className="px-4 py-2 font-medium">Gasto (último dia)</th>
                    <th className="px-4 py-2 font-medium">Leads (último dia)</th>
                    <th className="px-4 py-2 font-medium">Custo/lead (último dia)</th>
                  </tr>
                </thead>
                <tbody>
                  {campaigns.map((c) => <CampaignRow key={c.object_id} c={c} currency={currency} />)}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
