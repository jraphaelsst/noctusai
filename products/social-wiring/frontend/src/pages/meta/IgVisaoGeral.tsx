/**
 * IgVisaoGeral — Instagram "Visão geral" subtab of the Meta dashboard.
 *
 * Ports the KPI row + followers trend + per-post table from the retired
 * `InstagramInsights.tsx`, re-pointed from the local `AccountPicker` /
 * `{ig_user_id}` path-param model to the shared `activeAccountId`
 * (`useActiveAccountStore`, set by `<ConnectedAccountSwitcher provider="meta" />`
 * in the dashboard shell).
 *
 * States: no account selected (empty) / context loading / no IG account on
 * this connection (empty) / insights error banner / trend + posts each with
 * their own loading/empty/error.
 */
import { useMemo } from "react";
import {
  Camera,
  CircleAlert,
  Eye,
  Grid3x3,
  Instagram,
  Loader2,
  RefreshCw,
  Users,
  UserPlus,
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
import { Skeleton } from "@/components/ui/skeleton";
import { MetricCard } from "@/components/MetricCard";
import { formatNumber } from "@/lib/formatNumber";
import {
  useActiveMetaAccountId,
  useCaptureIgSnapshot,
  useIgInsights,
  useIgMedia,
  useIgSnapshots,
  useMetaContext,
} from "@/hooks/useMeta";

// ─── Followers trend chart ───────────────────────────────────────────────────

function FollowersTrendChart({ accountId }: { accountId: string }) {
  const { data, isLoading, isError } = useIgSnapshots(accountId, 90);

  const chartData = useMemo(
    () =>
      (data?.snapshots ?? []).map((s) => ({
        x: new Date(s.captured_at).toLocaleDateString("pt-BR", {
          day: "2-digit",
          month: "short",
        }),
        followers: s.followers_count ?? 0,
      })),
    [data],
  );

  if (isLoading) {
    return <Skeleton className="h-64 rounded-md" data-testid="ig-trend-loading" />;
  }

  if (isError) {
    return (
      <div
        className="flex h-64 items-center justify-center rounded-md border border-dashed text-sm text-destructive"
        data-testid="ig-trend-error"
      >
        Erro ao carregar histórico de seguidores.
      </div>
    );
  }

  if (chartData.length === 0) {
    return (
      <div
        className="flex h-64 items-center justify-center rounded-md border border-dashed px-4 text-center text-sm text-muted-foreground"
        data-testid="ig-trend-empty"
      >
        Sem histórico ainda — clique em "Capturar agora" para começar a
        acumular snapshots.
      </div>
    );
  }

  return (
    <div className="h-64 w-full" data-testid="ig-trend-chart">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
          <XAxis dataKey="x" fontSize={11} stroke="currentColor" opacity={0.6} />
          <YAxis
            tickFormatter={(v: number) => formatNumber(v)}
            fontSize={11}
            stroke="currentColor"
            opacity={0.6}
          />
          <Tooltip
            formatter={(value: number) => [formatNumber(value), "Seguidores"]}
            labelStyle={{ color: "var(--foreground)" }}
            contentStyle={{
              background: "var(--background)",
              border: "1px solid var(--border)",
              borderRadius: 6,
            }}
          />
          <Line
            type="monotone"
            dataKey="followers"
            stroke="hsl(var(--primary, 220 90% 56%))"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Per-post table ───────────────────────────────────────────────────────────

function PostsTable({ accountId }: { accountId: string }) {
  const { data, isLoading, isError } = useIgMedia(accountId, 25);
  const media = data?.media ?? [];

  if (isLoading) {
    return (
      <div className="space-y-2" data-testid="ig-posts-loading">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full rounded-md" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div
        className="rounded-md border border-dashed p-6 text-center text-sm text-destructive"
        data-testid="ig-posts-error"
      >
        Erro ao carregar posts.
      </div>
    );
  }

  if (media.length === 0) {
    return (
      <div
        className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground"
        data-testid="ig-posts-empty"
      >
        Nenhum post encontrado para esta conta.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto" data-testid="ig-posts-table">
      <table className="w-full min-w-[640px] border-separate border-spacing-0 text-sm">
        <thead>
          <tr className="border-b">
            <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground w-[40%]">
              Post
            </th>
            <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Alcance
            </th>
            <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Curtidas
            </th>
            <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Comentários
            </th>
            <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Salvos
            </th>
          </tr>
        </thead>
        <tbody>
          {media.map((item) => {
            const reach = item.insights?.reach ?? null;
            const saved = item.insights?.saved ?? null;
            return (
              <tr key={item.id} className="border-b last:border-0">
                <td className="px-3 py-3 align-top">
                  <div className="line-clamp-2 font-medium">
                    {item.caption ?? "(sem legenda)"}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {item.timestamp
                      ? new Date(item.timestamp).toLocaleDateString("pt-BR")
                      : "—"}
                  </div>
                </td>
                <td className="px-3 py-3 text-right tabular-nums align-middle">
                  {reach === null ? "—" : formatNumber(reach)}
                </td>
                <td className="px-3 py-3 text-right tabular-nums align-middle">
                  {formatNumber(item.like_count)}
                </td>
                <td className="px-3 py-3 text-right tabular-nums align-middle">
                  {formatNumber(item.comments_count)}
                </td>
                <td className="px-3 py-3 text-right tabular-nums align-middle">
                  {saved === null ? "—" : formatNumber(saved)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ─── Subtab ───────────────────────────────────────────────────────────────────

export default function IgVisaoGeral() {
  const accountId = useActiveMetaAccountId();
  const { data: context, isLoading: contextLoading, isError: contextError } =
    useMetaContext(accountId);
  const { data: insights, isLoading: insightsLoading } = useIgInsights(accountId, 30);
  const capture = useCaptureIgSnapshot(accountId);

  if (!accountId) {
    return (
      <Card>
        <CardContent
          className="p-6 text-center text-sm text-muted-foreground"
          data-testid="ig-overview-no-account"
        >
          Selecione uma conta conectada acima para ver a visão geral do
          Instagram.
        </CardContent>
      </Card>
    );
  }

  if (contextLoading) {
    return (
      <div className="space-y-4" data-testid="ig-overview-loading">
        <Skeleton className="h-10 w-64" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-md" />
          ))}
        </div>
      </div>
    );
  }

  if (contextError) {
    return (
      <Card>
        <CardContent
          className="flex items-center gap-2 p-6 text-sm text-destructive"
          data-testid="ig-overview-error"
        >
          <CircleAlert className="h-4 w-4 shrink-0" />
          Erro ao carregar o contexto do Instagram.
        </CardContent>
      </Card>
    );
  }

  const account = context?.instagram ?? null;

  if (!account) {
    return (
      <Card>
        <CardContent
          className="p-6 text-center text-sm text-muted-foreground"
          data-testid="ig-overview-empty"
        >
          Nenhuma conta do Instagram encontrada para esta conexão do Meta.
        </CardContent>
      </Card>
    );
  }

  const alcance = insights?.metrics?.reach ?? null;
  const visitas = insights?.metrics?.profile_views ?? null;

  return (
    <div className="space-y-6" data-testid="ig-overview-success">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-lg font-semibold">@{account.username}</div>
          {account.name && (
            <div className="text-sm text-muted-foreground">{account.name}</div>
          )}
        </div>
        <Button
          onClick={() => capture.mutate()}
          disabled={capture.isPending}
          data-testid="ig-capture-btn"
        >
          {capture.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Camera className="mr-2 h-4 w-4" />
          )}
          Capturar agora
        </Button>
      </div>

      {insights?.error && (
        <div
          className="flex items-center gap-2 rounded-md border border-dashed p-3 text-sm text-destructive"
          data-testid="ig-insights-error"
        >
          <CircleAlert className="h-4 w-4 shrink-0" />
          {insights.error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <MetricCard icon={Users} label="Seguidores" value={formatNumber(account.followers_count)} />
        <MetricCard icon={UserPlus} label="Seguindo" value={formatNumber(account.follows_count)} />
        <MetricCard icon={Grid3x3} label="Posts" value={formatNumber(account.media_count)} />
        <MetricCard
          icon={Eye}
          label="Alcance (30d)"
          value={insightsLoading ? "—" : formatNumber(alcance)}
          loading={insightsLoading}
        />
        <MetricCard
          icon={Instagram}
          label="Visitas ao perfil (30d)"
          value={insightsLoading ? "—" : formatNumber(visitas)}
          loading={insightsLoading}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <RefreshCw className="h-5 w-5" />
            Seguidores ao longo do tempo
          </CardTitle>
          <CardDescription>Últimos 90 dias, por snapshot.</CardDescription>
        </CardHeader>
        <CardContent>
          <FollowersTrendChart accountId={account.id} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Posts recentes</CardTitle>
          <CardDescription>
            Alcance, curtidas, comentários e salvos por post.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <PostsTable accountId={account.id} />
        </CardContent>
      </Card>
    </div>
  );
}
