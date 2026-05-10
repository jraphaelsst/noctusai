/**
 * useOrders — React Query hooks for order history + status transitions.
 *
 * Phase 7 PROPER: wired against the order endpoints. `usePlaceOrder` is the
 * direct-place mutation (cart-less); the cart→order flow goes through
 * `useCartMutations.checkout` which invalidates the orders cache too.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, useAuthStore } from "@noctusai/seed/infra";
import { toast } from "sonner";
import type { Order, OrderStatus } from "@/types";

export function useOrders() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["adconnect", "orders"],
    queryFn: async () => {
      const result = await api.get("/api/orders");
      return (result.data || []) as Order[];
    },
    enabled: !!user,
    staleTime: 60 * 1000,
  });
}

export function useOrder(id?: string) {
  return useQuery({
    queryKey: ["adconnect", "order", id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/orders/${id}`);
      return result.data as Order;
    },
    enabled: !!id,
    staleTime: 30 * 1000,
  });
}

export function usePlaceOrder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: { items: Array<{ product_id: string; quantidade: number }>; observacoes?: string }) => {
      const result = await api.post("/api/orders", data);
      return result.data as Order;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["adconnect", "orders"] });
      queryClient.invalidateQueries({ queryKey: ["adconnect", "cart"] });
      toast.success("Pedido criado");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar pedido", { description: error.message });
    },
  });
}

export function useTransitionOrderStatus() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, status }: { id: string; status: OrderStatus }) => {
      const result = await api.patch(`/api/orders/${id}/status`, { status });
      return result.data as Order;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["adconnect", "orders"] });
      queryClient.invalidateQueries({ queryKey: ["adconnect", "order", data?.id] });
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar pedido", { description: error.message });
    },
  });
}
