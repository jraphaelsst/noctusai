/**
 * `<Cart/>` — the cart view. Items live in `useCart()` (localStorage per host);
 * totals always come from the SERVER quote (`POST /api/storefront/checkout/quote`),
 * never computed client-side. Coupon errors from the quote are shown inline.
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { EmptyState, Field, Input, ListSkeleton, RefreshingBar, RetryError } from './controls';
import { useCommerceT } from './i18n';
import { formatCents } from './format';
import { errorMessage, type CommerceHooks } from './hooks';
import { CART_MAX_QTY, type CartApi } from './cartState';
import { useQuoteFor } from './useQuoteFor';
import type { Quote } from './types';

export interface CartProps {
  hooks: CommerceHooks;
  cart: CartApi;
  locale?: string;
  coupon?: string;
  onCouponChange?: (coupon: string) => void;
  onCheckout: (quote: Quote) => void;
}

export function Cart({ hooks, cart, locale, coupon = '', onCouponChange, onCheckout }: CartProps) {
  const { t, locale: loc } = useCommerceT(locale);
  const [draft, setDraft] = React.useState(coupon);
  const request = React.useMemo(() => ({ items: cart.quoteItems, ...(coupon ? { coupon } : {}) }), [cart.quoteItems, coupon]);
  const q = useQuoteFor(hooks, request);

  if (cart.items.length === 0) return <EmptyState message={t('cart.empty')} />;

  const quote = q.quote;
  return (
    <section className="space-y-4" aria-label={t('cart.title')} aria-busy={q.isRefreshing}>
      <h2 className="text-lg font-semibold">{t('cart.title')}</h2>
      {cart.corrupt ? <p role="alert" className="text-xs text-destructive">{t('cart.corrupt')}</p> : null}
      {cart.persistError ? <p role="alert" className="text-xs text-destructive">{t('cart.persist_error')}</p> : null}
      <ul className="divide-y rounded-md border">
        {cart.items.map((i) => (
          <li key={i.offer_id} className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm">
            <span>
              <span className="font-medium">{i.title}</span> <span className="text-muted-foreground">{i.offer_name}</span>
            </span>
            <span className="flex items-center gap-2">
              <Button size="icon" variant="outline" aria-label={t('cart.decrease')} onClick={() => cart.setQty(i.offer_id, i.qty - 1)}>−</Button>
              <span aria-label={t('cart.qty')}>{i.qty}</span>
              <Button size="icon" variant="outline" aria-label={t('cart.increase')} disabled={i.qty >= CART_MAX_QTY} onClick={() => cart.setQty(i.offer_id, i.qty + 1)}>+</Button>
              <Button size="sm" variant="ghost" onClick={() => cart.remove(i.offer_id)}>{t('common.remove')}</Button>
            </span>
          </li>
        ))}
      </ul>

      {onCouponChange ? (
        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            onCouponChange(draft.trim());
          }}
        >
          <Field label={t('cart.coupon')} error={quote?.coupon_error ?? null}>
            <Input value={draft} onChange={(e) => setDraft(e.target.value)} />
          </Field>
          <Button type="submit" variant="outline">{t('cart.apply')}</Button>
        </form>
      ) : null}

      <RefreshingBar active={q.isRefreshing} label={t('cart.updating')} />
      {q.showSkeleton ? (
        <ListSkeleton rows={2} />
      ) : q.error && !quote ? (
        <RetryError message={`${t('cart.quote_error')}: ${errorMessage(q.error)}`} onRetry={q.retry} retryLabel={t('common.retry')} />
      ) : quote ? (
        <>
          <dl className="ml-auto w-64 space-y-1 text-sm">
            <div className="flex justify-between"><dt>{t('cart.subtotal')}</dt><dd>{formatCents(quote.subtotal_cents, quote.currency, loc)}</dd></div>
            {quote.discount_cents > 0 ? (
              <div className="flex justify-between"><dt>{t('cart.discount')}</dt><dd>-{formatCents(quote.discount_cents, quote.currency, loc)}</dd></div>
            ) : null}
            <div className="flex justify-between text-base font-semibold"><dt>{t('cart.total')}</dt><dd>{formatCents(quote.total_cents, quote.currency, loc)}</dd></div>
          </dl>
          <div className="flex justify-end">
            <Button onClick={() => onCheckout(quote)}>{t('cart.checkout')}</Button>
          </div>
        </>
      ) : null}
    </section>
  );
}
