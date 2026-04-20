/**
 * ScorePill — a small pill displaying a numeric score with an optional
 * threshold-based color (green ≥ 80, amber ≥ 50, red < 50 by default).
 *
 *   <ScorePill value={92.3} label="Score" />
 *   <ScorePill value={41.1} thresholds={{ good: 70, warn: 40 }} />
 */
import React from 'react';

export interface ScorePillProps {
  value: number | null | undefined;
  label?: string;
  thresholds?: { good: number; warn: number };
  precision?: number;
  suffix?: string;
  className?: string;
}

const DEFAULT_THRESHOLDS = { good: 80, warn: 50 };

export function ScorePill({
  value,
  label,
  thresholds = DEFAULT_THRESHOLDS,
  precision = 1,
  suffix = '',
  className = '',
}: ScorePillProps) {
  if (value == null || Number.isNaN(value)) {
    return <span className={`inline-flex items-center gap-1 rounded-full border border-border bg-muted px-2 py-0.5 text-xs text-muted-foreground ${className}`}>
      {label && <span className="opacity-70">{label}:</span>} —
    </span>;
  }
  const tier = value >= thresholds.good ? 'good' : value >= thresholds.warn ? 'warn' : 'bad';
  const tierClass =
    tier === 'good'
      ? 'bg-green-500/10 text-green-700 dark:text-green-300 border-green-500/30'
      : tier === 'warn'
        ? 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/30'
        : 'bg-red-500/10 text-red-700 dark:text-red-300 border-red-500/30';
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${tierClass} ${className}`}>
      {label && <span className="font-normal opacity-80">{label}:</span>}
      <span>{value.toFixed(precision)}{suffix}</span>
    </span>
  );
}
