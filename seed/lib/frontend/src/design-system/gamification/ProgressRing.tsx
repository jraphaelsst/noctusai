/**
 * ProgressRing — a circular SVG progress indicator sized to any radius.
 *
 *   <ProgressRing value={72} label="Meta" />
 *   <ProgressRing value={120} thresholds={{ good: 100 }} size={96} />
 *
 * Values > 100 are clamped for display but the label shows the real number.
 * Color tiers match ScorePill for consistency.
 */
import React from 'react';

export interface ProgressRingProps {
  /** 0–100+. Over 100 shows the ring fully filled but the label reflects truth. */
  value: number | null | undefined;
  label?: string;
  size?: number; // pixel diameter
  strokeWidth?: number;
  thresholds?: { good: number; warn: number };
  className?: string;
}

const DEFAULT_THRESHOLDS = { good: 80, warn: 50 };

export function ProgressRing({
  value,
  label,
  size = 72,
  strokeWidth = 6,
  thresholds = DEFAULT_THRESHOLDS,
  className = '',
}: ProgressRingProps) {
  const v = value == null || Number.isNaN(value) ? 0 : value;
  const displayed = Math.max(0, Math.min(100, v));
  const tier = v >= thresholds.good ? 'good' : v >= thresholds.warn ? 'warn' : 'bad';
  const stroke =
    tier === 'good'
      ? 'stroke-green-500'
      : tier === 'warn'
        ? 'stroke-amber-500'
        : 'stroke-red-500';

  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - displayed / 100);

  return (
    <div className={`inline-flex flex-col items-center ${className}`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={strokeWidth}
          className="stroke-muted"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className={`${stroke} transition-[stroke-dashoffset] duration-700`}
        />
        <text
          x="50%"
          y="50%"
          textAnchor="middle"
          dominantBaseline="central"
          className="rotate-90 fill-foreground text-xs font-semibold"
          style={{ transformOrigin: 'center' }}
        >
          {value == null ? '—' : `${Math.round(v)}%`}
        </text>
      </svg>
      {label && <span className="mt-1 text-xs text-muted-foreground">{label}</span>}
    </div>
  );
}
