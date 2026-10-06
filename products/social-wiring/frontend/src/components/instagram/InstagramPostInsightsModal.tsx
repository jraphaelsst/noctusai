/**
 * InstagramPostInsightsModal — a post's insights over time, most relevant
 * metric first. The view is the seed `MediaInsightsModal`; this wrapper only
 * supplies Instagram data: history from
 * GET /api/instagram/accounts/{id}/media/{media_id}/insights/history.
 *
 * Outer gate is hook-free (mounted with `media` toggling null↔set); the inner
 * component owns the hooks and is keyed by media id.
 */
import { useMemo } from "react";

import {
  MediaInsightsModal,
  type MediaInsightsKpi,
  type MediaInsightsSeries,
} from "@noctusai/lib/design-system";
import {
  useInstagramMediaHistory,
  type InstagramMediaItem,
} from "@/hooks/useInstagramInsights";
import { mediaKindLabel, sortMetricsByPriority } from "./insights";

export interface InstagramPostInsightsModalProps {
  accountId: string | null;
  media: InstagramMediaItem | null;
  onClose: () => void;
}

export function InstagramPostInsightsModal(props: InstagramPostInsightsModalProps) {
  if (!props.media) return null;
  return <Content key={props.media.id} {...props} media={props.media} />;
}

function Content({
  accountId,
  media,
  onClose,
}: InstagramPostInsightsModalProps & { media: InstagramMediaItem }) {
  const history = useInstagramMediaHistory(accountId, media.id);
  const data = history.data;

  const metrics = useMemo(() => sortMetricsByPriority(data?.metrics ?? []), [data?.metrics]);

  // series === null only while nothing is on screen yet (initial load / error),
  // so a background refetch never blanks a chart that already has data.
  const series = useMemo<MediaInsightsSeries | null>(() => {
    if (!data) return null;
    return { metrics, points: data.points };
  }, [data, metrics]);

  const kpis = useMemo<MediaInsightsKpi[]>(() => {
    const last = data?.points[data.points.length - 1];
    const fromLatest = media.latest ?? {};
    return metrics.map((m) => {
      const v = last?.[m.key];
      const value =
        typeof v === "number" ? v : typeof fromLatest[m.key] === "number" ? fromLatest[m.key] : null;
      return { key: m.key, label: m.label, value, format: m.format };
    });
  }, [data, metrics, media.latest]);

  const showError = history.isError && !data;

  return (
    <MediaInsightsModal
      open
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      media={{
        title: null,
        caption: media.caption,
        mediaType: mediaKindLabel(media),
        thumbnailUrl: media.thumbnail_url ?? media.media_url,
        publishedAt: media.timestamp,
        permalink: media.permalink,
        permalinkLabel: "Abrir no Instagram",
      }}
      kpis={kpis}
      series={series}
      loading={history.isFetching}
      error={showError ? "Erro ao carregar o histórico deste post." : null}
      onRetry={() => void history.refetch()}
    />
  );
}

export default InstagramPostInsightsModal;
