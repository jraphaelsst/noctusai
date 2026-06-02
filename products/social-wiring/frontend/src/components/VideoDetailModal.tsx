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
 *   - Edit form (title / description / visibility) → PATCH /api/videos/{id}
 *   - "Remover do catálogo" → confirmation dialog → DELETE /api/videos/{id}
 *     (catalog-only removal — does NOT delete the real YouTube video)
 *   - "Excluir permanentemente do YouTube" → two-step typed confirm (irreversible)
 *     → DELETE /api/videos/{id}?purge_remote=true
 *
 * Opens when video row is clicked; closed via onClose().
 * Fetches trend data via useVideoTrend — data flows only when videoId is set.
 */
import { useState } from "react";
import {
  AlertTriangle,
  Edit2,
  ExternalLink,
  Eye,
  Heart,
  Loader2,
  MessageCircle,
  PlaySquare,
  Trash2,
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

import {
  formatDuration,
  type PrivacyStatus,
  type Video,
  useDeleteVideo,
  useUpdateVideo,
} from "@/hooks/useVideos";
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
  /** Called after a successful update so the parent list refreshes. */
  onUpdated?: (updated: Video) => void;
  /** Called after a successful delete so the parent list refreshes. */
  onDeleted?: () => void;
}

export function VideoDetailModal({
  video,
  onClose,
  onUpdated,
  onDeleted,
}: VideoDetailModalProps) {
  if (!video) return null;

  // ─── Edit form state ──────────────────────────────────────────────────────
  const [editOpen, setEditOpen] = useState(false);
  const [editTitle, setEditTitle] = useState(video.title ?? "");
  const [editDescription, setEditDescription] = useState(video.description ?? "");
  const [editPrivacy, setEditPrivacy] = useState<PrivacyStatus>(
    video.privacy_status ?? "private",
  );
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [purgeConfirmOpen, setPurgeConfirmOpen] = useState(false);
  const [purgeConfirmText, setPurgeConfirmText] = useState("");

  const PURGE_CONFIRM_PHRASE = "EXCLUIR PERMANENTEMENTE";

  const { mutate: updateVideo, isPending: isUpdating } = useUpdateVideo({
    onSuccess: (updated) => {
      setEditOpen(false);
      onUpdated?.(updated);
    },
  });

  const { mutate: deleteVideo, isPending: isDeleting } = useDeleteVideo({
    onSuccess: () => {
      setDeleteConfirmOpen(false);
      setPurgeConfirmOpen(false);
      onClose();
      onDeleted?.();
    },
  });

  const handleSave = () => {
    updateVideo({
      youtubeVideoId: video.youtube_video_id,
      body: {
        title: editTitle.trim() || undefined,
        description: editDescription,
        privacy_status: editPrivacy,
      },
    });
  };

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
        {/* Action buttons (edit / delete / close) */}
        <div className="absolute right-3 top-3 z-10 flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => {
              setEditTitle(video.title ?? "");
              setEditDescription(video.description ?? "");
              setEditPrivacy(video.privacy_status ?? "private");
              setEditOpen((v) => !v);
              setDeleteConfirmOpen(false);
              setPurgeConfirmOpen(false);
            }}
            aria-label="Editar video"
            title="Editar"
          >
            <Edit2 className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="text-destructive hover:text-destructive"
            onClick={() => {
              setDeleteConfirmOpen((v) => !v);
              setEditOpen(false);
              setPurgeConfirmOpen(false);
            }}
            aria-label="Remover do catálogo"
            title="Remover do catálogo"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            aria-label="Fechar"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

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

          {/* Edit form (inline, collapsible) */}
          {editOpen && (
            <Card data-testid="edit-form">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Editar video</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-muted-foreground" htmlFor="edit-title">
                    Título
                  </label>
                  <input
                    id="edit-title"
                    type="text"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    maxLength={100}
                    disabled={isUpdating}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                    placeholder="Título do video"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-muted-foreground" htmlFor="edit-description">
                    Descrição
                  </label>
                  <textarea
                    id="edit-description"
                    value={editDescription}
                    onChange={(e) => setEditDescription(e.target.value)}
                    maxLength={5000}
                    rows={4}
                    disabled={isUpdating}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 resize-y"
                    placeholder="Descrição do video"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-muted-foreground" htmlFor="edit-privacy">
                    Visibilidade
                  </label>
                  <select
                    id="edit-privacy"
                    value={editPrivacy}
                    onChange={(e) => setEditPrivacy(e.target.value as PrivacyStatus)}
                    disabled={isUpdating}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                  >
                    <option value="public">Público</option>
                    <option value="unlisted">Não listado</option>
                    <option value="private">Privado</option>
                  </select>
                </div>
                <div className="flex items-center gap-2 pt-1">
                  <Button
                    size="sm"
                    onClick={handleSave}
                    disabled={isUpdating || !editTitle.trim()}
                    aria-label="Salvar alterações"
                  >
                    {isUpdating ? (
                      <>
                        <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                        Salvando…
                      </>
                    ) : (
                      "Salvar"
                    )}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setEditOpen(false)}
                    disabled={isUpdating}
                  >
                    Cancelar
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Delete confirmation panel — catalog-only */}
          {deleteConfirmOpen && (
            <Card
              className="border-destructive/40 bg-destructive/5"
              data-testid="delete-confirm"
            >
              <CardContent className="space-y-3 pt-4">
                <p className="text-sm font-medium">Remover do catálogo?</p>
                <p className="text-sm text-muted-foreground">
                  Isso remove apenas o card local. O video no YouTube{" "}
                  <strong>não é afetado</strong> e pode ser restaurado via
                  "Sincronizar". Os snapshots de histórico são preservados.
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() =>
                      deleteVideo({ youtubeVideoId: video.youtube_video_id })
                    }
                    disabled={isDeleting}
                    aria-label="Confirmar remoção do catálogo"
                  >
                    {isDeleting ? (
                      <>
                        <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                        Removendo…
                      </>
                    ) : (
                      "Remover do catálogo"
                    )}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setDeleteConfirmOpen(false)}
                    disabled={isDeleting}
                  >
                    Cancelar
                  </Button>
                </div>
                {/* Separator + permanent-delete escalation link */}
                <div className="border-t border-destructive/20 pt-3">
                  <button
                    type="button"
                    className="text-xs text-muted-foreground underline underline-offset-2 hover:text-destructive transition-colors"
                    onClick={() => {
                      setDeleteConfirmOpen(false);
                      setPurgeConfirmOpen(true);
                      setPurgeConfirmText("");
                    }}
                    data-testid="open-purge-confirm"
                  >
                    Excluir permanentemente do YouTube (irreversível)
                  </button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Permanent-delete confirmation panel — two-step typed confirm */}
          {purgeConfirmOpen && (
            <Card
              className="border-destructive bg-destructive/10"
              data-testid="purge-confirm"
            >
              <CardContent className="space-y-3 pt-4">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="h-5 w-5 text-destructive mt-0.5 shrink-0" />
                  <div>
                    <p className="text-sm font-semibold text-destructive">
                      Excluir permanentemente do YouTube
                    </p>
                    <p className="text-sm text-muted-foreground mt-1">
                      Esta ação <strong>remove o video real do seu canal no YouTube</strong>.
                      Não existe desfazer, lixeira ou forma de recuperar o video
                      após a exclusão. O video desaparecerá do YouTube Studio,
                      dos analytics e de todos os embeds imediatamente.
                    </p>
                  </div>
                </div>
                <div className="space-y-1">
                  <label
                    className="text-xs font-medium text-muted-foreground"
                    htmlFor="purge-confirm-input"
                  >
                    Para confirmar, digite{" "}
                    <span className="font-mono font-semibold text-destructive select-all">
                      {PURGE_CONFIRM_PHRASE}
                    </span>{" "}
                    abaixo:
                  </label>
                  <input
                    id="purge-confirm-input"
                    type="text"
                    value={purgeConfirmText}
                    onChange={(e) => setPurgeConfirmText(e.target.value)}
                    disabled={isDeleting}
                    autoComplete="off"
                    spellCheck={false}
                    className="w-full rounded-md border border-destructive/60 bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-destructive disabled:opacity-50"
                    placeholder={PURGE_CONFIRM_PHRASE}
                    data-testid="purge-confirm-input"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() =>
                      deleteVideo({
                        youtubeVideoId: video.youtube_video_id,
                        purgeRemote: true,
                      })
                    }
                    disabled={
                      isDeleting ||
                      purgeConfirmText.trim() !== PURGE_CONFIRM_PHRASE
                    }
                    aria-label="Confirmar exclusão permanente do YouTube"
                    data-testid="purge-confirm-submit"
                  >
                    {isDeleting ? (
                      <>
                        <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                        Excluindo…
                      </>
                    ) : (
                      "Excluir permanentemente do YouTube"
                    )}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setPurgeConfirmOpen(false);
                      setPurgeConfirmText("");
                    }}
                    disabled={isDeleting}
                  >
                    Cancelar
                  </Button>
                </div>
              </CardContent>
            </Card>
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
