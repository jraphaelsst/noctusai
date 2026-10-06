/**
 * VideoDetailModal — per-video detail sheet (YouTube).
 *
 * The view (header, KPIs, history chart with metric selector, loading / empty /
 * error states, permalink) is the seed's `MediaInsightsModal`; this file only
 * supplies the YouTube data and the product-owned actions, passed through the
 * modal's `extra` slot:
 *   - Privacy badge + tags
 *   - Edit form (title / description / visibility) → PATCH /api/videos/{id}
 *   - "Remover do catálogo" → confirmation → DELETE /api/videos/{id}
 *     (catalog-only removal — does NOT delete the real YouTube video)
 *   - "Excluir permanentemente do YouTube" → two-step typed confirm (irreversible)
 *     → DELETE /api/videos/{id}?purge_remote=true
 *
 * Trend data comes from useVideoTrend (/api/youtube/videos/{id}/trend) —
 * fetched only while a video is selected.
 */
import { useMemo, useState } from "react";
import { AlertTriangle, Edit2, Loader2, Trash2 } from "lucide-react";
import {
  MediaInsightsModal,
  type MediaInsightsKpi,
  type MediaInsightsSeries,
} from "@noctusai/lib/design-system";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import {
  formatDuration,
  type PrivacyStatus,
  type Video,
  useDeleteVideo,
  useUpdateVideo,
} from "@/hooks/useVideos";
import { useVideoTrend } from "@/hooks/useVideoTrend";

const TREND_METRICS: MediaInsightsSeries["metrics"] = [
  { key: "views", label: "Visualizações", format: "compact" },
  { key: "likes", label: "Curtidas", format: "compact" },
  { key: "comments", label: "Comentários", format: "compact" },
];

// ─── Modal ─────────────────────────────────────────────────────────────────────

export interface VideoDetailModalProps {
  video: Video | null;
  onClose: () => void;
  /** Called after a successful update so the parent list refreshes. */
  onUpdated?: (updated: Video) => void;
  /** Called after a successful delete so the parent list refreshes. */
  onDeleted?: () => void;
  /**
   * Open the modal straight into a mode — set by a row's inline Edit/Delete
   * icon. `null`/omitted = plain view (the row-click default).
   */
  initialMode?: "edit" | "delete" | null;
}

/**
 * Outer gate — intentionally hook-free. The parent mounts this unconditionally
 * with `video` toggling null↔set; if the hooks lived here, that toggle would
 * change the hook count between renders of the SAME mounted component and
 * violate the Rules of Hooks ("Rendered more hooks than during the previous
 * render"). Keeping hooks in the inner component (mounted only when a video
 * exists, and keyed by video id so switching videos resets form state) makes
 * the hook count stable for every mounted instance.
 */
export function VideoDetailModal(props: VideoDetailModalProps) {
  if (!props.video) return null;
  return (
    <VideoDetailContent
      key={props.video.youtube_video_id}
      {...props}
      video={props.video}
    />
  );
}

function VideoDetailContent({
  video,
  onClose,
  onUpdated,
  onDeleted,
  initialMode = null,
}: VideoDetailModalProps & { video: Video }) {
  // ─── Edit form state ──────────────────────────────────────────────────────
  const [editOpen, setEditOpen] = useState(initialMode === "edit");
  const [editTitle, setEditTitle] = useState(video.title ?? "");
  const [editDescription, setEditDescription] = useState(video.description ?? "");
  const [editPrivacy, setEditPrivacy] = useState<PrivacyStatus>(
    video.privacy_status ?? "private",
  );
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(initialMode === "delete");
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

  const { data: trend, loading: trendLoading, error: trendError, refetch } = useVideoTrend(
    video.youtube_video_id,
  );
  const kpis: MediaInsightsKpi[] = [
    { key: "views", label: "Visualizações", value: video.view_count, format: "compact" },
    { key: "likes", label: "Curtidas", value: video.like_count, format: "compact" },
    { key: "comments", label: "Comentários", value: video.comment_count, format: "compact" },
  ];
  // series === null only while there is nothing to show yet (loading / error),
  // so the modal's two-signal loading never blanks a chart that has data.
  const series = useMemo<MediaInsightsSeries | null>(() => {
    if (trend.length === 0 && (trendLoading || trendError)) return null;
    return {
      metrics: TREND_METRICS,
      points: trend.map((pt) => ({
        date: pt.snapshot_date,
        views: pt.view_count,
        likes: pt.like_count,
        comments: pt.comment_count,
      })),
    };
  }, [trend, trendLoading, trendError]);

  const extra = (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {video.privacy_status && (
          <Badge variant={video.privacy_status === "public" ? "default" : "secondary"}>
            {video.privacy_status === "public"
              ? "Público"
              : video.privacy_status === "unlisted"
              ? "Não listado"
              : "Privado"}
          </Badge>
        )}
        {video.tags && video.tags.length > 0 && (
          <>
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
          </>
        )}
        <div className="ml-auto flex items-center gap-1">
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
        </div>
      </div>

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

    </div>
  );

  return (
    <MediaInsightsModal
      open
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      media={{
        title: video.title ?? video.youtube_video_id,
        caption: video.description,
        mediaType: duration ? `Vídeo · ${duration}` : "Vídeo",
        thumbnailUrl: video.thumbnail_url,
        publishedAt: video.published_at,
        permalink: youtubeUrl,
        permalinkLabel: "Abrir no YouTube",
      }}
      kpis={kpis}
      series={series}
      loading={trendLoading}
      error={trendError ? `Erro ao carregar histórico: ${trendError}` : null}
      onRetry={refetch}
      extra={extra}
    />
  );
}
