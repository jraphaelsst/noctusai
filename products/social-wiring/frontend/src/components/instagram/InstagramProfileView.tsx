/**
 * InstagramProfileView — the ONE Instagram profile surface, shared by the Meta
 * page (Instagram tab) and, later, CoreStudio "Minha conta › Instagram".
 *
 *   header   avatar · @username · name · followers/following/posts · sync action
 *   banners  reconnect (insights scope missing) · App Review pending · sync result
 *   KPIs     Seguidores · Novos seguidores · Visualizações · Engajamento · Comentários
 *   charts   Engajamento + Alcance with a 30 dias / 7 dias / Último dia toggle
 *   posts    InstagramPostGrid (optional via `showPosts`)
 *
 * Data is DAILY, never intraday: "Último dia" is the latest daily point. The
 * account-level metrics of a day-D point cover the previous BRT day (Meta lags
 * up to 48h) — stated under the charts.
 * "Novos seguidores" is DERIVED from followers_count deltas over the period;
 * "—" when fewer than two captures exist.
 */
import { useMemo, useState } from "react";
import {
  CircleAlert,
  Eye,
  Heart,
  Instagram,
  Loader2,
  MessageCircle,
  RefreshCw,
  ShieldAlert,
  UserPlus,
  Users,
} from "lucide-react";

import {
  ChartCard,
  LineChart,
  StatTile,
  StatTileRow,
  formatMediaInsightValue,
  MEDIA_INSIGHTS_EMPTY_MESSAGE,
} from "@noctusai/lib/design-system";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useStartProviderOAuth } from "@/hooks/useIntegrationAccounts";
import {
  isSyncAppReview,
  isSyncReconnect,
  useInstagramProfile,
  useInstagramSync,
  useInstagramTrend,
  type InstagramProfile,
} from "@/hooks/useInstagramInsights";
import { InstagramPostGrid } from "./InstagramPostGrid";
import {
  PERIOD_LABEL,
  followerGrowth,
  pointsForPeriod,
  sumMetric,
  type InstagramPeriod,
} from "./insights";

const PERIODS: InstagramPeriod[] = ["30d", "7d", "last"];

function fmt(v: number | null): string {
  return formatMediaInsightValue(v, "int");
}

function formatSynced(iso: string | null): string {
  if (!iso) return "ainda não sincronizado";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "ainda não sincronizado";
  return `sincronizado em ${d.toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" })}`;
}

function ReconnectBanner({
  profile,
  onReconnect,
  pending,
  detail,
}: {
  profile: InstagramProfile | undefined;
  onReconnect: () => void;
  pending: boolean;
  detail?: string | null;
}) {
  return (
    <div
      role="alert"
      data-testid="ig-reconnect-banner"
      className="flex flex-wrap items-center gap-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm"
    >
      <ShieldAlert className="h-4 w-4 shrink-0 text-amber-500" />
      <p className="flex-1">
        {detail ??
          "Esta conta foi conectada sem a permissão de métricas do Instagram. Reconecte para liberar os insights."}
        {profile?.username ? ` (@${profile.username})` : ""}
      </p>
      <Button size="sm" onClick={onReconnect} disabled={pending} data-testid="ig-reconnect-button">
        {pending && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
        Reconectar Instagram
      </Button>
    </div>
  );
}

export interface InstagramProfileViewProps {
  accountId: string;
  /** Render the post grid under the charts. Default true. */
  showPosts?: boolean;
}

export function InstagramProfileView({ accountId, showPosts = true }: InstagramProfileViewProps) {
  const [period, setPeriod] = useState<InstagramPeriod>("30d");
  const profileQ = useInstagramProfile(accountId);
  const trendQ = useInstagramTrend(accountId, 30);
  const sync = useInstagramSync(accountId);
  const oauth = useStartProviderOAuth("instagram");

  const profile = profileQ.data;
  const trend = trendQ.data;

  const showSkeleton = profileQ.isPending && !profileQ.data;
  const trendSkeleton = trendQ.isPending && !trendQ.data;
  const isRefreshing = (profileQ.isFetching && !!profileQ.data) || (trendQ.isFetching && !!trendQ.data);

  const all = useMemo(() => trend?.points ?? [], [trend]);
  const inPeriod = useMemo(() => pointsForPeriod(all, period), [all, period]);

  const kpi = useMemo(
    () => ({
      novos: followerGrowth(all, period),
      views: sumMetric(inPeriod, "views"),
      engagement: sumMetric(inPeriod, "total_interactions"),
      comments: sumMetric(inPeriod, "comments"),
    }),
    [all, inPeriod, period],
  );

  const periodHint = period === "last" ? "último dia" : `últimos ${PERIOD_LABEL[period]}`;

  const syncData = sync.data;
  const reconnectFromSync = syncData && isSyncReconnect(syncData) ? syncData : null;
  const needsReconnect = (profile ? !profile.insights_scope_granted : false) || !!reconnectFromSync;
  const appReview = syncData && isSyncAppReview(syncData) ? syncData : null;
  const syncOk = syncData && !isSyncReconnect(syncData) && !isSyncAppReview(syncData) ? syncData : null;

  const reconnect = () => oauth.mutate(profile?.marca_id ? { marcaId: profile.marca_id } : undefined);

  const noData = !!profile && !profile.last_synced_at && all.length === 0;
  const chartXFormatter = (v: string) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(v);
    return m ? `${m[3]}/${m[2]}` : v;
  };

  const chartCard = (title: string, key: string, subtitle: string) => {
    const hasAny = inPeriod.some((p) => typeof p[key] === "number");
    const last = inPeriod[inPeriod.length - 1];
    return (
      <ChartCard
        title={title}
        subtitle={subtitle}
        loading={trendSkeleton}
        error={trendQ.isError && !trend ? "Erro ao carregar a tendência." : null}
        isEmpty={!trendSkeleton && !hasAny}
        emptyMessage={MEDIA_INSIGHTS_EMPTY_MESSAGE}
        minBodyHeight={240}
      >
        {period === "last" ? (
          <div className="flex h-[240px] flex-col items-center justify-center gap-1" data-testid={`ig-chart-${key}-last`}>
            <span className="text-4xl font-semibold tabular-nums">
              {fmt(typeof last?.[key] === "number" ? (last[key] as number) : null)}
            </span>
            <span className="text-xs text-muted-foreground">
              último dia coletado{last ? ` (${chartXFormatter(last.date)})` : ""}
            </span>
          </div>
        ) : (
          <LineChart
            data={inPeriod}
            xKey="date"
            series={[{ key, label: title }]}
            height={240}
            xTickFormatter={chartXFormatter}
          />
        )}
      </ChartCard>
    );
  };

  return (
    <div className="space-y-6" data-testid="ig-profile-view">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-4 rounded-lg border bg-card p-4">
        {showSkeleton ? (
          <Skeleton className="h-16 w-16 rounded-full" />
        ) : profile?.profile_picture_url ? (
          <img
            src={profile.profile_picture_url}
            alt={profile.username ?? "Perfil do Instagram"}
            className="h-16 w-16 rounded-full object-cover"
          />
        ) : (
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-muted">
            <Instagram className="h-7 w-7 text-muted-foreground" />
          </div>
        )}
        <div className="min-w-0 flex-1">
          {showSkeleton ? (
            <Skeleton className="h-5 w-40" />
          ) : (
            <>
              <h2 className="truncate text-lg font-semibold" data-testid="ig-username">
                {profile?.username ? `@${profile.username}` : "Instagram"}
              </h2>
              {profile?.name && <p className="truncate text-sm text-muted-foreground">{profile.name}</p>}
              <p className="mt-1 text-xs text-muted-foreground">
                {fmt(profile?.followers_count ?? null)} seguidores · {fmt(profile?.follows_count ?? null)} seguindo ·{" "}
                {fmt(profile?.media_count ?? null)} publicações · {formatSynced(profile?.last_synced_at ?? null)}
                {isRefreshing && " · Atualizando…"}
              </p>
            </>
          )}
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => sync.mutate()}
          disabled={sync.isPending}
          data-testid="ig-sync-button"
        >
          {sync.isPending ? (
            <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="mr-2 h-3.5 w-3.5" />
          )}
          {sync.isPending ? "Sincronizando…" : "Sincronizar agora"}
        </Button>
      </div>

      {profileQ.isError && !profile && (
        <div
          role="alert"
          data-testid="ig-profile-error"
          className="flex items-center gap-2 rounded-md border border-destructive/40 p-3 text-sm text-destructive"
        >
          <CircleAlert className="h-4 w-4" /> Erro ao carregar o perfil.
          <Button variant="ghost" size="sm" onClick={() => void profileQ.refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {needsReconnect && (
        <ReconnectBanner
          profile={profile}
          onReconnect={reconnect}
          pending={oauth.isPending}
          detail={reconnectFromSync?.error}
        />
      )}
      {appReview && (
        <div
          role="status"
          data-testid="ig-app-review-notice"
          className="flex items-start gap-3 rounded-md border border-dashed p-3 text-sm"
        >
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
          <p>
            {appReview.error ??
              "A permissão de métricas ainda está pendente de aprovação pela Meta (App Review). Os insights ficam disponíveis assim que ela for liberada."}
          </p>
        </div>
      )}
      {sync.isError && (
        <div role="alert" data-testid="ig-sync-error" className="rounded-md border border-destructive/40 p-3 text-sm text-destructive">
          Não foi possível sincronizar agora. Tente novamente em instantes.
        </div>
      )}
      {syncOk && (
        <p data-testid="ig-sync-result" className="text-xs text-muted-foreground">
          {syncOk.status === "skipped"
            ? "Hoje já foi sincronizado — nada novo a coletar."
            : syncOk.status === "partial"
              ? `Sincronização parcial: ${syncOk.media_synced} publicações, ${syncOk.media_failed} com falha.`
              : `Sincronizado: ${syncOk.media_synced} publicações atualizadas.`}
        </p>
      )}

      {noData && !needsReconnect && (
        <div data-testid="ig-no-data" className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
          Ainda não há dados desta conta. Clique em “Sincronizar agora” para a primeira coleta — a partir daí
          os números passam a ser coletados todos os dias.
        </div>
      )}

      {/* Period toggle */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-muted-foreground">Desempenho da conta</h3>
        <div role="group" aria-label="Período" className="inline-flex rounded-md border p-0.5">
          {PERIODS.map((p) => (
            <Button
              key={p}
              type="button"
              size="sm"
              variant={period === p ? "default" : "ghost"}
              aria-pressed={period === p}
              onClick={() => setPeriod(p)}
              data-testid={`ig-period-${p}`}
            >
              {PERIOD_LABEL[p]}
            </Button>
          ))}
        </div>
      </div>

      {/* KPIs */}
      <StatTileRow className="lg:grid-cols-5">
        <StatTile
          icon={Users}
          label="Seguidores"
          value={fmt(profile?.followers_count ?? null)}
          loading={showSkeleton}
        />
        <StatTile
          icon={UserPlus}
          label="Novos seguidores"
          value={fmt(kpi.novos)}
          hint={`Variação de seguidores nos ${periodHint}`}
          loading={trendSkeleton}
        />
        <StatTile icon={Eye} label="Visualizações" value={fmt(kpi.views)} hint={periodHint} loading={trendSkeleton} />
        <StatTile icon={Heart} label="Engajamento" value={fmt(kpi.engagement)} hint={periodHint} loading={trendSkeleton} />
        <StatTile icon={MessageCircle} label="Comentários" value={fmt(kpi.comments)} hint={periodHint} loading={trendSkeleton} />
      </StatTileRow>

      {/* Charts */}
      <div className="grid gap-4 lg:grid-cols-2">
        {chartCard("Engajamento", "total_interactions", `Interações por dia · ${PERIOD_LABEL[period]}`)}
        {chartCard("Alcance", "reach", `Contas alcançadas por dia · ${PERIOD_LABEL[period]}`)}
      </div>
      <p className="text-xs text-muted-foreground">
        Dados diários: as métricas da conta em cada data referem-se ao dia anterior à coleta (a Meta pode
        atrasar até 48h).
      </p>

      {showPosts && (
        <section className="space-y-3">
          <h3 className="text-sm font-medium text-muted-foreground">Publicações</h3>
          <InstagramPostGrid accountId={accountId} />
        </section>
      )}
    </div>
  );
}

export default InstagramProfileView;
