/**
 * RankBadge — a visually-tiered rank indicator.
 *
 *   <RankBadge rank={1} />      // gold
 *   <RankBadge rank={2} />      // silver
 *   <RankBadge rank={3} />      // bronze
 *   <RankBadge rank={12} />     // neutral
 *
 * Tiers follow the convention "top-3 get medals; everyone else gets their
 * number". Gamification rule per `KB/CONTEXT/07-GAMIFICATION.md` — subtle,
 * always tied to real business activity, with a tooltip explaining the
 * formula if wrapped in a TooltipProvider.
 */
import React from 'react';

export interface RankBadgeProps {
  rank: number;
  /** Optional hint shown as the `title=` attribute (no TooltipProvider required). */
  title?: string;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

function rankStyle(rank: number): { bg: string; fg: string; ring: string } {
  if (rank === 1) return { bg: 'bg-amber-400', fg: 'text-amber-950', ring: 'ring-amber-500/50' };
  if (rank === 2) return { bg: 'bg-slate-300', fg: 'text-slate-900', ring: 'ring-slate-400/50' };
  if (rank === 3) return { bg: 'bg-orange-400', fg: 'text-orange-950', ring: 'ring-orange-500/50' };
  return { bg: 'bg-muted', fg: 'text-muted-foreground', ring: 'ring-muted-foreground/20' };
}

function sizeClass(size: 'sm' | 'md' | 'lg' = 'md'): string {
  if (size === 'sm') return 'h-5 min-w-5 text-[10px] px-1';
  if (size === 'lg') return 'h-8 min-w-8 text-sm px-2';
  return 'h-6 min-w-6 text-xs px-1.5';
}

export function RankBadge({ rank, title, size = 'md', className = '' }: RankBadgeProps) {
  const style = rankStyle(rank);
  return (
    <span
      title={title ?? `Posição #${rank} no ranking`}
      className={`inline-flex items-center justify-center rounded-full font-semibold ring-1 ${style.bg} ${style.fg} ${style.ring} ${sizeClass(size)} ${className}`}
    >
      #{rank}
    </span>
  );
}
