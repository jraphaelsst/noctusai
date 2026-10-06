/**
 * InstagramPostCard — one post tile: thumbnail, kind + date, and the six
 * headline metrics (Curtidas, Comentários, Compartilhamentos, Visualizações,
 * Alcance, Salvamentos). A metric Meta did not serve renders "—", never 0.
 * Clicking opens the insights modal (it is a button, not a link).
 */
import { Film, Image as ImageIcon, Images } from "lucide-react";

import { formatMediaInsightValue } from "@noctusai/lib/design-system";
import type { InstagramMediaItem } from "@/hooks/useInstagramInsights";
import { formatPostDate, mediaKindLabel } from "./insights";

function Fallback({ item }: { item: InstagramMediaItem }) {
  const Icon =
    item.media_type === "VIDEO" ? Film : item.media_type === "CAROUSEL_ALBUM" ? Images : ImageIcon;
  return (
    <div className="flex h-full w-full items-center justify-center text-muted-foreground/60">
      <Icon className="h-8 w-8" strokeWidth={1.5} />
    </div>
  );
}

export function InstagramPostCard({
  item,
  onOpen,
}: {
  item: InstagramMediaItem;
  onOpen: (item: InstagramMediaItem) => void;
}) {
  const latest = item.latest ?? {};
  const stats: Array<[string, number | null | undefined]> = [
    ["Curtidas", item.like_count ?? latest.likes],
    ["Comentários", item.comments_count ?? latest.comments],
    ["Compartilhamentos", latest.shares],
    ["Visualizações", latest.views],
    ["Alcance", latest.reach],
    ["Salvamentos", latest.saved],
  ];
  const image = item.thumbnail_url ?? item.media_url;
  return (
    <button
      type="button"
      onClick={() => onOpen(item)}
      data-testid="ig-post-card"
      aria-label={`Ver métricas do post de ${formatPostDate(item.timestamp)}`}
      className="group flex flex-col overflow-hidden rounded-lg border bg-card text-left transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="aspect-square w-full overflow-hidden bg-muted">
        {image ? (
          <img
            src={image}
            alt={item.caption ?? "Post do Instagram"}
            className="h-full w-full object-cover transition-opacity group-hover:opacity-90"
            loading="lazy"
          />
        ) : (
          <Fallback item={item} />
        )}
      </div>
      <div className="space-y-2 p-3">
        <div className="flex items-center justify-between text-xs">
          <span className="rounded bg-muted px-1.5 py-0.5 font-medium">{mediaKindLabel(item)}</span>
          <span className="text-muted-foreground">{formatPostDate(item.timestamp)}</span>
        </div>
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
          {stats.map(([label, value]) => (
            <div key={label} className="flex items-baseline justify-between gap-2">
              <dt className="truncate text-muted-foreground">{label}</dt>
              <dd className="font-medium tabular-nums" data-testid={`ig-post-stat-${label}`}>
                {formatMediaInsightValue(value ?? null, "compact")}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </button>
  );
}

export default InstagramPostCard;
