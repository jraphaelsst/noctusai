/**
 * useOrders — Phase 7 SKELETON hook for order history + detail.
 *
 * TODO(adconnect-phase-7): wire to GET /api/orders (history) and
 *   GET /api/orders/{id} (detail). Add useMutation for status transitions
 *   (only the brand-admin endpoints, not distributor-side — distributor only
 *   places + cancels). Mirror the useCarteira pattern in
 *   products/personal-finance/frontend/src/hooks/useCarteira.ts.
 */
import type { Order } from "@/types";

const MOCK_ORDERS: Order[] = [];

export interface UseOrdersResult {
  data: Order[];
  isLoading: boolean;
  error: Error | null;
}

export function useOrders(): UseOrdersResult {
  // TODO(adconnect-phase-7): wire to /api/orders
  return {
    data: MOCK_ORDERS,
    isLoading: false,
    error: null,
  };
}

export interface UseOrderResult {
  data: Order | null;
  isLoading: boolean;
  error: Error | null;
}

export function useOrder(id?: string): UseOrderResult {
  // TODO(adconnect-phase-7): wire to /api/orders/{id}
  const order = id ? MOCK_ORDERS.find((o) => o.id === id) ?? null : null;
  return {
    data: order,
    isLoading: false,
    error: null,
  };
}

export interface PlaceOrderInput {
  cart_id: string;
  notes?: string;
}

export interface UsePlaceOrderResult {
  placeOrder: (input: PlaceOrderInput) => void;
  isPending: boolean;
}

export function usePlaceOrder(): UsePlaceOrderResult {
  // TODO(adconnect-phase-7): wire to POST /api/orders (or POST /api/cart/checkout).
  return {
    placeOrder: (input) => {
      // eslint-disable-next-line no-console
      console.log("[skeleton] placeOrder", input);
    },
    isPending: false,
  };
}
