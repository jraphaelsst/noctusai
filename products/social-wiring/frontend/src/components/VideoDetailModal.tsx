/**
 * VideoDetailModal — per-video detail sheet.
 *
 * Shows:
 *   - Thumbnail + full title + description
 *   - Metrics row (views / comments / likes)
 *   - Privacy badge + published date
 *   - "Abrir no YouTube" link
 *   - Views-over-time line chart from /api/youtube/videos/{id}/trend
 *     (reuses local ViewsChart, adapted for snapshot points vs cumulative series)
 *   - Empty trend state: "Sem histórico ainda — sincronize para acumular snapshots."
 *
 * Opens when video row is clicked; closed via onClose().
 * Fetches trend data via useVideoTrend — data flows only when videoId is set.
 */
import {
  ExternalLink,
  Eye,
  Heart,
  Loader2,
  MessageCircle,
  PlaySquare,
  X,
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

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import { formatDuration, type Video } from "@/hooks/useVideos";
import { useVideoTrend } from "@/hooks/useVideoTrend";

function fmtNum(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString("pt-BR");
}

// ─── Trend chart (per-video snapshot points — NOT cumulative) ─────────────────

function VideoTrendChart({
  videoId,
}: {
  videoId: string | null;
}) {
  const { data, loading, error } = useVideoTrend(videoId);

  if (loading) {
    return (
      <div className="flex h-48 items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-48 items-center justify-center rounded-md border border-dashed text-sm text-destructive">
        Erro ao carregar histórico: {error}
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground px-4 text-center">
        Sem histórico ainda — sincronize para acumular snapshots.
      </div>
    );
  }

  const chartData = data.map((pt) => ({
    x: new Date(pt.snapshot_date).toLocaleDateString("pt-BR", {
      day: "2-digit",
      month: "short",
    }),
    views: pt.view_count,
    likes: pt.like_count,
    comments: pt.comment_count,
  }));

  return (
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
          <XAxis dataKey="x" fontSize={10} stroke="currentColor" opacity={0.6} />
          <YAxis tickFormatter={fmtNum} fontSize={10} stroke="currentColor" opacity={0.6} />
          <Tooltip
            formatter={(value: number, name: string) => [
              fmtNum(value),
              name === "views" ? "Visualizações" : name === "likes" ? "Curtidas" : "Comentários",
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
            activeDot={{ r: 3 }}
          />
          <Line
            type="monotone"
            dataKey="likes"
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

// ─── Modal ─────────────────────────────────────────────────────────────────────

export interface VideoDetailModalProps {
  video: Video | null;
  onClose: () => void;
}

export function VideoDetailModal({ video, onClose }: VideoDetailModalProps) {
  if (!video) return null;

  const youtubeUrl = `https://www.youtube.com/watch?v=${video.youtube_video_id}`;
  const duration = formatDuration(video.duration);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center sm:items-center bg-black/60 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      aria-label={`Detalhes: ${video.title ?? video.youtube_video_id}`}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative w-full max-w-2xl rounded-xl bg-background shadow-2xl overflow-hidden max-h-[90vh] overflow-y-auto">
        {/* Close button */}
        <Button
          variant="ghost"
          size="icon"
          className="absolute right-3 top-3 z-10"
          onClick={onClose}
          aria-label="Fechar"
        >
          <X className="h-4 w-4" />
        </Button>

        {/* Thumbnail */}
        {video.thumbnail_url && (
          <div className="relative h-48 w-full overflow-hidden bg-muted">
            <img
              src={video.thumbnail_url}
              alt=""
              className="h-full w-full object-cover"
            />
            {duration && (
              <span className="absolute bottom-2 right-2 rounded bg-black/80 px-1.5 py-0.5 text-[11px] font-mono text-white">
                {duration}
              </span>
            )}
          </div>
        )}

        <div className="p-5 space-y-4">
          {/* Title + external link */}
          <div className="flex items-start justify-between gap-3">
            <h2 className="text-lg font-semibold leading-snug">
              {video.title ?? video.youtube_video_id}
            </h2>
            <Button asChild variant="outline" size="sm" className="shrink-0">
              <a href={youtubeUrl} target="_blank" rel="noreferrer">
                <ExternalLink className="mr-1.5 h-3.5 w-3.5" />
                Abrir no YouTube
              </a>
            </Button>
          </div>

          {/* Meta row */}
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            {video.privacy_status && (
              <Badge variant={video.privacy_status === "public" ? "default" : "secondary"}>
                {video.privacy_status === "public"
                  ? "Público"
                  : video.privacy_status === "unlisted"
                  ? "Não listado"
                  : "Privado"}
              </Badge>
            )}
            {video.published_at && (
              <span>
                Publicado em{" "}
                {new Date(video.published_at).toLocaleDateString("pt-BR", {
                  day: "2-digit",
                  month: "long",
                  year: "numeric",
                })}
              </span>
            )}
          </div>

          {/* Metrics */}
          <div className="grid grid-cols-3 gap-3">
            <Card>
              <CardContent className="flex items-center gap-2 p-3">
                <Eye className="h-4 w-4 text-muted-foreground" />
                <div>
                  <div className="text-base font-semibold tabular-nums">
                    {fmtNum(video.view_count)}
                  </div>
                  <div className="text-xs text-muted-foreground">Visualizações</div>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="flex items-center gap-2 p-3">
                <Heart className="h-4 w-4 text-muted-foreground" />
                <div>
                  <div className="text-base font-semibold tabular-nums">
                    {fmtNum(video.like_count)}
                  </div>
                  <div className="text-xs text-muted-foreground">Curtidas</div>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="flex items-center gap-2 p-3">
                <MessageCircle className="h-4 w-4 text-muted-foreground" />
                <div>
                  <div className="text-base font-semibold tabular-nums">
                    {fmtNum(video.comment_count)}
                  </div>
                  <div className="text-xs text-muted-foreground">Comentários</div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Description */}
          {video.description && (
            <div>
              <p className="text-sm text-muted-foreground leading-relaxed line-clamp-4">
                {video.description}
              </p>
            </div>
          )}

          {/* Tags */}
          {video.tags && video.tags.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {video.tags.slice(0, 10).map((tag) => (
                <Badge key={tag} variant="outline" className="text-[11px]">
                  {tag}
                </Badge>
              ))}
              {video.tags.length > 10 && (
                <Badge variant="outline" className="text-[11px]">
                  +{video.tags.length - 10}
                </Badge>
              )}
            </div>
          )}

          {/* Trend chart */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">
                Evolução de visualizações
              </CardTitle>
            </CardHeader>
            <CardContent>
              <VideoTrendChart videoId={video.youtube_video_id} />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
