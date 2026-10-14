/** Layout helpers shared by the inventory organs (the design-system primitives are imported directly). */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { ErrorState } from '../design-system/ui/FormControls';
import { Skeleton } from '../design-system/ui/Skeleton';

export { Badge } from '../design-system/ui/Badge';
export { Button };
export { Field, FormError, EmptyState, Select, Textarea, Card } from '../design-system/ui/FormControls';
export { Input } from '../design-system/ui/Input';
export { Dialog, DialogBody, DialogFooter, DialogHeader } from '../design-system/ui/Dialog';

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

/** "Refreshing" pulse over data already on screen — never replaces it. */
export function RefreshingBar({ active, label }: { active: boolean; label: string }) {
  return active ? (
    <p role="status" className="text-xs text-muted-foreground">
      {label}
    </p>
  ) : null;
}
