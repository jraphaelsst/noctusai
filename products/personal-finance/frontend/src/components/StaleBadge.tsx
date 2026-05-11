/**
 * StaleBadge — quote freshness indicator (PF-6 degraded-mode UX).
 *
 * Renders a small visual badge when a cotacao's data source is the yfinance
 * dry-run fallback OR when the quote timestamp exceeds the freshness window.
 * Returns `null` when the data is fresh (live yfinance quote within window) —
 * silent absence is correct UX for the common case; we only want to draw
 * attention to staleness.
 *
 * **Freshness thresholds** (per PROJECT.md Phase 5 PF-6 / §7 Q5 default):
 *   - `acao` / `acoes` / stocks: 15 minutes
 *   - `fundo` / `fii` / funds:   30 minutes
 *   - other / unknown:           20 minutes (midpoint default)
 *
 * The decision tree:
 *   1. `fonte === 'dry-run'`  →  always show "Dados simulados" badge
 *   2. `timestamp` absent     →  show "Idade desconhecida" badge
 *   3. age > threshold        →  show "Defasado há {N}min" badge
 *   4. otherwise              →  return null (fresh — no badge)
 *
 * **Why a separate component.** PF currently has no live-cotacao consumers
 * (Watchlist + Carteira render persisted `preco_atual` from the assets table,
 * not real-time quotes). The badge ships ready-to-wire so future surfaces
 * that DO fetch via `useCotacao(ticker)` get degraded-mode UX for free.
 */
import { AlertTriangle, Clock } from "lucide-react";

export type CotacaoLike = {
  fonte?: "yfinance" | "dry-run";
  timestamp?: string;
};

export type AssetKind = "acao" | "fundo" | "fii" | "etf" | "outro";

const FRESHNESS_MINUTES: Record<AssetKind, number> = {
  acao: 15,
  fundo: 30,
  fii: 30,
  etf: 15,
  outro: 20,
};

/**
 * Compute staleness from a cotacao + asset kind.
 *
 * Pure function — exported so tests + consumers can call without rendering.
 * Returns `null` when the quote is fresh; otherwise returns a reason +
 * (when applicable) the computed age in minutes.
 */
export function computeStaleness(
  cotacao: CotacaoLike | null | undefined,
  kind: AssetKind = "outro",
  now: () => number = Date.now,
): { reason: "dry-run" | "no-timestamp" | "old"; ageMinutes?: number } | null {
  if (!cotacao) return null;
  if (cotacao.fonte === "dry-run") {
    return { reason: "dry-run" };
  }
  if (!cotacao.timestamp) {
    return { reason: "no-timestamp" };
  }
  const ts = new Date(cotacao.timestamp).getTime();
  if (Number.isNaN(ts)) {
    return { reason: "no-timestamp" };
  }
  const ageMinutes = Math.floor((now() - ts) / 60000);
  const threshold = FRESHNESS_MINUTES[kind] ?? FRESHNESS_MINUTES.outro;
  if (ageMinutes > threshold) {
    return { reason: "old", ageMinutes };
  }
  return null;
}

export interface StaleBadgeProps {
  cotacao: CotacaoLike | null | undefined;
  kind?: AssetKind;
  /** Test seam — defaults to `Date.now`. */
  now?: () => number;
  className?: string;
}

export function StaleBadge({ cotacao, kind = "outro", now, className = "" }: StaleBadgeProps) {
  const staleness = computeStaleness(cotacao, kind, now);
  if (!staleness) return null;

  const baseClass =
    "inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium";

  if (staleness.reason === "dry-run") {
    return (
      <span
        className={`${baseClass} bg-amber-500/10 text-amber-600 dark:text-amber-400 ${className}`}
        data-testid="stale-badge-dry-run"
        title="Dados simulados — yfinance indisponível"
      >
        <AlertTriangle className="w-2.5 h-2.5" />
        Dados simulados
      </span>
    );
  }

  if (staleness.reason === "no-timestamp") {
    return (
      <span
        className={`${baseClass} bg-muted text-muted-foreground ${className}`}
        data-testid="stale-badge-no-timestamp"
        title="Idade da cotação desconhecida"
      >
        <Clock className="w-2.5 h-2.5" />
        Idade desconhecida
      </span>
    );
  }

  return (
    <span
      className={`${baseClass} bg-amber-500/10 text-amber-600 dark:text-amber-400 ${className}`}
      data-testid="stale-badge-old"
      title={`Defasado há ${staleness.ageMinutes} minutos`}
    >
      <Clock className="w-2.5 h-2.5" />
      Defasado há {staleness.ageMinutes}min
    </span>
  );
}

export default StaleBadge;
