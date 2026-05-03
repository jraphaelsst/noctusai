/**
 * `<AIBadgeStack/>` — composes multiple AI badges into the single
 * `LayoutEnrichment.aiBadge` slot. Each child badge null-renders when
 * empty, so the stack collapses to nothing when no badge has content.
 *
 * The seed framework's layout factory uses this as the default `aiBadge`
 * fill (`<AIBadgeStack badges={DEFAULT_AI_BADGES}/>`) — products inherit
 * the standard set without writing any code. Products that want
 * product-specific badges spread the defaults: `aiBadge: <AIBadgeStack
 * badges={[<DailyBriefBadge/>, ...DEFAULT_AI_BADGES]}/>`.
 *
 * Inline-flex with 8px gap matches the layout actions row's spacing.
 */
import * as React from 'react';

export interface AIBadgeStackProps {
  /** Ordered list of badge components / elements. Order is rendering order. */
  badges: React.ReactNode[];
  /** Optional className override on the wrapper. */
  className?: string;
}

export function AIBadgeStack({ badges, className }: AIBadgeStackProps) {
  if (!badges.length) return null;
  return (
    <span className={`inline-flex items-center gap-2 ${className ?? ''}`}>
      {badges.map((badge, i) => (
        <React.Fragment key={i}>{badge}</React.Fragment>
      ))}
    </span>
  );
}

export default AIBadgeStack;
