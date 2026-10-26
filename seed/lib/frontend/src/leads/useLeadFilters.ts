import * as React from 'react';
import type { LeadFiltersState } from './types';

/** Filters that are controlled when the host passes them (so Funil <-> Lista share one search) and local otherwise. */
export function useLeadFilters(
  controlled: LeadFiltersState | undefined,
  onChange: ((next: LeadFiltersState) => void) | undefined,
): [LeadFiltersState, (next: LeadFiltersState) => void] {
  const [local, setLocal] = React.useState<LeadFiltersState>({});
  const value = controlled ?? local;
  const set = React.useCallback(
    (next: LeadFiltersState) => {
      if (controlled === undefined) setLocal(next);
      onChange?.(next);
    },
    [controlled, onChange],
  );
  return [value, set];
}

/** `value` after it has stopped changing for `ms` (typing in the search box must not fire a request per key). */
export function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = React.useState(value);
  React.useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}
