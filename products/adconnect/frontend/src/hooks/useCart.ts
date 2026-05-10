/**
 * useCart — Phase 7 SKELETON hook for distributor cart.
 *
 * TODO(adconnect-phase-7): wire to GET /api/cart, POST /api/cart/items,
 *   PATCH /api/cart/items/{id}, DELETE /api/cart/items/{id}, POST /api/cart/checkout.
 *   Use useMutation for write ops with cache invalidation on the "cart"
 *   query key, mirroring the useCreateAtivo pattern in
 *   products/personal-finance/frontend/src/hooks/useAtivos.ts.
 */
import type { Cart } from "@/types";

const MOCK_CART: Cart = {
  id: "cart-skeleton",
  distributor_id: "dist-skeleton",
  status: "ativo",
  items: [],
  subtotal: 0,
  total: 0,
  updated_at: new Date().toISOString(),
};

export interface UseCartResult {
  data: Cart | null;
  isLoading: boolean;
  error: Error | null;
}

export function useCart(): UseCartResult {
  // TODO(adconnect-phase-7): wire to /api/cart
  return {
    data: MOCK_CART,
    isLoading: false,
    error: null,
  };
}

export interface UseCartMutationsResult {
  addItem: (productId: string, quantity: number) => void;
  updateItem: (itemId: string, quantity: number) => void;
  removeItem: (itemId: string) => void;
  checkout: () => void;
}

export function useCartMutations(): UseCartMutationsResult {
  // TODO(adconnect-phase-7): replace with useMutation hooks on /api/cart endpoints.
  return {
    addItem: (productId, quantity) => {
      // eslint-disable-next-line no-console
      console.log("[skeleton] addItem", { productId, quantity });
    },
    updateItem: (itemId, quantity) => {
      // eslint-disable-next-line no-console
      console.log("[skeleton] updateItem", { itemId, quantity });
    },
    removeItem: (itemId) => {
      // eslint-disable-next-line no-console
      console.log("[skeleton] removeItem", { itemId });
    },
    checkout: () => {
      // eslint-disable-next-line no-console
      console.log("[skeleton] checkout");
    },
  };
}
