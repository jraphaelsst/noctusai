/**
 * useCatalog — Phase 7 SKELETON hook for product catalog.
 *
 * Returns the React Query {data, isLoading, error} shape so the eventual swap
 * to a real `useQuery` call in Phase 7 PROPER is a one-file change.
 *
 * TODO(adconnect-phase-7): wire to GET /api/products with filter/search/sort
 *   query params, and GET /api/products/{id} for the detail view. Replace the
 *   hard-coded MOCK_PRODUCTS / MOCK_CATEGORIAS arrays with React Query calls
 *   that go through `api` from `@noctusai/seed/infra`. Mirror the
 *   useAtivos/useAtivo pattern in
 *   products/personal-finance/frontend/src/hooks/useAtivos.ts.
 */
import type { CatalogFilters, Categoria, Product } from "@/types";

const MOCK_CATEGORIAS: Categoria[] = [
  { id: "cat6", nome: "Cabos Cat.6", ordem: 1 },
  { id: "cat5e", nome: "Cabos Cat.5e", ordem: 2 },
  { id: "fibra", nome: "Fibra Óptica", ordem: 3 },
  { id: "patch-panel", nome: "Patch Panels", ordem: 4 },
  { id: "acessorios", nome: "Acessórios", ordem: 5 },
];

const MOCK_PRODUCTS: Product[] = [
  {
    id: "1",
    sku: "ADC-CAT6-CMX-305",
    name: "Cabo de Rede Cat.6 CMX",
    category: "cat6",
    category_id: "cat6",
    base_price: 890.0,
    preferential_price: 712.0,
    in_stock: true,
    min_order: 5,
    multiple: 5,
    cashback_percent: 5,
    brand: "AdConnect",
  },
  {
    id: "2",
    sku: "ADC-CAT6-CM-305",
    name: "Cabo de Rede Cat.6 CM",
    category: "cat6",
    category_id: "cat6",
    base_price: 950.0,
    preferential_price: 760.0,
    in_stock: true,
    min_order: 5,
    multiple: 5,
    cashback_percent: 5,
    brand: "AdConnect",
  },
  {
    id: "5",
    sku: "ADC-FO-SCSC-3M",
    name: "Cordão Óptico Duplex SC/SC",
    category: "fibra",
    category_id: "fibra",
    base_price: 45.0,
    preferential_price: 32.0,
    in_stock: true,
    min_order: 20,
    multiple: 10,
    cashback_percent: 3,
    brand: "AdConnect",
  },
  {
    id: "7",
    sku: "ADC-PP24-CAT6",
    name: "Patch Panel 24 Portas Cat.6",
    category: "patch-panel",
    category_id: "patch-panel",
    base_price: 320.0,
    preferential_price: 240.0,
    in_stock: true,
    min_order: 2,
    multiple: 1,
    cashback_percent: 5,
    brand: "AdConnect",
  },
];

export interface UseCatalogResult {
  data: Product[];
  categorias: Categoria[];
  isLoading: boolean;
  error: Error | null;
}

export function useCatalog(_filters?: CatalogFilters): UseCatalogResult {
  // TODO(adconnect-phase-7): wire to /api/products?search=&category=&in_stock=&sort_by=
  return {
    data: MOCK_PRODUCTS,
    categorias: MOCK_CATEGORIAS,
    isLoading: false,
    error: null,
  };
}

export interface UseProductResult {
  data: Product | null;
  isLoading: boolean;
  error: Error | null;
}

export function useProduct(id?: string): UseProductResult {
  // TODO(adconnect-phase-7): wire to /api/products/{id}
  const product = id ? MOCK_PRODUCTS.find((p) => p.id === id) ?? null : null;
  return {
    data: product,
    isLoading: false,
    error: null,
  };
}
