/**
 * ChannelContentTable — YouTube Studio "Conteúdo do canal" inspired table.
 *
 * Columns (all honest, no fabricated data):
 *   Vídeo       — thumbnail with duration badge + title + description preview
 *   Visibilidade — badge from privacy_status (Público / Não listado / Privado)
 *   Data        — published_at (pt-BR) with "Publicado" sub-line
 *   Visualizações — view_count (pt-BR thousand separator)
 *   Comentários  — comment_count
 *   Curtidas     — like_count
 *
 * NOTE: YouTube no longer exposes dislike counts publicly; "Não gostei" column
 * is intentionally OMITTED. "Restrições" is also omitted — we don't capture
 * that data. Honest columns only.
 *
 * Sorting: header clicks on Data/Visualizações toggle asc/desc client-side.
 * Pagination: "Carregar mais" button uses cursor from the parent hook.
 * Row click: calls onRowClick(video) so the parent can open the detail modal.
 *
 * Usage:
 *   <ChannelContentTable
 *     items={items}
 *     loading={loading}
 *     loadingMore={loadingMore}
 *     hasMore={hasMore}
 *     onLoadMore={loadMore}
 *     onRowClick={(v) => setSelectedVideo(v)}
 *   />
 */
import { useMemo, useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  ChevronsUpDown,
  Eye,
  Globe,
  Heart,
  Lock,
  Loader2,
  MessageCircle,
  Link as LinkIcon,
  PlaySquare,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDuration, type Video } from "@/hooks/useVideos";

// ─── Privacy badge ────────────────────────────────────────────────────────────

type PrivacyStatus = "public" | "unlisted" | "private" | null | undefined;

const PRIVACY_CONFIG: Record<
  string,
  { label: string; icon: React.ElementType; variant: "default" | "secondary" | "outline" | "destructive" }
> = {
  public: { label: "Público", icon: Globe, variant: "default" },
  unlisted: { label: "Não listado", icon: LinkIcon, variant: "secondary" },
  private: { label: "Privado", icon: Lock, variant: "outline" },
};

function PrivacyBadge({ status }: { status: PrivacyStatus }) {
  const cfg = status ? PRIVACY_CONFIG[status] : null;
  if (!cfg) {
    return (
      <Badge variant="outline" className="gap-1 text-[11px]">
        <LinkIcon className="h-3 w-3" />
        Não listado
      </Badge>
    );
  }
  const Icon = cfg.icon;
  return (
    <Badge variant={cfg.variant} className="gap-1 text-[11px]">
      <Icon className="h-3 w-3" />
      {cfg.label}
    </Badge>
  );
}

// ─── Duration badge ───────────────────────────────────────────────────────────

function DurationBadge({ duration }: { duration?: string | null }) {
  const text = formatDuration(duration);
  if (!text) return null;
  return (
    <span className="absolute bottom-1 right-1 rounded bg-black/80 px-1 py-0.5 text-[10px] font-mono text-white">
      {text}
    </span>
  );
}

// ─── Number formatter (pt-BR thousands separator) ─────────────────────────────

function fmtNum(n: number): string {
  return n.toLocaleString("pt-BR");
}

// ─── Sort types ───────────────────────────────────────────────────────────────

type SortKey = "published_at" | "view_count" | null;
type SortDir = "asc" | "desc";

function SortIcon({
  column,
  active,
  dir,
}: {
  column: string;
  active: boolean;
  dir: SortDir;
}) {
  if (!active) return <ChevronsUpDown className="ml-1 inline h-3.5 w-3.5 text-muted-foreground" />;
  if (dir === "asc") return <ChevronUp className="ml-1 inline h-3.5 w-3.5" />;
  return <ChevronDown className="ml-1 inline h-3.5 w-3.5" />;
}

// ─── Column header ────────────────────────────────────────────────────────────

function SortableHeader({
  label,
  colKey,
  sortKey,
  sortDir,
  onSort,
}: {
  label: string;
  colKey: SortKey;
  sortKey: SortKey;
  sortDir: SortDir;
  onSort: (k: SortKey) => void;
}) {
  if (!colKey) return <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">{label}</th>;
  return (
    <th
      className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide cursor-pointer select-none hover:text-foreground transition-colors"
      onClick={() => onSort(colKey)}
      aria-sort={sortKey === colKey ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
    >
      {label}
      <SortIcon column={colKey} active={sortKey === colKey} dir={sortDir} />
    </th>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export interface ChannelContentTableProps {
  items: Video[];
  loading?: boolean;
  loadingMore?: boolean;
  hasMore?: boolean;
  onLoadMore?: () => void;
  onRowClick?: (video: Video) => void;
  /** Empty-state message when items is empty + not loading */
  emptyMessage?: string;
}

export function ChannelContentTable({
  items,
  loading = false,
  loadingMore = false,
  hasMore = false,
  onLoadMore,
  onRowClick,
  emptyMessage = "Nenhum vídeo no cache. Clique em Sincronizar.",
}: ChannelContentTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>(null);
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  function handleSort(key: SortKey) {
    if (!key) return;
    if (sortKey === key) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  const sorted = useMemo(() => {
    if (!sortKey) return items;
    return [...items].sort((a, b) => {
      let cmp = 0;
      if (sortKey === "published_at") {
        const at = a.published_at ? new Date(a.published_at).getTime() : 0;
        const bt = b.published_at ? new Date(b.published_at).getTime() : 0;
        cmp = at - bt;
      } else if (sortKey === "view_count") {
        cmp = a.view_count - b.view_count;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [items, sortKey, sortDir]);

  if (loading) {
    return (
      <div className="space-y-2 p-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-16 rounded-md" />
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-16 text-center text-sm text-muted-foreground">
        <PlaySquare className="h-10 w-10" />
        <p>{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-separate border-spacing-0 text-sm">
        <thead>
          <tr className="border-b">
            {/* Non-sortable video column */}
            <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide w-[40%]">
              Vídeo
            </th>
            <SortableHeader
              label="Visibilidade"
              colKey={null}
              sortKey={sortKey}
              sortDir={sortDir}
              onSort={handleSort}
            />
            <SortableHeader
              label="Data"
              colKey="published_at"
              sortKey={sortKey}
              sortDir={sortDir}
              onSort={handleSort}
            />
            <SortableHeader
              label="Visualizações"
              colKey="view_count"
              sortKey={sortKey}
              sortDir={sortDir}
              onSort={handleSort}
            />
            <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Comentários
            </th>
            <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Curtidas
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((video) => (
            <VideoRow key={video.id} video={video} onRowClick={onRowClick} />
          ))}
        </tbody>
      </table>

      {hasMore && (
        <div className="flex justify-center py-4">
          <Button variant="outline" size="sm" onClick={onLoadMore} disabled={loadingMore}>
            {loadingMore && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Carregar mais
          </Button>
        </div>
      )}
    </div>
  );
}

// ─── Row ──────────────────────────────────────────────────────────────────────

function VideoRow({
  video,
  onRowClick,
}: {
  video: Video;
  onRowClick?: (v: Video) => void;
}) {
  return (
    <tr
      className="border-b last:border-0 hover:bg-muted/40 transition-colors cursor-pointer group"
      onClick={() => onRowClick?.(video)}
      tabIndex={0}
      role="button"
      aria-label={`Abrir detalhes de ${video.title ?? video.youtube_video_id}`}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onRowClick?.(video);
      }}
    >
      {/* Vídeo column: thumbnail + duration badge + title + description */}
      <td className="px-3 py-3 align-top">
        <div className="flex items-start gap-3">
          <div className="relative h-14 w-24 shrink-0 overflow-hidden rounded bg-muted">
            {video.thumbnail_url ? (
              <img
                src={video.thumbnail_url}
                alt=""
                loading="lazy"
                className="h-full w-full object-cover"
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center">
                <PlaySquare className="h-5 w-5 text-muted-foreground" />
              </div>
            )}
            <DurationBadge duration={video.duration} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <span className="line-clamp-2 text-sm font-medium leading-snug group-hover:text-primary transition-colors">
                {video.title ?? video.youtube_video_id}
              </span>
              {video.uploaded_via_app && (
                <Badge variant="default" className="shrink-0 gap-1 text-[10px] py-0">
                  <Sparkles className="h-2.5 w-2.5" />
                  App
                </Badge>
              )}
            </div>
            {video.description && (
              <p className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">
                {video.description}
              </p>
            )}
          </div>
        </div>
      </td>

      {/* Visibilidade */}
      <td className="px-3 py-3 align-middle">
        <PrivacyBadge status={video.privacy_status} />
      </td>

      {/* Data */}
      <td className="px-3 py-3 align-middle whitespace-nowrap">
        {video.published_at ? (
          <>
            <div className="text-sm">
              {new Date(video.published_at).toLocaleDateString("pt-BR")}
            </div>
            <div className="text-xs text-muted-foreground">Publicado</div>
          </>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>

      {/* Visualizações */}
      <td className="px-3 py-3 align-middle">
        <span className="inline-flex items-center gap-1 tabular-nums">
          <Eye className="h-3.5 w-3.5 text-muted-foreground" />
          {fmtNum(video.view_count)}
        </span>
      </td>

      {/* Comentários */}
      <td className="px-3 py-3 align-middle">
        <span className="inline-flex items-center gap-1 tabular-nums">
          <MessageCircle className="h-3.5 w-3.5 text-muted-foreground" />
          {fmtNum(video.comment_count)}
        </span>
      </td>

      {/* Curtidas — dislike count intentionally omitted (YouTube no longer
          exposes dislikes publicly; showing fake 0 would be dishonest) */}
      <td className="px-3 py-3 align-middle">
        <span className="inline-flex items-center gap-1 tabular-nums">
          <Heart className="h-3.5 w-3.5 text-muted-foreground" />
          {fmtNum(video.like_count)}
        </span>
      </td>
    </tr>
  );
}
