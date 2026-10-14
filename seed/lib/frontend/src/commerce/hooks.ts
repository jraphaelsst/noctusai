/**
 * `createCommerceHooks(apiBase | api)` — TanStack Query hooks for the commerce
 * staff API (CONTRACT §3) and the public storefront API (CONTRACT §4).
 *
 * Transport: pass a string base URL (public storefront use — plain `fetch`,
 * no auth, `{data}` envelopes unwrapped here) OR an already-authenticated
 * seed `ApiClient` (staff use — `createApiClient()` of the host product).
 *
 * 🔴 Loading contract (`KB § PATTERNS/frontend/lying-loading-state.md`): every
 * read hook returns `showSkeleton = isPending && !data` (first load only) and
 * `isRefreshing = isFetching && !!data` (indicator only, never an early
 * return). Never `isLoading`, never a bare `isFetching` gate. Lists whose key
 * changes (page/filters/search) keep `placeholderData: (prev) => prev`.
 * Authorization-scoped personal data keyed by id (customer detail, public
 * order by token) deliberately does NOT use placeholderData: showing the
 * previous customer's/buyer's data under a new key would leak it.
 *
 * Errors are never swallowed: queries expose `error`, mutations reject with
 * `ApiError` so the caller renders it (409 `versao_conflitante`, 422
 * `aceite_obrigatorio`, ...).
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryKey,
} from '@tanstack/react-query';
import { type ApiClient } from '../api';
import { apiErrorCode, apiErrorStatus, createFetchTransport, errorMessage, keep, signals } from '../organ-kit/query';
import type {
  AccessLinkRequest,
  Category,
  CategoryInput,
  CheckoutRequest,
  CheckoutResult,
  CnpjLookupResult,
  CommerceEnvelope,
  Coupon,
  CouponInput,
  Customer,
  Media,
  Offer,
  OfferInput,
  Order,
  OrderStatus,
  Paginated,
  Product,
  ProductInput,
  ProductStatus,
  PrivacyRequestInput,
  PublicOrder,
  Quote,
  QuoteRequest,
  Storefront,
  StorefrontProduct,
  CatalogItem,
  StoreProfile,
  StoreProfileInput,
} from './types';

/** The subset of the seed `ApiClient` the commerce hooks need. */
export type CommerceApi = Pick<ApiClient, 'get' | 'post' | 'put' | 'patch' | 'delete' | 'upload'>;

// Moved to the shared organ kit; re-exported so existing `commerce/hooks` importers keep working.
export { apiErrorCode, apiErrorStatus, createFetchTransport, errorMessage, keep, signals };

export interface PageParams {
  page?: number;
  q?: string;
}
export interface ProductListParams extends PageParams {
  status?: ProductStatus | '';
}
export interface OrderListParams {
  page?: number;
  status?: OrderStatus | '';
}
export interface CatalogParams extends PageParams {
  category?: string;
}

/** Namespaced query keys (exported so hosts can invalidate precisely). */
export const commerceKeys = {
  all: ['commerce'] as const,
  profile: ['commerce', 'staff', 'profile'] as const,
  categories: ['commerce', 'staff', 'categories'] as const,
  products: ['commerce', 'staff', 'products'] as const,
  product: (id: string) => ['commerce', 'staff', 'products', 'detail', id] as const,
  offers: (productId: string) => ['commerce', 'staff', 'products', 'detail', productId, 'offers'] as const,
  coupons: ['commerce', 'staff', 'coupons'] as const,
  customers: ['commerce', 'staff', 'customers'] as const,
  customer: (id: string) => ['commerce', 'staff', 'customers', 'detail', id] as const,
  orders: ['commerce', 'staff', 'orders'] as const,
  order: (id: string) => ['commerce', 'staff', 'orders', 'detail', id] as const,
  storefront: ['commerce', 'storefront', 'profile'] as const,
  catalog: ['commerce', 'storefront', 'catalog'] as const,
  storefrontProduct: (slug: string) => ['commerce', 'storefront', 'product', slug] as const,
  publicOrder: (token: string) => ['commerce', 'storefront', 'order', token] as const,
};

/** Order polling interval while a payment is pending (ms). */
export const ORDER_POLL_MS = 5000;

// ---------------------------------------------------------------------------
// Transport
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

export function createCommerceHooks(apiOrBase: string | CommerceApi) {
  const api: CommerceApi = typeof apiOrBase === 'string' ? createFetchTransport(apiOrBase) : apiOrBase;

  const unwrap = async <T,>(p: Promise<CommerceEnvelope<T>>): Promise<T> => (await p).data;

  function useInvalidate() {
    const qc = useQueryClient();
    return (...keys: QueryKey[]) => Promise.all(keys.map((k) => qc.invalidateQueries({ queryKey: k })));
  }

  // ---- staff: profile ----------------------------------------------------
  function useProfile() {
    const q = useQuery<StoreProfile | null>({
      queryKey: commerceKeys.profile,
      queryFn: () => unwrap(api.get('/api/commerce/profile')),
    });
    return signals(q);
  }
  function useSaveProfile() {
    const inv = useInvalidate();
    return useMutation({
      mutationFn: (body: StoreProfileInput) =>
        unwrap<StoreProfile>(api.put('/api/commerce/profile', body)),
      onSuccess: () => inv(commerceKeys.profile),
    });
  }
  function useCnpjLookup() {
    return useMutation({
      mutationFn: (cnpj: string) =>
        unwrap<CnpjLookupResult>(api.post('/api/commerce/profile/cnpj-lookup', { cnpj })),
    });
  }

  // ---- staff: categories -------------------------------------------------
  function useCategories() {
    const q = useQuery<Category[]>({
      queryKey: commerceKeys.categories,
      queryFn: async () => {
        const r = await api.get<{ data: Category[] }>('/api/commerce/categories');
        return r.data;
      },
    });
    return signals(q);
  }
  function useCategoryMutations() {
    const inv = useInvalidate();
    const done = () => inv(commerceKeys.categories);
    return {
      create: useMutation({
        mutationFn: (b: CategoryInput) => unwrap<Category>(api.post('/api/commerce/categories', b)),
        onSuccess: done,
      }),
      update: useMutation({
        mutationFn: ({ id, ...b }: Partial<CategoryInput> & { id: string }) =>
          unwrap<Category>(api.patch(`/api/commerce/categories/${id}`, b)),
        onSuccess: done,
      }),
      remove: useMutation({
        mutationFn: (id: string) => api.delete(`/api/commerce/categories/${id}`),
        onSuccess: done,
      }),
    };
  }

  // ---- staff: products ---------------------------------------------------
  function useProducts(params: ProductListParams = {}) {
    const q = useQuery<Paginated<Product>>({
      queryKey: [...commerceKeys.products, 'list', params],
      queryFn: () => api.get('/api/commerce/products', params),
      placeholderData: keep,
    });
    return signals(q);
  }
  function useProduct(id: string | null | undefined) {
    // No placeholderData: id-keyed detail must not show another product's content.
    const q = useQuery<Product>({
      queryKey: commerceKeys.product(id ?? ''),
      queryFn: () => unwrap(api.get(`/api/commerce/products/${id}`)),
      enabled: !!id,
    });
    return signals(q);
  }
  function useProductMutations() {
    const inv = useInvalidate();
    const done = () => inv(commerceKeys.products);
    return {
      create: useMutation({
        mutationFn: (b: ProductInput) => unwrap<Product>(api.post('/api/commerce/products', b)),
        onSuccess: done,
      }),
      update: useMutation({
        mutationFn: ({ id, ...b }: Partial<ProductInput> & { id: string }) =>
          unwrap<Product>(api.patch(`/api/commerce/products/${id}`, b)),
        onSuccess: done,
      }),
      remove: useMutation({
        mutationFn: (id: string) => api.delete(`/api/commerce/products/${id}`),
        onSuccess: done,
      }),
      setStatus: useMutation({
        mutationFn: ({ id, status }: { id: string; status: ProductStatus }) =>
          unwrap<Product>(api.post(`/api/commerce/products/${id}/status`, { status })),
        onSuccess: done,
      }),
    };
  }

  // ---- staff: offers + media --------------------------------------------
  function useOffers(productId: string | null | undefined) {
    const q = useQuery<Offer[]>({
      queryKey: commerceKeys.offers(productId ?? ''),
      queryFn: async () => (await api.get<{ data: Offer[] }>(`/api/commerce/products/${productId}/offers`)).data,
      enabled: !!productId,
    });
    return signals(q);
  }
  function useOfferMutations(productId: string) {
    const inv = useInvalidate();
    // Offers live under the product detail key, so one invalidation covers both.
    const done = () => inv(commerceKeys.product(productId), commerceKeys.products);
    return {
      create: useMutation({
        mutationFn: (b: OfferInput) => unwrap<Offer>(api.post(`/api/commerce/products/${productId}/offers`, b)),
        onSuccess: done,
      }),
      update: useMutation({
        mutationFn: ({ id, ...b }: Partial<OfferInput> & { id: string }) =>
          unwrap<Offer>(api.patch(`/api/commerce/products/${productId}/offers/${id}`, b)),
        onSuccess: done,
      }),
      remove: useMutation({
        mutationFn: (id: string) => api.delete(`/api/commerce/products/${productId}/offers/${id}`),
        onSuccess: done,
      }),
    };
  }
  function useMediaMutations(productId: string) {
    const inv = useInvalidate();
    const done = () => inv(commerceKeys.product(productId));
    return {
      upload: useMutation({
        mutationFn: ({ file, alt }: { file: File; alt?: string }) => {
          const form = new FormData();
          form.append('file', file);
          if (alt) form.append('alt', alt);
          return unwrap<Media>(api.upload(`/api/commerce/products/${productId}/media`, form));
        },
        onSuccess: done,
      }),
      remove: useMutation({
        mutationFn: (mediaId: string) => api.delete(`/api/commerce/products/${productId}/media/${mediaId}`),
        onSuccess: done,
      }),
    };
  }

  // ---- staff: coupons ----------------------------------------------------
  function useCoupons() {
    const q = useQuery<Coupon[]>({
      queryKey: commerceKeys.coupons,
      queryFn: async () => (await api.get<{ data: Coupon[] }>('/api/commerce/coupons')).data,
    });
    return signals(q);
  }
  function useCouponMutations() {
    const inv = useInvalidate();
    const done = () => inv(commerceKeys.coupons);
    return {
      create: useMutation({
        mutationFn: (b: CouponInput) => unwrap<Coupon>(api.post('/api/commerce/coupons', b)),
        onSuccess: done,
      }),
      update: useMutation({
        mutationFn: ({ id, ...b }: Partial<CouponInput> & { id: string }) =>
          unwrap<Coupon>(api.patch(`/api/commerce/coupons/${id}`, b)),
        onSuccess: done,
      }),
      remove: useMutation({
        mutationFn: (id: string) => api.delete(`/api/commerce/coupons/${id}`),
        onSuccess: done,
      }),
    };
  }

  // ---- staff: customers --------------------------------------------------
  function useCustomers(params: PageParams = {}) {
    const q = useQuery<Paginated<Customer>>({
      queryKey: [...commerceKeys.customers, 'list', params],
      queryFn: () => api.get('/api/commerce/customers', params),
      placeholderData: keep,
    });
    return signals(q);
  }
  function useCustomer(id: string | null | undefined) {
    // Personal data keyed by id: no placeholderData (would show a previous person's PII).
    const q = useQuery<Customer>({
      queryKey: commerceKeys.customer(id ?? ''),
      queryFn: () => unwrap(api.get(`/api/commerce/customers/${id}`)),
      enabled: !!id,
    });
    return signals(q);
  }
  function useExportCustomer() {
    return useMutation({
      mutationFn: (id: string) => unwrap<Record<string, unknown>>(api.get(`/api/commerce/customers/${id}/export`)),
    });
  }
  function useAnonymizeCustomer() {
    const inv = useInvalidate();
    return useMutation({
      mutationFn: (id: string) => unwrap<Customer>(api.post(`/api/commerce/customers/${id}/anonymize`, {})),
      onSuccess: () => inv(commerceKeys.customers),
    });
  }

  // ---- staff: orders -----------------------------------------------------
  function useOrders(params: OrderListParams = {}) {
    const q = useQuery<Paginated<Order>>({
      queryKey: [...commerceKeys.orders, 'list', params],
      queryFn: () => api.get('/api/commerce/orders', params),
      placeholderData: keep,
    });
    return signals(q);
  }
  function useOrder(id: string | null | undefined) {
    const q = useQuery<Order>({
      queryKey: commerceKeys.order(id ?? ''),
      queryFn: () => unwrap(api.get(`/api/commerce/orders/${id}`)),
      enabled: !!id,
    });
    return signals(q);
  }
  function useCancelOrder() {
    const inv = useInvalidate();
    return useMutation({
      mutationFn: (id: string) => unwrap<Order>(api.post(`/api/commerce/orders/${id}/cancel`, {})),
      onSuccess: () => inv(commerceKeys.orders),
    });
  }

  // ---- storefront (public) ----------------------------------------------
  function useStorefront() {
    const q = useQuery<Storefront>({
      queryKey: commerceKeys.storefront,
      queryFn: () => unwrap(api.get('/api/storefront')),
      staleTime: 60_000,
    });
    return signals(q);
  }
  function useCatalog(params: CatalogParams = {}) {
    const q = useQuery<Paginated<CatalogItem>>({
      queryKey: [...commerceKeys.catalog, params],
      queryFn: () => api.get('/api/storefront/catalog', params),
      placeholderData: keep,
    });
    return signals(q);
  }
  function useStorefrontProduct(slug: string | null | undefined) {
    const q = useQuery<StorefrontProduct>({
      queryKey: commerceKeys.storefrontProduct(slug ?? ''),
      queryFn: () => unwrap(api.get(`/api/storefront/products/${slug}`)),
      enabled: !!slug,
    });
    return signals(q);
  }
  function useQuote() {
    return useMutation({
      mutationFn: (b: QuoteRequest) => unwrap<Quote>(api.post('/api/storefront/checkout/quote', b)),
    });
  }
  function useCheckout() {
    return useMutation({
      mutationFn: (b: CheckoutRequest) => unwrap<CheckoutResult>(api.post('/api/storefront/checkout', b)),
    });
  }
  /**
   * Public order by token. With `poll`, refetches every `ORDER_POLL_MS` ONLY
   * while the order is `pending_payment` (stops on any other status); a poll
   * reports `isRefreshing`, never a skeleton.
   */
  function usePublicOrder(token: string | null | undefined, opts: { poll?: boolean } = {}) {
    const q = useQuery<PublicOrder>({
      queryKey: commerceKeys.publicOrder(token ?? ''),
      queryFn: () => unwrap(api.get(`/api/storefront/orders/${token}`)),
      enabled: !!token,
      refetchInterval: opts.poll
        ? (query) => (query.state.data?.status === 'pending_payment' ? ORDER_POLL_MS : false)
        : false,
    });
    return signals(q);
  }
  function useAccessLink() {
    return useMutation({
      mutationFn: (b: AccessLinkRequest) => api.post('/api/storefront/orders/access-link', b),
    });
  }
  function usePrivacyRequest() {
    return useMutation({
      mutationFn: (b: PrivacyRequestInput) => api.post('/api/storefront/privacy-requests', b),
    });
  }

  return {
    useProfile,
    useSaveProfile,
    useCnpjLookup,
    useCategories,
    useCategoryMutations,
    useProducts,
    useProduct,
    useProductMutations,
    useOffers,
    useOfferMutations,
    useMediaMutations,
    useCoupons,
    useCouponMutations,
    useCustomers,
    useCustomer,
    useExportCustomer,
    useAnonymizeCustomer,
    useOrders,
    useOrder,
    useCancelOrder,
    useStorefront,
    useCatalog,
    useStorefrontProduct,
    useQuote,
    useCheckout,
    usePublicOrder,
    useAccessLink,
    usePrivacyRequest,
  };
}

export type CommerceHooks = ReturnType<typeof createCommerceHooks>;
