/**
 * VisaoGeralPanel — channel overview tab inside the YouTube page.
 *
 * Content:
 *   - Stat cards: total_videos / total_views / total_likes / total_comments
 *   - Subscribers/views trend chart from /api/youtube/channel/trend (30 days)
 *   - Top 5 videos compact grid
 *
 * All data sourced from useDashboardStats, useTopVideos, useChannelTrend.
 * accountId threaded from useActiveAccountStore via each hook's default.
 */
import { useMemo } from "react";
import {
  Activity,
  CheckCircle2,
  CircleAlert,
  Eye,
  Heart,
  MessageCircle,
  PlaySquare,
  Sparkles,
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

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import { MetricCard } from "@/components/MetricCard";
import { VideoCard } from "@/components/VideoCard";
import {
  formatNumber,
  useDashboardStats,
  useTopVideos,
} from "@/hooks/useDashboard";
import { useChannelTrend } from "@/hooks/useChannelTrend";

// ─── Channel trend chart ──────────────────────────────────────────────────────

function ChannelTrendChart() {
  const { data, loading, error } = useChannelTrend(30);

  const chartData = useMemo(
    () =>
      data.map((pt) => ({
        x: new Date(pt.snapshot_date).toLocaleDateString("pt-BR", {
          day: "2-digit",
          month: "short",
        }),
        views: pt.view_count,
        subscribers: pt.subscriber_count,
      })),
    [data],
  );

  if (loading) {
    return <Skeleton className="h-64 rounded-md" />;
  }

  if (error) {
    return (
      <div className="flex h-64 items-center justify-center rounded-md border border-dashed text-sm text-destructive">
        Erro ao carregar tendência: {error}
      </div>
    );
  }

  if (chartData.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground text-center px-4">
        Sem dados de tendência ainda — sincronize para acumular snapshots.
      </div>
    );
  }

  return (
    <div className="h-64 w-full">
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
            formatter={(value: number, name: string) => [
              formatNumber(value),
              name === "views" ? "Visualizações" : "Inscritos",
            ]}
            labelStyle={{ color: "var(--foreground)" }}
            contentStyle={{
              background: "var(--background)",
              border: "1px solid var(--border)",
              borderRadius: 6,
            }}
          />
          <Line
            type="monotone"
            dataKey="views"
            stroke="hsl(var(--primary, 220 90% 56%))"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
          <Line
            type="monotone"
            dataKey="subscribers"
            stroke="hsl(var(--destructive, 0 84% 60%))"
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 3 }}
            strokeDasharray="4 2"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Channel card ─────────────────────────────────────────────────────────────

function ChannelInfoCard({
  channelTitle,
  channelId,
  totalVideos,
  lastSyncedAt,
}: {
  channelTitle: string | null;
  channelId: string | null;
  totalVideos: number;
  lastSyncedAt: string | null;
}) {
  const connected = !!channelId;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {connected ? (
            <CheckCircle2 className="h-5 w-5 text-emerald-600" />
          ) : (
            <CircleAlert className="h-5 w-5 text-amber-600" />
          )}
          Canal conectado
        </CardTitle>
        <CardDescription>
          {connected
            ? "OAuth ativo. Sincronize na aba de Videos para atualizar o cache."
            : "Nenhum canal conectado. Va em Configuracoes → YouTube."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-muted-foreground">Canal</span>
          <span className="font-medium">{channelTitle ?? "—"}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Videos no cache</span>
          <span className="font-medium tabular-nums">{totalVideos}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Ultima sincronizacao</span>
          <span className="font-medium">
            {lastSyncedAt
              ? new Date(lastSyncedAt).toLocaleString("pt-BR")
              : "—"}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Panel ────────────────────────────────────────────────────────────────────

export function VisaoGeralPanel() {
  const { data: stats, loading: statsLoading } = useDashboardStats();
  const { data: topVideos, loading: topLoading } = useTopVideos(5);

  return (
    <div className="space-y-6">
      {/* KPI row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          icon={PlaySquare}
          label="Total Videos"
          value={statsLoading ? "—" : formatNumber(stats?.total_videos ?? 0)}
          loading={statsLoading}
        />
        <MetricCard
          icon={Eye}
          label="Visualizacoes"
          value={statsLoading ? "—" : formatNumber(stats?.total_views ?? 0)}
          loading={statsLoading}
        />
        <MetricCard
          icon={Heart}
          label="Curtidas"
          value={statsLoading ? "—" : formatNumber(stats?.total_likes ?? 0)}
          loading={statsLoading}
        />
        <MetricCard
          icon={MessageCircle}
          label="Comentarios"
          value={statsLoading ? "—" : formatNumber(stats?.total_comments ?? 0)}
          loading={statsLoading}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Trend chart */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5" />
              Tendencia do canal (30 dias)
            </CardTitle>
            <CardDescription>
              Visualizacoes e inscritos por snapshot diario.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ChannelTrendChart />
          </CardContent>
        </Card>

        {/* Channel info */}
        <ChannelInfoCard
          channelTitle={stats?.channel_title ?? null}
          channelId={stats?.channel_id ?? null}
          totalVideos={stats?.total_videos ?? 0}
          lastSyncedAt={stats?.last_synced_at ?? null}
        />
      </div>

      {/* Top 5 videos */}
      <div>
        <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold">
          <Sparkles className="h-5 w-5" />
          Top 5 videos
        </h2>
        {topLoading ? (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-44 rounded-md" />
            ))}
          </div>
        ) : topVideos.length === 0 ? (
          <Card>
            <CardContent className="p-6 text-sm text-muted-foreground">
              Nenhum video no cache. Sincronize na aba de Videos.
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5">
            {topVideos.map((v) => (
              <VideoCard
                key={v.youtube_video_id}
                variant="compact"
                video={{
                  id: v.youtube_video_id,
                  youtube_video_id: v.youtube_video_id,
                  title: v.title,
                  description: null,
                  thumbnail_url: v.thumbnail_url,
                  published_at: v.published_at,
                  duration: v.duration,
                  privacy_status: null,
                  view_count: v.view_count,
                  like_count: v.like_count,
                  comment_count: v.comment_count,
                  favorite_count: 0,
                  tags: [],
                  category_id: null,
                  uploaded_via_app: v.uploaded_via_app,
                  synced_at: new Date().toISOString(),
                }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
