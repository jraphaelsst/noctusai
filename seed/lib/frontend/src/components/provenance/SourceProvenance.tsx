/**
 * SourceProvenance — "where does this value come from, and may I edit it?"
 *
 * The mirror + owned-overlay rule (every data UI ships with data management):
 * a screen that shows an external system's data (Vista, a CRM, a bank feed)
 * next to data WE author must say, per field or per section, which is which.
 * External-mirror values are READ-ONLY and carry their source + freshness;
 * owned values are editable. Where we hold a value that differs from the
 * external one, BOTH are shown.
 *
 * Two pieces:
 *
 * - `<SourceBadge source="Vista" syncedAt={iso} />` — a small read-only
 *   marker ("Vista · sincronizado há 2 h"). Replaces the "edit" pencil that
 *   opens nothing: it states WHY there is no editor.
 * - `<MirrorOverrideValue mirror="120 m²" owned="115 m²" />` — "Vista: X ·
 *   Nosso: Y" when both exist and differ; just the one that exists otherwise.
 *   It never decides precedence — the caller passes what its backend
 *   resolved; this only renders both.
 *
 * → KB § PATTERNS/frontend/mirror-owned-overlay.md
 */
import * as React from 'react';

import { Badge } from '../../design-system/ui/Badge';
import { cn } from '../../utils';

/** "há 5 min" / "há 2 h" / "há 3 dias" — coarse on purpose; the title carries the exact time. */
export function formatSyncedAgo(syncedAt: string | null | undefined, now: Date = new Date()): string | null {
  if (!syncedAt) return null;
  const t = new Date(syncedAt).getTime();
  if (Number.isNaN(t)) return null;
  const min = Math.max(0, Math.floor((now.getTime() - t) / 60_000));
  if (min < 1) return 'agora';
  if (min < 60) return `há ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `há ${h} h`;
  const d = Math.floor(h / 24);
  return `há ${d} ${d === 1 ? 'dia' : 'dias'}`;
}

export interface SourceBadgeProps {
  /** The external system's name, e.g. "Vista". */
  source: string;
  /** ISO timestamp of the last sync of this data; omitted ⇒ no freshness shown. */
  syncedAt?: string | null;
  /** Injectable clock (tests). */
  now?: Date;
  className?: string;
  'data-testid'?: string;
}

export function SourceBadge({ source, syncedAt, now, className, 'data-testid': testId }: SourceBadgeProps) {
  const ago = formatSyncedAgo(syncedAt, now);
  const exact = syncedAt && !Number.isNaN(new Date(syncedAt).getTime()) ? new Date(syncedAt).toLocaleString('pt-BR') : null;
  const title = `Somente leitura — espelho de ${source}${exact ? `, sincronizado em ${exact}` : ''}. Para mudar, altere na origem.`;
  return (
    <Badge variant="outline" className={cn('font-normal', className)} title={title} data-testid={testId ?? 'source-badge'}>
      {source}
      {ago ? <span className="text-muted-foreground"> · {ago}</span> : null}
    </Badge>
  );
}

export interface MirrorOverrideValueProps {
  /** The external system's value, already formatted; null/empty ⇒ absent. */
  mirror?: React.ReactNode;
  /** Our own value, already formatted; null/empty ⇒ absent. */
  owned?: React.ReactNode;
  mirrorLabel?: string;
  ownedLabel?: string;
  className?: string;
}

const isEmpty = (v: React.ReactNode) => v === null || v === undefined || v === '' || v === false;

export function MirrorOverrideValue({
  mirror,
  owned,
  mirrorLabel = 'Vista',
  ownedLabel = 'Nosso',
  className,
}: MirrorOverrideValueProps) {
  const temMirror = !isEmpty(mirror);
  const temOwned = !isEmpty(owned);
  if (!temMirror && !temOwned) return null;
  const diverge = temMirror && temOwned && String(mirror) !== String(owned);
  if (!diverge) {
    return <span className={className}>{temOwned ? owned : mirror}</span>;
  }
  return (
    <span className={cn('inline-flex flex-wrap gap-x-2', className)} data-testid="mirror-override-value">
      <span className="text-muted-foreground">
        {mirrorLabel}: <span data-testid="mirror-value">{mirror}</span>
      </span>
      <span>
        · {ownedLabel}: <strong data-testid="owned-value">{owned}</strong>
      </span>
    </span>
  );
}
