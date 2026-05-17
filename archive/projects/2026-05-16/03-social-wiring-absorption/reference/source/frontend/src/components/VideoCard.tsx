/**
 * VideoCard — single video tile for the Videos page card-grid view.
 *
 * Variant: ``compact`` for the Dashboard "top videos" list. Layout
 * differences only — same data shape, same hooks.
 */
import { ExternalLink, Eye, Heart, MessageCircle, Sparkles } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  formatCount,
  formatDuration,
  youtubeUrl,
  type PrivacyStatus,
  type Video,
} from "@/hooks/useVideos";

const PRIVACY_LABELS: Record<PrivacyStatus, string> = {
  public: "Publico",
  unlisted: "Nao listado",
  private: "Privado",
};

interface VideoCardProps {
  video: Video;
  variant?: "default" | "compact";
  onClick?: (video: Video) => void;
}

export function VideoCard({ video, variant = "default", onClick }: VideoCardProps) {
  const compact = variant === "compact";

  return (
    <Card
      className={cn(
        "group cursor-pointer overflow-hidden transition-shadow hover:shadow-md",
        compact && "shadow-none border-0",
      )}
      onClick={() => onClick?.(video)}
    >
      <div className="relative aspect-video w-full bg-muted">
        {video.thumbnail_url ? (
          <img
            src={video.thumbnail_url}
            alt={video.title ?? video.youtube_video_id}
            loading="lazy"
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
            Sem thumbnail
          </div>
        )}
        {video.duration && (
          <span className="absolute bottom-2 right-2 rounded bg-black/80 px-1.5 py-0.5 text-xs font-medium text-white">
            {formatDuration(video.duration)}
          </span>
        )}
        {video.uploaded_via_app && (
          <Badge
            variant="default"
            className="absolute left-2 top-2 gap-1 bg-primary/90 text-[10px]"
          >
            <Sparkles className="h-3 w-3" />
            App
          </Badge>
        )}
      </div>

      <CardContent className={cn("space-y-2 p-3", compact && "p-2")}>
        <div className="flex items-start justify-between gap-2">
          <h3
            className={cn(
              "line-clamp-2 text-sm font-medium leading-snug",
              compact && "text-xs",
            )}
          >
            {video.title || video.youtube_video_id}
          </h3>
          {video.privacy_status && !compact && (
            <Badge variant="outline" className="shrink-0 text-[10px]">
              {PRIVACY_LABELS[video.privacy_status]}
            </Badge>
          )}
        </div>

        {!compact && (
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <Eye className="h-3 w-3" />
              {formatCount(video.view_count)}
            </span>
            <span className="inline-flex items-center gap-1">
              <Heart className="h-3 w-3" />
              {formatCount(video.like_count)}
            </span>
            <span className="inline-flex items-center gap-1">
              <MessageCircle className="h-3 w-3" />
              {formatCount(video.comment_count)}
            </span>
          </div>
        )}

        {compact && (
          <div className="text-[11px] text-muted-foreground">
            {formatCount(video.view_count)} views
          </div>
        )}

        {!compact && (
          <Button
            asChild
            variant="ghost"
            size="sm"
            className="h-7 w-full text-xs"
            onClick={(e) => e.stopPropagation()}
          >
            <a href={youtubeUrl(video.youtube_video_id)} target="_blank" rel="noreferrer">
              Abrir no YouTube
              <ExternalLink className="ml-1 h-3 w-3" />
            </a>
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
