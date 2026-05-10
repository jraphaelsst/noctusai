/**
 * useCatalog — React Query hooks for the AdConnect product catalog.
 *
 * Phase 7 PROPER: wired to backend endpoints landed in Wave 2 (Engineer C).
 * GET /api/products supports filter / search / sort / in-stock query params;
 * preferential pricing is applied server-side for distributor users.
 */
import { useQuery } from "@tanstack/react-query";
import { api, useAuthStore } from "@noctusai/seed/infra";
import type { CatalogFilters, Categoria, Product } from "@/types";

export function useCatalog(filters: CatalogFilters = {}) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["adconnect", "catalog", filters],
    queryFn: async () => {
      const params: Record<string, any> = {};
      if (filters.search) params.search = filters.search;
      if (filters.category) params.category = filters.category;
      if (filters.in_stock_only) params.in_stock_only = true;
      if (filters.sort_by) params.sort_by = filters.sort_by;
      const result = await api.get("/api/products", params);
      return (result.data || []) as Product[];
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useProduct(id?: string) {
  return useQuery({
    queryKey: ["adconnect", "product", id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/products/${id}`);
      return result.data as Product;
    },
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useCategorias() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["adconnect", "categorias"],
    queryFn: async () => {
      const result = await api.get("/api/products/categorias");
      return (result.data || []) as Categoria[];
    },
    enabled: !!user,
    staleTime: 10 * 60 * 1000,
  });
}
