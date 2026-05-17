/**
 * Videos page — browse the connected channel's full catalog.
 *
 * Default view: card grid. Toggle to a compact table for power users.
 * The "Sync" button hits POST /api/videos/sync; the cache refreshes
 * via the hook's onComplete callback.
 *
 * Filters in Phase 3 (light): app-uploaded toggle + free-text title
 * search (client-side; small N because cache is bounded by channel
 * size). Date-range and privacy-status filters deferred to a later
 * iteration once we see how the page is actually used.
 */
import { useMemo, useState } from "react";
import {
  ExternalLink,
  Eye,
  Grid,
  Heart,
  Loader2,
  MessageCircle,
  RefreshCw,
  Search,
  Sparkles,
  Table as TableIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";

import { VideoCard } from "@/components/VideoCard";
import {
  formatCount,
  formatDuration,
  useVideos,
  useVideoSync,
  youtubeUrl,
  type Video,
} from "@/hooks/useVideos";

type ViewMode = "grid" | "table";

function VideoTableRow({ video }: { video: Video }) {
  return (
    <div className="flex items-center gap-3 border-b py-2 last:border-0 hover:bg-muted/30">
      <div className="relative h-12 w-20 shrink-0 overflow-hidden rounded bg-muted">
        {video.thumbnail_url && (
          <img
            src={video.thumbnail_url}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover"
          />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium">
            {video.title || video.youtube_video_id}
          </span>
          {video.uploaded_via_app && (
            <Badge variant="default" className="shrink-0 gap-1 text-[10px]">
              <Sparkles className="h-3 w-3" />
              App
            </Badge>
          )}
        </div>
        <div className="text-xs text-muted-foreground">
          {video.published_at
            ? new Date(video.published_at).toLocaleDateString("pt-BR")
            : "—"}
          {video.duration && <> · {formatDuration(video.duration)}</>}
        </div>
      </div>
      <div className="hidden items-center gap-4 text-xs text-muted-foreground sm:flex">
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
      <Button asChild variant="ghost" size="icon" className="shrink-0">
        <a
          href={youtubeUrl(video.youtube_video_id)}
          target="_blank"
          rel="noreferrer"
          aria-label="Abrir no YouTube"
        >
          <ExternalLink className="h-4 w-4" />
        </a>
      </Button>
    </div>
  );
}

export default function VideosPage() {
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  const [search, setSearch] = useState("");
  const [appOnly, setAppOnly] = useState(false);

  const { items, totalKnown, loading, loadingMore, hasMore, refresh, loadMore, error } =
    useVideos({ uploadedViaApp: appOnly || undefined });

  const { sync, pending: syncing } = useVideoSync(refresh);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter((v) => (v.title ?? "").toLowerCase().includes(q));
  }, [items, search]);

  return (
    <div className="container max-w-7xl space-y-6 py-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Videos do canal</h1>
          <p className="text-sm text-muted-foreground">
            {totalKnown} videos no cache.{" "}
            <span className="text-xs">
              Use Sincronizar para atualizar com o YouTube.
            </span>
          </p>
        </div>
        <Button onClick={() => sync()} disabled={syncing}>
          {syncing ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="mr-2 h-4 w-4" />
          )}
          Sincronizar
        </Button>
      </div>

      <Card>
        <CardContent className="flex flex-wrap items-center gap-4 p-4">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="pl-10"
              placeholder="Buscar por titulo..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          <div className="flex items-center gap-2">
            <Switch
              id="app-only"
              checked={appOnly}
              onCheckedChange={setAppOnly}
            />
            <Label htmlFor="app-only" className="cursor-pointer">
              Apenas enviados pelo app
            </Label>
          </div>

          <div className="ml-auto flex rounded-md border">
            <Button
              variant={viewMode === "grid" ? "default" : "ghost"}
              size="sm"
              className="rounded-r-none"
              onClick={() => setViewMode("grid")}
              aria-label="Visualizacao em grade"
            >
              <Grid className="h-4 w-4" />
            </Button>
            <Button
              variant={viewMode === "table" ? "default" : "ghost"}
              size="sm"
              className="rounded-l-none border-l"
              onClick={() => setViewMode("table")}
              aria-label="Visualizacao em tabela"
            >
              <TableIcon className="h-4 w-4" />
            </Button>
          </div>
        </CardContent>
      </Card>

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : error ? (
        <Card>
          <CardContent className="p-6 text-sm text-destructive">{error}</CardContent>
        </Card>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 p-12 text-center text-sm text-muted-foreground">
            <Sparkles className="h-8 w-8" />
            {items.length === 0
              ? "Nenhum video no cache. Clique em Sincronizar para buscar do YouTube."
              : "Nenhum video bate com os filtros atuais."}
          </CardContent>
        </Card>
      ) : viewMode === "grid" ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filtered.map((v) => (
            <VideoCard key={v.id} video={v} />
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="p-2">
            {filtered.map((v) => (
              <VideoTableRow key={v.id} video={v} />
            ))}
          </CardContent>
        </Card>
      )}

      {hasMore && !search && (
        <div className="flex justify-center">
          <Button
            variant="outline"
            onClick={loadMore}
            disabled={loadingMore}
          >
            {loadingMore && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Carregar mais
          </Button>
        </div>
      )}
    </div>
  );
}
