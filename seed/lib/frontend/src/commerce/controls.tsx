/**
 * Re-exports of the seed form primitives the commerce organ is drawn with,
 * plus a few commerce-local layout helpers. One import seam for the folder.
 */
import * as React from 'react';
export { Field, FormError, EmptyState, ErrorState, Select, Textarea, Card } from '../design-system/ui/FormControls';
export { Input } from '../design-system/ui/Input';
import { Skeleton } from '../design-system/ui/Skeleton';
import { Button } from '../design-system/ui/Button';
import { ErrorState } from '../design-system/ui/FormControls';

/** Skeleton rows for a first load (one announcement for screen readers). */
export function ListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2" data-testid="list-loading">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} height={36} width="100%" announce={i === 0} />
      ))}
    </div>
  );
}

/** Error block with a retry button. */
export function RetryError({ message, onRetry, retryLabel }: { message: string; onRetry: () => void; retryLabel: string }) {
  return (
    <div className="space-y-2 text-center">
      <ErrorState message={message} />
      <Button variant="outline" onClick={onRetry}>
        {retryLabel}
      </Button>
    </div>
  );
}

/** Small "refreshing" pulse shown over data already on screen — never replaces it. */
export function RefreshingBar({ active, label }: { active: boolean; label: string }) {
  return active ? (
    <p role="status" className="text-xs text-muted-foreground">
      {label}
    </p>
  ) : null;
}
