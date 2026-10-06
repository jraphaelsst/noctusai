/**
 * MediaInsightsModal — product-agnostic "one post / one video" insights sheet.
 *
 * Generalizes social-wiring's `VideoDetailModal` (YouTube) + `AdDetalheModal`
 * so YouTube, Instagram, Meta and CoreStudio share ONE modal instead of N
 * hand-rolled ones. The product owns data fetching + any actions (edit /
 * delete / boost...) — the modal only renders:
 *
 *   header   thumbnail · title · clamped-expandable caption · type + date ·
 *            permalink button (label comes from props)
 *   KPIs     StatTileRow of `kpis` (caller pre-sorts by relevance)
 *   `extra`  product slot (edit form, delete panel, ...)
 *   chart    metric chips (multi-select) + LineChart over `series.points`
 *            with a date x-axis; default = the first 2 metrics that have data
 *
 * Built on the Radix dialog (`ui/radix-dialog`, a real focus trap + Escape +
 * aria-labelledby/-describedby) rather than the inline `ui/Dialog`, which has
 * no focus trap. Loading follows the two-signal rule
 * (`KB § PATTERNS/frontend/lying-loading-state.md`): skeleton only when
 * `loading && !series`; a refetch over existing data shows a quiet
 * "Atualizando…" and keeps the chart mounted.
 */
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ExternalLink } from "lucide-react";
import { cn } from "../../utils";
import { ChartCard } from "../charts/ChartCard";
import { LineChart } from "../charts/LineChart";
import { StatTile } from "../charts/StatTile";
import { StatTileRow } from "../charts/StatTileRow";
import { formatCompactNumber, formatPercent } from "../charts/formatters";
import {
  Dialog as RadixDialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "../ui/radix-dialog";

export type MediaInsightsFormat = "int" | "compact" | "percent" | "duration_ms";

export interface MediaInsightsMedia {
  title?: string | null;
  caption?: string | null;
  /** Free label, e.g. "Reel", "Vídeo", "Short". */
  mediaType?: string | null;
  thumbnailUrl?: string | null;
  /** ISO date/datetime. */
  publishedAt?: string | null;
  permalink?: string | null;
  /** e.g. "Abrir no Instagram" / "Abrir no YouTube". */
  permalinkLabel?: string;
}

export interface MediaInsightsKpi {
  key: string;
  label: string;
  /** `null` renders "—" (never a false 0). */
  value: number | null;
  format?: MediaInsightsFormat;
}

export interface MediaInsightsMetric {
  key: string;
  label: string;
  format?: MediaInsightsFormat;
}

export interface MediaInsightsSeriesPoint {
  /** "YYYY-MM-DD" (or ISO datetime). */
  date: string;
  [metricKey: string]: number | string | null | undefined;
}

export interface MediaInsightsSeries {
  points: MediaInsightsSeriesPoint[];
  /** Priority-ordered (most relevant first). */
  metrics: MediaInsightsMetric[];
}

export interface MediaInsightsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  media: MediaInsightsMedia;
  kpis: MediaInsightsKpi[];
  series: MediaInsightsSeries | null;
  /** Any in-flight fetch (initial or refetch) — the modal derives both signals. */
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  /** Product slot rendered between the KPIs and the chart. */
  extra?: ReactNode;
  className?: string;
}

export const MEDIA_INSIGHTS_EMPTY_MESSAGE =
  "Sem histórico ainda — os dados começam a ser coletados diariamente";

const DEFAULT_SELECTED = 2;
const CAPTION_EXPAND_THRESHOLD = 140;

function formatDurationMs(ms: number): string {
  const totalSec = Math.round(ms / 1000);
  if (totalSec < 60) return `${totalSec} s`;
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${String(s).padStart(2, "0")} min`;
}

/** Format a metric value; `null`/non-finite => "—". */
export function formatMediaInsightValue(
  value: number | null | undefined,
  format: MediaInsightsFormat = "compact",
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  switch (format) {
    case "int":
      return value.toLocaleString("pt-BR");
    case "percent":
      return formatPercent(value);
    case "duration_ms":
      return formatDurationMs(value);
    default:
      return formatCompactNumber(value);
  }
}

/** "2026-05-01" -> "01/05" without a Date round-trip (no timezone shift). */
function shortDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${m[3]}/${m[2]}` : iso;
}

function formatPublished(iso: string): string | null {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" });
}

function hasData(points: MediaInsightsSeriesPoint[], key: string): boolean {
  return points.some((p) => typeof p[key] === "number");
}

export function MediaInsightsModal({
  open,
  onOpenChange,
  media,
  kpis,
  series,
  loading = false,
  error = null,
  onRetry,
  extra,
  className,
}: MediaInsightsModalProps) {
  const [captionOpen, setCaptionOpen] = useState(false);
  useEffect(() => setCaptionOpen(false), [media.caption, open]);

  const metrics = series?.metrics ?? [];
  const points = series?.points ?? [];
  const signature = metrics.map((m) => m.key).join("|");

  // Default = first 2 priority metrics that actually have data (else first 2).
  const defaultKeys = useMemo(() => {
    const withData = metrics.filter((m) => hasData(points, m.key));
    return (withData.length > 0 ? withData : metrics).slice(0, DEFAULT_SELECTED).map((m) => m.key);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, points]);
  const [override, setOverride] = useState<{ sig: string; keys: string[] } | null>(null);
  const selectedKeys = override && override.sig === signature ? override.keys : defaultKeys;

  const toggle = (key: string) => {
    const next = selectedKeys.includes(key)
      ? selectedKeys.filter((k) => k !== key)
      : metrics.map((m) => m.key).filter((k) => k === key || selectedKeys.includes(k));
    if (next.length === 0) return; // always keep >= 1 series drawn
    setOverride({ sig: signature, keys: next });
  };

  // Two signals — never a bare isLoading.
  const hasSeries = series !== null;
  const showSkeleton = loading && !hasSeries;
  const isRefreshing = loading && hasSeries;

  const selectedMetrics = metrics.filter((m) => selectedKeys.includes(m.key));
  const primaryFormat = selectedMetrics[0]?.format ?? "compact";
  const chartData = useMemo(
    () => points.map((p) => ({ ...p, __label: shortDate(String(p.date)) })),
    [points],
  );

  const title = media.title?.trim() || media.caption?.trim()?.split("\n")[0] || "Detalhes da mídia";
  const caption = media.caption?.trim();
  const showCaption = !!caption && caption !== media.title?.trim();
  const captionLong =
    !!caption && (caption.length > CAPTION_EXPAND_THRESHOLD || caption.includes("\n"));
  const published = media.publishedAt ? formatPublished(media.publishedAt) : null;
  const chartEmpty = !error && !showSkeleton && (points.length === 0 || metrics.length === 0);

  return (
    <RadixDialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="media-insights-modal"
        aria-busy={isRefreshing || undefined}
        className={cn(
          "max-h-[92vh] max-w-4xl gap-0 overflow-y-auto p-0 max-sm:max-w-[calc(100vw-1rem)]",
          className,
        )}
      >
        <div className="space-y-4 p-4 sm:p-5">
          {/* Header */}
          <div className="flex items-start gap-3 pr-8">
            {media.thumbnailUrl && (
              <img
                src={media.thumbnailUrl}
                alt=""
                className="h-16 w-16 shrink-0 rounded-md bg-muted object-cover sm:h-24 sm:w-24"
              />
            )}
            <div className="min-w-0 flex-1 space-y-1">
              <DialogTitle className="line-clamp-2 break-words text-base font-semibold leading-snug sm:text-lg">
                {title}
              </DialogTitle>
              <DialogDescription className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground sm:text-sm">
                {media.mediaType && (
                  <span className="rounded-full bg-muted px-2 py-0.5 text-foreground">
                    {media.mediaType}
                  </span>
                )}
                {published && <span>Publicado em {published}</span>}
                {!media.mediaType && !published && (
                  <span className="sr-only">Métricas e histórico da mídia</span>
                )}
              </DialogDescription>
              {showCaption && (
                <div>
                  <p
                    className={cn(
                      "whitespace-pre-line break-words text-sm leading-relaxed text-muted-foreground",
                      !captionOpen && "line-clamp-3",
                    )}
                  >
                    {caption}
                  </p>
                  {captionLong && (
                    <button
                      type="button"
                      aria-expanded={captionOpen}
                      onClick={() => setCaptionOpen((v) => !v)}
                      className="mt-0.5 text-xs font-medium text-primary underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      {captionOpen ? "Ver menos" : "Ver mais"}
                    </button>
                  )}
                </div>
              )}
              {media.permalink && (
                <a
                  href={media.permalink}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 inline-flex items-center gap-1.5 rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                  {media.permalinkLabel ?? "Abrir publicação"}
                </a>
              )}
            </div>
          </div>

          {/* KPIs */}
          {kpis.length > 0 && (
            <StatTileRow>
              {kpis.map((k) => (
                <StatTile
                  key={k.key}
                  label={k.label}
                  value={formatMediaInsightValue(k.value, k.format)}
                />
              ))}
            </StatTileRow>
          )}

          {extra}

          {/* History chart */}
          <ChartCard
            title="Evolução diária"
            loading={showSkeleton}
            error={error ?? null}
            isEmpty={chartEmpty}
            emptyMessage={MEDIA_INSIGHTS_EMPTY_MESSAGE}
            minBodyHeight={220}
            actions={
              isRefreshing ? (
                <span role="status" className="text-xs text-muted-foreground">
                  Atualizando…
                </span>
              ) : undefined
            }
          >
            <div className="space-y-3">
              {metrics.length > 1 && (
                <div role="group" aria-label="Métricas do gráfico" className="flex flex-wrap gap-1.5">
                  {metrics.map((m) => {
                    const active = selectedKeys.includes(m.key);
                    return (
                      <button
                        key={m.key}
                        type="button"
                        aria-pressed={active}
                        onClick={() => toggle(m.key)}
                        className={cn(
                          "rounded-full border px-3 py-1 text-xs font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                          active
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-input bg-background text-muted-foreground hover:bg-accent",
                        )}
                      >
                        {m.label}
                      </button>
                    );
                  })}
                </div>
              )}
              <LineChart
                data={chartData}
                xKey="__label"
                series={selectedMetrics.map((m) => ({ key: m.key, label: m.label }))}
                height={220}
                valueFormatter={(v) => formatMediaInsightValue(v, primaryFormat)}
              />
            </div>
          </ChartCard>

          {error && onRetry && (
            <div className="flex justify-center">
              <button
                type="button"
                onClick={onRetry}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                Tentar novamente
              </button>
            </div>
          )}
        </div>
      </DialogContent>
    </RadixDialog>
  );
}
