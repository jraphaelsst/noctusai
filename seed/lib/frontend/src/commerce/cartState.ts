/**
 * Cart — local state persisted per storefront host in `localStorage`.
 *
 * Prices here are DISPLAY snapshots only; the server recomputes every total
 * (quote + checkout), so a stale or tampered cart can never change what is
 * charged. Storage failures (private mode, quota, corrupt JSON) never lose
 * the in-memory cart and are never silent: `persistError` / `corrupt` expose
 * them so the UI can say so.
 */
import * as React from 'react';
import type { QuoteItemInput } from './types';

export interface CartItem {
  offer_id: string;
  product_slug: string;
  title: string;
  offer_name: string;
  unit_price_cents: number;
  currency: string;
  qty: number;
}

export const CART_MAX_QTY = 99;

export function cartStorageKey(host?: string): string {
  const h = host ?? (typeof window !== 'undefined' ? window.location.host : 'default');
  return `commerce.cart.${h}`;
}

function isCartItem(x: unknown): x is CartItem {
  const i = x as CartItem;
  return (
    !!i &&
    typeof i.offer_id === 'string' &&
    typeof i.title === 'string' &&
    Number.isInteger(i.qty) &&
    i.qty > 0 &&
    Number.isInteger(i.unit_price_cents)
  );
}

export function readCart(key: string): { items: CartItem[]; corrupt: boolean } {
  let raw: string | null;
  try {
    raw = window.localStorage.getItem(key);
  } catch {
    // Storage unavailable (blocked/private mode): start empty; writes will report `persistError`.
    return { items: [], corrupt: false };
  }
  if (!raw) return { items: [], corrupt: false };
  try {
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.every(isCartItem)) return { items: parsed, corrupt: false };
  } catch {
    // fallthrough to corrupt
  }
  return { items: [], corrupt: true };
}

export interface CartApi {
  items: CartItem[];
  count: number;
  /** Request body items for quote/checkout. */
  quoteItems: QuoteItemInput[];
  add: (item: Omit<CartItem, 'qty'>, qty?: number) => void;
  setQty: (offerId: string, qty: number) => void;
  remove: (offerId: string) => void;
  clear: () => void;
  /** True when the last write to localStorage failed (cart still works in memory). */
  persistError: boolean;
  /** True when the stored cart was unreadable and was discarded. */
  corrupt: boolean;
}

export function useCart(host?: string): CartApi {
  const key = cartStorageKey(host);
  const initial = React.useRef<{ items: CartItem[]; corrupt: boolean } | null>(null);
  if (initial.current === null) initial.current = readCart(key);
  const [items, setItems] = React.useState<CartItem[]>(initial.current.items);
  const [persistError, setPersistError] = React.useState(false);
  const corrupt = initial.current.corrupt;

  const persist = React.useCallback(
    (next: CartItem[]) => {
      try {
        window.localStorage.setItem(key, JSON.stringify(next));
        setPersistError(false);
      } catch {
        setPersistError(true);
      }
    },
    [key],
  );

  const update = React.useCallback(
    (fn: (prev: CartItem[]) => CartItem[]) => {
      setItems((prev) => {
        const next = fn(prev);
        persist(next);
        return next;
      });
    },
    [persist],
  );

  const clampQty = (q: number) => Math.max(1, Math.min(CART_MAX_QTY, Math.floor(q)));

  return {
    items,
    count: items.reduce((n, i) => n + i.qty, 0),
    quoteItems: items.map((i) => ({ offer_id: i.offer_id, qty: i.qty })),
    add: (item, qty = 1) =>
      update((prev) => {
        const existing = prev.find((i) => i.offer_id === item.offer_id);
        return existing
          ? prev.map((i) => (i.offer_id === item.offer_id ? { ...i, qty: clampQty(i.qty + qty) } : i))
          : [...prev, { ...item, qty: clampQty(qty) }];
      }),
    setQty: (offerId, qty) =>
      update((prev) =>
        qty <= 0 ? prev.filter((i) => i.offer_id !== offerId) : prev.map((i) => (i.offer_id === offerId ? { ...i, qty: clampQty(qty) } : i)),
      ),
    remove: (offerId) => update((prev) => prev.filter((i) => i.offer_id !== offerId)),
    clear: () => update(() => []),
    persistError,
    corrupt,
  };
}
