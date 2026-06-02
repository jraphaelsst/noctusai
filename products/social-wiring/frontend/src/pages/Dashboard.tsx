/**
 * Dashboard — activity overview for the connected channel.
 *
 * Layout (top-to-bottom):
 *   1. VisaoGeralPanel: KPI cards + channel trend chart + top-5 videos
 *   2. Upload queue (live)
 *   3. Recent uploads + delivery status
 *
 * KPI / trend / top-5 are delegated to VisaoGeralPanel so the same component
 * powers both the Dashboard page and the YouTube "Visão geral" tab.
 */
import { useEffect, useState } from "react";
import {
  ExternalLink,
  PlaySquare,
  RefreshCw,
  RotateCw,
} from "lucide-react";
import { toast } from "sonner";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

import { ConnectedAccountSwitcher } from "@/components/ConnectedAccountSwitcher";
import { VisaoGeralPanel } from "@/components/VisaoGeralPanel";
import {
  retryUpload,
  useDashboardStats,
  useQueueState,
  useRecentUploads,
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
  // error + refresh used for the header error card and "Atualizar" button.
  // KPI / trend / top-5 are delegated to VisaoGeralPanel which has its own fetches.
  const { error, refresh } = useDashboardStats();
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

      {/* Live account/client switcher — re-points the KPI/top-videos/recent
          hooks via the shared useActiveAccountStore (same store as the YouTube
          page), so the user can view a different account's data in-place. */}
      <ConnectedAccountSwitcher />

      {error && (
        <Card>
          <CardContent className="p-4 text-sm text-destructive">{error}</CardContent>
        </Card>
      )}

      {/* Channel overview: KPI cards + trend chart + top-5 videos.
          VisaoGeralPanel reads from useDashboardStats, useTopVideos, useChannelTrend
          all defaulting to the active account from useActiveAccountStore. */}
      <VisaoGeralPanel />

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
