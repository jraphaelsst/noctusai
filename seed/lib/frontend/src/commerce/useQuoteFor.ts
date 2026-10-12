/**
 * `useQuoteFor(hooks, request)` — keeps a server quote in sync with a cart
 * request (items + coupon). The two loading signals are computed off `data`:
 * `showSkeleton` only before the first quote; `isRefreshing` while a newer one
 * is in flight over a quote already on screen.
 */
import * as React from 'react';
import type { CommerceHooks } from './hooks';
import type { Quote, QuoteRequest } from './types';

export function useQuoteFor(hooks: CommerceHooks, request: QuoteRequest, provided?: Quote | null) {
  const mutation = hooks.useQuote();
  const key = JSON.stringify(request);
  const { mutate } = mutation;
  React.useEffect(() => {
    if (provided || request.items.length === 0) return;
    mutate(request);
    // `key` captures the request value; `mutate` is stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, provided]);

  const quote = provided ?? mutation.data;
  return {
    quote,
    error: provided ? null : mutation.error,
    showSkeleton: !provided && request.items.length > 0 && mutation.isPending && !mutation.data,
    isRefreshing: !provided && mutation.isPending && !!mutation.data,
    retry: () => mutate(request),
  };
}
