/**
 * Pure helpers shared by the Instagram insights components.
 * `null` always means "Meta did not serve it" — never coerced to 0.
 */
import type {
  InstagramMediaItem,
  InstagramMetricDef,
  InstagramTrendPoint,
} from "@/hooks/useInstagramInsights";

export type InstagramPeriod = "30d" | "7d" | "last";

export const PERIOD_LABEL: Record<InstagramPeriod, string> = {
  "30d": "30 dias",
  "7d": "7 dias",
  last: "Último dia",
};

/** Ascending by priority (1 = most relevant); stable for ties. */
export function sortMetricsByPriority(metrics: InstagramMetricDef[]): InstagramMetricDef[] {
  return metrics
    .map((m, i) => ({ m, i }))
    .sort((a, b) => a.m.priority - b.m.priority || a.i - b.i)
    .map(({ m }) => m);
}

/** "YYYY-MM-DD" minus N days, computed in UTC (no timezone shift). */
function shiftDate(date: string, days: number): string {
  const [y, m, d] = date.split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1, d - days));
  return t.toISOString().slice(0, 10);
}

/** Points inside the period, ascending. "last" = only the latest daily point. */
export function pointsForPeriod(
  points: InstagramTrendPoint[],
  period: InstagramPeriod,
): InstagramTrendPoint[] {
  if (points.length === 0) return [];
  const sorted = [...points].sort((a, b) => a.date.localeCompare(b.date));
  const latest = sorted[sorted.length - 1];
  if (period === "last") return [latest];
  const days = period === "7d" ? 7 : 30;
  const min = shiftDate(latest.date, days - 1);
  return sorted.filter((p) => p.date >= min);
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** Sum of a daily metric; `null` when no point served it. */
export function sumMetric(points: InstagramTrendPoint[], key: string): number | null {
  let total = 0;
  let any = false;
  for (const p of points) {
    const v = num(p[key]);
    if (v !== null) {
      total += v;
      any = true;
    }
  }
  return any ? total : null;
}

/**
 * "Novos seguidores" derived from `followers_count` deltas: last value minus the
 * first value in the window. For "last", `window` must include the previous
 * day's point (pass the unsliced series). `null` when not derivable (< 2 points
 * with a followers_count).
 */
export function followerGrowth(
  allPoints: InstagramTrendPoint[],
  period: InstagramPeriod,
): number | null {
  const sorted = [...allPoints]
    .sort((a, b) => a.date.localeCompare(b.date))
    .filter((p) => num(p.followers_count) !== null);
  if (sorted.length < 2) return null;
  const last = sorted[sorted.length - 1];
  const lastVal = num(last.followers_count) as number;
  if (period === "last") return lastVal - (num(sorted[sorted.length - 2].followers_count) as number);
  const inWindow = pointsForPeriod(sorted, period);
  if (inWindow.length < 2) return null;
  return lastVal - (num(inWindow[0].followers_count) as number);
}

export function mediaKindLabel(item: Pick<InstagramMediaItem, "media_type" | "media_product_type">): string {
  switch (item.media_product_type) {
    case "REELS":
      return "Reel";
    case "STORY":
      return "Story";
    case "AD":
      return "Anúncio";
    default:
      break;
  }
  if (item.media_type === "CAROUSEL_ALBUM") return "Carrossel";
  if (item.media_type === "VIDEO") return "Reel";
  if (item.media_type === "IMAGE") return "Foto";
  return "Post";
}

/** dd/MM/yyyy from an ISO timestamp, in America/Sao_Paulo. */
export function formatPostDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
}
