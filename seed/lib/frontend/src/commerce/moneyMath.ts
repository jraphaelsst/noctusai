/** Order money arithmetic shared by the P4 money organs (integer cents only). */
import type { Order, OrderCharge, OrderRefund } from './types';

/** What the buyer paid: the PAID charge attempt (interest included); falls back to the order total on a pre-P4 order. */
export function paidCents(order: Pick<Order, 'charges' | 'total_cents'>): number {
  const paid = (order.charges ?? []).find((c) => c.status === 'paid');
  return paid ? paid.amount_cents : order.total_cents;
}

/** Refunds that still hold money back from the balance (the server subtracts every non-failed refund). */
export function heldRefundCents(refunds: readonly OrderRefund[] | undefined): number {
  return (refunds ?? []).filter((r) => r.status !== 'failed').reduce((sum, r) => sum + r.amount_cents, 0);
}

export function doneRefundCents(refunds: readonly OrderRefund[] | undefined): number {
  return (refunds ?? []).filter((r) => r.status === 'done').reduce((sum, r) => sum + r.amount_cents, 0);
}

/** Still refundable, never negative. The server is the authority — this only drives the UI. */
export function refundableCents(order: Pick<Order, 'charges' | 'refunds' | 'total_cents'>): number {
  return Math.max(0, paidCents(order) - heldRefundCents(order.refunds));
}

export function hasRefundInProgress(refunds: readonly OrderRefund[] | undefined): boolean {
  return (refunds ?? []).some((r) => r.status === 'requested');
}

/** One id per refund ATTEMPT; reused on a retry of the same input so the server never double-refunds. */
export function newIdempotencyKey(): string {
  const c = (globalThis as { crypto?: Crypto }).crypto;
  if (c && typeof c.randomUUID === 'function') return c.randomUUID();
  return `k-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

export type { OrderCharge };
