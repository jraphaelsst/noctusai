/**
 * Dashboard — analytics + activity overview for the connected channel.
 *
 * Layout (top-to-bottom):
 *   1. KPI cards row (Total Videos / Views / Likes / Comments)
 *   2. Cumulative views chart (recharts; uses top-50 cached videos)
 *   3. Top 5 videos panel (compact card grid)
 *   4. Recent uploads + delivery status panel
 *   5. Connected channel card (right column when wide)
 *
 * All read-only; data sourced from `/api/dashboard/*` endpoints which
 * read from `video_cache` + `upload_jobs` + `notification_log`. Zero
 * YouTube API calls — sync is explicit (Videos page → Sync button).
 */
import { useEffect, useState } from "react";
import {
  Activity,
  CheckCircle2,
  CircleAlert,
  Eye,
  ExternalLink,
  Heart,
  MessageCircle,
  PlaySquare,
  RefreshCw,
  RotateCw,
  Sparkles,
} from "lucide-react";
import { toast } from "sonner";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

import { MetricCard } from "@/components/MetricCard";
import { VideoCard } from "@/components/VideoCard";
import { ViewsChart } from "@/components/ViewsChart";
import {
  formatNumber,
  retryUpload,
  useDashboardStats,
  useQueueState,
  useRecentUploads,
  useTopVideos,
  type NotificationDeliveryStatus,
  type QueueEntry,
  type RecentUpload,
} from "@/hooks/useDashboard";

const DELIVERY_BADGE: Record<
  NotificationDeliveryStatus,
  { label: string; variant: "default" | "secondary" | "destructive" | "outline" }
> = {
  none: { label: "Sem notificacao", variant: "outline" },
  all_sent: { label: "Notificado", variant: "default" },
  partial: { label: "Parcial", variant: "secondary" },
  all_failed: { label: "Falha de envio", variant: "destructive" },
};

function ChannelCard({
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
            ? "OAuth ativo. Sincronize a pagina de Videos para atualizar o cache."
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

function RecentUploadsRow({
  upload,
  onRetried,
}: {
  upload: RecentUpload;
  onRetried: () => void;
}) {
  const badge = DELIVERY_BADGE[upload.notification_status];
  const url = upload.youtube_video_id
    ? `https://www.youtube.com/watch?v=${upload.youtube_video_id}`
    : null;
  const [retrying, setRetrying] = useState(false);
  const isFailed = upload.status === "failed";
  const isProcessing = upload.status === "processing";

  const handleRetry = async () => {
    setRetrying(true);
    try {
      await retryUpload(upload.job_id);
      toast.success("Re-enviado para a fila");
      onRetried();
    } catch (err: any) {
      toast.error(err?.message ?? "Falha ao re-enviar");
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div className="flex items-center justify-between gap-4 border-b py-3 last:border-0">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 truncate text-sm font-medium">
          {upload.product_code && (
            <Badge variant="outline" className="shrink-0 text-[10px] font-mono">
              {upload.product_code}
            </Badge>
          )}
          {upload.title}
        </div>
        <div className="truncate text-xs text-muted-foreground">
          {new Date(upload.created_at).toLocaleString("pt-BR")} · {upload.status}
        </div>
        {url && (
          <div className="truncate text-xs">
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="text-primary hover:underline"
            >
              {url}
            </a>
          </div>
        )}
        {upload.error_message && (
          <div className="truncate text-xs text-destructive">
            {upload.error_message}
          </div>
        )}
      </div>
      <div className="flex items-center gap-2">
        {isProcessing && (
          <Badge variant="secondary" className="whitespace-nowrap">
            ⏳ processando no YouTube
          </Badge>
        )}
        <Badge variant={badge.variant}>{badge.label}</Badge>
        {upload.notification_attempts > 0 && (
          <span className="text-xs tabular-nums text-muted-foreground">
            {upload.notification_succeeded}/{upload.notification_attempts}
          </span>
        )}
        {isFailed && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => void handleRetry()}
            disabled={retrying}
            aria-label="Tentar de novo"
          >
            <RotateCw className={`mr-1 h-4 w-4 ${retrying ? "animate-spin" : ""}`} />
            {retrying ? "Enviando…" : "Tentar de novo"}
          </Button>
        )}
        {url && (
          <Button asChild variant="ghost" size="icon">
            <a href={url} target="_blank" rel="noreferrer" aria-label="Abrir no YouTube">
              <ExternalLink className="h-4 w-4" />
            </a>
          </Button>
        )}
      </div>
    </div>
  );
}

function QueueRow({ entry, max }: { entry: QueueEntry; max: number }) {
  const inFlight = entry.position <= max;
  return (
    <div className="flex items-center gap-3 border-b py-2 last:border-0">
      <Badge variant={inFlight ? "default" : "outline"} className="font-mono">
        {entry.position}
      </Badge>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 truncate text-sm">
          {entry.product_code && (
            <Badge variant="outline" className="shrink-0 text-[10px] font-mono">
              {entry.product_code}
            </Badge>
          )}
          <span className="truncate">{entry.title ?? "(sem título)"}</span>
        </div>
        <div className="truncate text-xs text-muted-foreground">
          {entry.status ?? "queued"} · enfileirado{" "}
          {new Date(entry.enqueued_at * 1000).toLocaleTimeString("pt-BR")}
        </div>
      </div>
      {inFlight && (
        <Badge variant="secondary" className="whitespace-nowrap">
          em execução
        </Badge>
      )}
    </div>
  );
}

export default function Dashboard() {
  const { data: stats, loading: statsLoading, error, refresh } = useDashboardStats();
  const { data: topVideos, loading: topLoading } = useTopVideos(5);
  // Wider window for the chart so the cumulative view-count line has body.
  const { data: chartVideos } = useTopVideos(50);
  const { data: recent, loading: recentLoading, refresh: refreshRecent } = useRecentUploads(10);
  const { data: queueState } = useQueueState(5000);

  // Refresh recent uploads when the window regains focus — a freshly
  // notified job from another tab should show up promptly.
  useEffect(() => {
    const onFocus = () => void refreshRecent();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refreshRecent]);

  return (
    <div className="container max-w-7xl space-y-6 py-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex items-center gap-3">
          <PlaySquare className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-semibold">Dashboard</h1>
            <p className="text-sm text-muted-foreground">
              Visao geral do canal + atividade recente.
            </p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={() => void refresh()}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Atualizar
        </Button>
      </div>

      {error && (
        <Card>
          <CardContent className="p-4 text-sm text-destructive">{error}</CardContent>
        </Card>
      )}

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
          label="Likes"
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
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5" />
              Visualizacoes acumuladas
            </CardTitle>
            <CardDescription>
              Soma cumulativa por data de publicacao (top 50 do cache).
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ViewsChart videos={chartVideos} />
          </CardContent>
        </Card>

        <ChannelCard
          channelTitle={stats?.channel_title ?? null}
          channelId={stats?.channel_id ?? null}
          totalVideos={stats?.total_videos ?? 0}
          lastSyncedAt={stats?.last_synced_at ?? null}
        />
      </div>

      {/* Top videos */}
      <div>
        <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold">
          <Sparkles className="h-5 w-5" />
          Top 5 videos
        </h2>
        {topLoading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-44 rounded-md" />
            ))}
          </div>
        ) : topVideos.length === 0 ? (
          <Card>
            <CardContent className="p-6 text-sm text-muted-foreground">
              Nenhum video no cache. Sincronize na pagina de Videos.
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5">
            {topVideos.map((v) => (
              <VideoCard
                key={v.youtube_video_id}
                variant="compact"
                video={{
                  id: v.youtube_video_id,        // VideoCard treats this opaquely
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

      {/* Upload queue — live "what's in the pipeline" panel */}
      {queueState && queueState.total > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Fila de upload</CardTitle>
            <CardDescription>
              {queueState.total} {queueState.total === 1 ? "upload" : "uploads"} na
              fila · max {queueState.max_concurrent} em paralelo · atualiza a
              cada 5s.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div>
              {queueState.entries.map((entry) => (
                <QueueRow
                  key={entry.job_id}
                  entry={entry}
                  max={queueState.max_concurrent}
                />
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Recent uploads */}
      <Card>
        <CardHeader>
          <CardTitle>Envios recentes</CardTitle>
          <CardDescription>
            Os 10 ultimos jobs de upload + status de entrega das notificacoes.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {recentLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-12 rounded" />
              ))}
            </div>
          ) : recent.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-6 text-center text-sm text-muted-foreground">
              <PlaySquare className="h-8 w-8" />
              Nenhum envio ainda. Va em Upload para enviar seu primeiro video.
            </div>
          ) : (
            <div>
              {recent.map((u) => (
                <RecentUploadsRow
                  key={u.job_id}
                  upload={u}
                  onRetried={() => void refreshRecent()}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
