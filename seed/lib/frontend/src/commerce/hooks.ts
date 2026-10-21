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
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { listOps, useCacheWriteMutation } from '../cache-writes';
import { type ApiClient } from '../api';
import { apiErrorCode, apiErrorStatus, createFetchTransport, errorMessage, keep, signals } from '../organ-kit/query';
import { pageOps } from '../organ-kit/page-ops';
import type { FiscalUpdate, FiscalView, Invoice, InvoiceKind } from './fiscalTypes';
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
  RefundInput,
  RegeneratePaymentInput,
  RegeneratePaymentResult,
  OrderRefund,
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
  fiscal: ['commerce', 'staff', 'fiscal'] as const,
  invoices: (orderId: string) => ['commerce', 'staff', 'invoices', orderId] as const,
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

  /**
   * Cache writes (KB § PATTERNS/frontend/mutation-cache-writes.md). Staff writes answer with the saved record, so it
   * goes into the cache the moment it arrives: arrays (`listOps`) and paginated lists (`pageOps`, prefix match) take
   * the row; a detail keeps its nested parts (`offers` / `media` / `items` / `events` are only on GET-by-id, so a
   * PATCH answer is MERGED into the detail, never swapped for it). What the server derives (lists a new row belongs
   * to, totals) refreshes on the background settle. A write with nothing to place says so with a `noc-allow` marker.
   */
  /** Merge a PATCH-style answer into a cached detail without dropping the nested parts only GET-by-id carries. */
  const mergeInto = <T extends object>(old: T | undefined, saved: Partial<T>): T | undefined => listOps.merge(old, saved);

  // ---- staff: profile ----------------------------------------------------
  function useProfile() {
    const q = useQuery<StoreProfile | null>({
      queryKey: commerceKeys.profile,
      queryFn: () => unwrap(api.get('/api/commerce/profile')),
    });
    return signals(q);
  }
  function useSaveProfile() {
    return useCacheWriteMutation<StoreProfile, StoreProfileInput>({
      mutationFn: (body) => unwrap<StoreProfile>(api.put('/api/commerce/profile', body)),
      targets: [{ queryKey: commerceKeys.profile, commit: (_old: StoreProfile | null | undefined, saved: StoreProfile) => saved }],
    });
  }
  function useCnpjLookup() {
    return useMutation({ // noc-allow: invalidate-only — a registry lookup: it changes nothing on the server and no cached query holds its answer
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
    const key = commerceKeys.categories;
    return {
      create: useCacheWriteMutation<Category, CategoryInput>({
        mutationFn: (b) => unwrap<Category>(api.post('/api/commerce/categories', b)),
        targets: [{ queryKey: key, commit: (old: Category[] | undefined, saved: Category) => listOps.replace(old, saved.id, saved) }],
      }),
      update: useCacheWriteMutation<Category, Partial<CategoryInput> & { id: string }>({
        mutationFn: ({ id, ...b }) => unwrap<Category>(api.patch(`/api/commerce/categories/${id}`, b)),
        targets: ({ id, ...changes }) => [
          {
            queryKey: key,
            optimistic: (old: Category[] | undefined) => listOps.patch(old, id, changes as Partial<Category>),
            commit: (old: Category[] | undefined, saved: Category) => listOps.patch(old, id, saved),
          },
        ],
      }),
      remove: useCacheWriteMutation<unknown, string>({
        mutationFn: (id) => api.delete(`/api/commerce/categories/${id}`),
        targets: (id) => [{ queryKey: key, optimistic: (old: Category[] | undefined) => listOps.remove(old, id) }],
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
    const qc = useQueryClient();
    /** The row on every cached list page (prefix: details / offers under the same prefix are not pages, so untouched). */
    const rows = (id: string) => ({
      queryKey: commerceKeys.products,
      match: 'prefix' as const,
      commit: (old: unknown, saved: Product) => pageOps.patch(old, id, saved),
    });
    return {
      create: useCacheWriteMutation<Product, ProductInput>({
        mutationFn: (b) => unwrap<Product>(api.post('/api/commerce/products', b)),
        // which list page / filter the new product lands on is the server's call: lists converge on the settle
        targets: [{ queryKey: commerceKeys.products }],
        // a product that was just created has no offers or media yet: its detail is fully known
        onSuccess: (saved) => {
          qc.setQueryData(commerceKeys.product(saved.id), { offers: [], media: [], ...saved });
        },
      }),
      update: useCacheWriteMutation<Product, Partial<ProductInput> & { id: string }>({
        mutationFn: ({ id, ...b }) => unwrap<Product>(api.patch(`/api/commerce/products/${id}`, b)),
        targets: ({ id }) => [
          { queryKey: commerceKeys.product(id), commit: (old: Product | undefined, saved: Product) => mergeInto(old, saved) },
          rows(id),
        ],
      }),
      remove: useCacheWriteMutation<unknown, string>({
        mutationFn: (id) => api.delete(`/api/commerce/products/${id}`),
        targets: (id) => [{ queryKey: commerceKeys.products, match: 'prefix', optimistic: (old: unknown) => pageOps.remove(old, id) }],
      }),
      setStatus: useCacheWriteMutation<Product, { id: string; status: ProductStatus }>({
        mutationFn: ({ id, status }) => unwrap<Product>(api.post(`/api/commerce/products/${id}/status`, { status })),
        // draw the new status on the click; a refusal (422 `sem_oferta_ativa`) rolls it back
        targets: ({ id, status }) => [
          {
            queryKey: commerceKeys.product(id),
            optimistic: (old: Product | undefined) => mergeInto(old, { status }),
            commit: (old: Product | undefined, saved: Product) => mergeInto(old, saved),
          },
          {
            ...rows(id),
            optimistic: (old: unknown) => pageOps.patch(old, id, { status }),
          },
        ],
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
    // Offers live under the product detail key (`offers(productId)` AND the detail's embedded `offers`): both take the
    // row. Product LISTS show a derived summary of the offers, so they refresh on the settle.
    const offersKey = commerceKeys.offers(productId);
    const embedded = (edit: (offers: Offer[]) => Offer[] | undefined) => (old: Product | undefined) =>
      old && Array.isArray(old.offers) ? mergeInto(old, { offers: edit(old.offers) ?? old.offers }) : old;
    return {
      create: useCacheWriteMutation<Offer, OfferInput>({
        mutationFn: (b) => unwrap<Offer>(api.post(`/api/commerce/products/${productId}/offers`, b)),
        targets: [
          { queryKey: offersKey, commit: (old: Offer[] | undefined, saved: Offer) => listOps.replace(old, saved.id, saved) },
          { queryKey: commerceKeys.product(productId), commit: (old: Product | undefined, saved: Offer) => embedded((offers) => listOps.replace(offers, saved.id, saved))(old) },
        ],
        invalidate: [commerceKeys.products],
      }),
      update: useCacheWriteMutation<Offer, Partial<OfferInput> & { id: string }>({
        mutationFn: ({ id, ...b }) => unwrap<Offer>(api.patch(`/api/commerce/products/${productId}/offers/${id}`, b)),
        targets: ({ id, ...changes }) => [
          {
            queryKey: offersKey,
            optimistic: (old: Offer[] | undefined) => listOps.patch(old, id, changes as Partial<Offer>),
            commit: (old: Offer[] | undefined, saved: Offer) => listOps.patch(old, id, saved),
          },
          {
            queryKey: commerceKeys.product(productId),
            optimistic: embedded((offers) => listOps.patch(offers, id, changes as Partial<Offer>)),
            commit: (old: Product | undefined, saved: Offer) => embedded((offers) => listOps.patch(offers, id, saved))(old),
          },
        ],
        invalidate: [commerceKeys.products],
      }),
      remove: useCacheWriteMutation<unknown, string>({
        mutationFn: (id) => api.delete(`/api/commerce/products/${productId}/offers/${id}`),
        targets: (id) => [
          { queryKey: offersKey, optimistic: (old: Offer[] | undefined) => listOps.remove(old, id) },
          { queryKey: commerceKeys.product(productId), optimistic: embedded((offers) => listOps.remove(offers, id)) },
        ],
        invalidate: [commerceKeys.products],
      }),
    };
  }
  function useMediaMutations(productId: string) {
    const detail = commerceKeys.product(productId);
    const embeddedMedia = (edit: (media: Media[]) => Media[] | undefined) => (old: Product | undefined) =>
      old && Array.isArray(old.media) ? mergeInto(old, { media: edit(old.media) ?? old.media }) : old;
    return {
      upload: useCacheWriteMutation<Media, { file: File; alt?: string }>({
        mutationFn: ({ file, alt }) => {
          const form = new FormData();
          form.append('file', file);
          if (alt) form.append('alt', alt);
          return unwrap<Media>(api.upload(`/api/commerce/products/${productId}/media`, form));
        },
        targets: [{ queryKey: detail, commit: (old: Product | undefined, saved: Media) => embeddedMedia((media) => listOps.replace(media, saved.id, saved))(old) }],
      }),
      remove: useCacheWriteMutation<unknown, string>({
        mutationFn: (mediaId) => api.delete(`/api/commerce/products/${productId}/media/${mediaId}`),
        targets: (mediaId) => [{ queryKey: detail, optimistic: embeddedMedia((media) => listOps.remove(media, mediaId)) }],
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
    const key = commerceKeys.coupons;
    return {
      create: useCacheWriteMutation<Coupon, CouponInput>({
        mutationFn: (b) => unwrap<Coupon>(api.post('/api/commerce/coupons', b)),
        targets: [{ queryKey: key, commit: (old: Coupon[] | undefined, saved: Coupon) => listOps.replace(old, saved.id, saved) }],
      }),
      update: useCacheWriteMutation<Coupon, Partial<CouponInput> & { id: string }>({
        mutationFn: ({ id, ...b }) => unwrap<Coupon>(api.patch(`/api/commerce/coupons/${id}`, b)),
        targets: ({ id, ...changes }) => [
          {
            queryKey: key,
            optimistic: (old: Coupon[] | undefined) => listOps.patch(old, id, changes as Partial<Coupon>),
            commit: (old: Coupon[] | undefined, saved: Coupon) => listOps.patch(old, id, saved),
          },
        ],
      }),
      remove: useCacheWriteMutation<unknown, string>({
        mutationFn: (id) => api.delete(`/api/commerce/coupons/${id}`),
        targets: (id) => [{ queryKey: key, optimistic: (old: Coupon[] | undefined) => listOps.remove(old, id) }],
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
    return useMutation({ // noc-allow: invalidate-only — an LGPD data export: a read of the customer's dump, it changes nothing and no cached query holds it
      mutationFn: (id: string) => unwrap<Record<string, unknown>>(api.get(`/api/commerce/customers/${id}/export`)),
    });
  }
  function useAnonymizeCustomer() {
    return useCacheWriteMutation<Customer, string>({
      mutationFn: (id) => unwrap<Customer>(api.post(`/api/commerce/customers/${id}/anonymize`, {})),
      // the anonymised customer replaces the detail (orders / consents stay) and its row on every cached list page
      targets: (id) => [
        { queryKey: commerceKeys.customer(id), commit: (old: Customer | undefined, saved: Customer) => mergeInto(old, saved) },
        { queryKey: commerceKeys.customers, match: 'prefix', commit: (old: unknown, saved: Customer) => pageOps.patch(old, id, saved) },
      ],
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
    return useCacheWriteMutation<Order, string>({
      mutationFn: (id) => unwrap<Order>(api.post(`/api/commerce/orders/${id}/cancel`, {})),
      // the cancelled order goes into its detail (items / events kept) and its row on every cached list page
      targets: (id) => [
        { queryKey: commerceKeys.order(id), commit: (old: Order | undefined, saved: Order) => mergeInto(old, saved) },
        { queryKey: commerceKeys.orders, match: 'prefix', commit: (old: unknown, saved: Order) => pageOps.patch(old, id, saved) },
      ],
    });
  }

  /**
   * Refund (full when `amount_cents` is omitted, partial otherwise). `idempotencyKey` rides as the
   * `Idempotency-Key` header: re-sending the SAME key after an inconclusive attempt returns the same
   * refund instead of creating a second one. A result with `status: 'requested'` is "em andamento".
   */
  function useCreateRefund() {
    const qc = useQueryClient();
    return useMutation({ // noc-allow: invalidate-only — the answer is a refund row that no cached query lists; what a refund changes (order status, refunded totals, events) is server-derived, so the order re-reads
      mutationFn: ({ orderId, idempotencyKey, ...body }: RefundInput & { orderId: string; idempotencyKey: string }) =>
        unwrap<OrderRefund>(
          api.post(`/api/commerce/orders/${orderId}/refunds`, body, { headers: { 'Idempotency-Key': idempotencyKey } }),
        ),
      onSuccess: (_r, v) => Promise.all([qc.invalidateQueries({ queryKey: commerceKeys.order(v.orderId) }), qc.invalidateQueries({ queryKey: commerceKeys.orders })]),
    });
  }

  // ---- staff: fiscal (CONTRACT P4 §2.5) ----------------------------------
  function useFiscal() {
    const q = useQuery<FiscalView>({
      queryKey: commerceKeys.fiscal,
      queryFn: () => unwrap(api.get('/api/commerce/fiscal')),
    });
    return signals(q);
  }
  function useFiscalMutations() {
    const qc = useQueryClient();
    // the server answers with the whole fiscal view: it replaces the cached one
    const fiscalView = { queryKey: commerceKeys.fiscal, commit: (_old: FiscalView | undefined, saved: FiscalView) => saved };
    return {
      save: useCacheWriteMutation<FiscalView, FiscalUpdate>({
        mutationFn: (b) => unwrap<FiscalView>(api.put('/api/commerce/fiscal', b)),
        targets: [fiscalView],
      }),
      /** The A1 (.pfx) and its password are forwarded to the invoice provider and never stored by us. */
      uploadCertificate: useMutation({ // noc-allow: invalidate-only — the answer is an opaque provider receipt (the certificate is never stored by us); the fiscal view's certificate status is server-derived, so it re-reads
        mutationFn: ({ file, password }: { file: File; password: string }) => {
          const form = new FormData();
          form.append('file', file);
          form.append('password', password);
          return unwrap<unknown>(api.upload('/api/commerce/fiscal/certificate', form));
        },
        onSuccess: () => qc.invalidateQueries({ queryKey: commerceKeys.fiscal }),
      }),
      cutover: useCacheWriteMutation<FiscalView, string>({
        mutationFn: (confirm) => unwrap<FiscalView>(api.post('/api/commerce/fiscal/nfse-cutover', { confirm })),
        targets: [fiscalView],
      }),
      rollback: useCacheWriteMutation<FiscalView, string>({
        mutationFn: (confirm) => unwrap<FiscalView>(api.post('/api/commerce/fiscal/nfse-cutover/rollback', { confirm })),
        targets: [fiscalView],
      }),
    };
  }
  function useOrderInvoices(orderId: string | null | undefined) {
    const q = useQuery<Invoice[]>({
      queryKey: commerceKeys.invoices(orderId ?? ''),
      queryFn: async () => (await api.get<{ data: Invoice[] }>(`/api/commerce/orders/${orderId}/invoices`)).data,
      enabled: !!orderId,
    });
    return signals(q);
  }
  function useInvoiceMutations(orderId: string) {
    const key = commerceKeys.invoices(orderId);
    return {
      issue: useCacheWriteMutation<Invoice, InvoiceKind>({
        mutationFn: (kind) => unwrap<Invoice>(api.post(`/api/commerce/orders/${orderId}/invoices`, { kind })),
        targets: [{ queryKey: key, commit: (old: Invoice[] | undefined, saved: Invoice) => listOps.replace(old, saved.id, saved) }],
      }),
      cancel: useCacheWriteMutation<Invoice, { id: string; reason: string }>({
        mutationFn: ({ id, reason }) => unwrap<Invoice>(api.post(`/api/commerce/invoices/${id}/cancel`, { reason })),
        targets: ({ id }) => [{ queryKey: key, commit: (old: Invoice[] | undefined, saved: Invoice) => listOps.patch(old, id, saved) }],
      }),
    };
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
    return useMutation({ // noc-allow: invalidate-only — a price quote (nothing is written server-side, no cached query holds it)
      mutationFn: (b: QuoteRequest) => unwrap<Quote>(api.post('/api/storefront/checkout/quote', b)),
    });
  }
  function useCheckout() {
    return useMutation({ // noc-allow: invalidate-only — creates the order and answers with the payment hand-off; no cached read holds an order that did not exist yet (the status page fetches it by token)
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
  /**
   * "Gerar novo pagamento": regenerate (expired/failed) or switch the method (pending) of an order, by its
   * token. Refreshes the public order afterwards. Rate-limited server-side (429 `muitas_tentativas`).
   */
  function useRegeneratePayment(token: string | null | undefined) {
    return useCacheWriteMutation<RegeneratePaymentResult, RegeneratePaymentInput>({
      mutationFn: (b) => unwrap<RegeneratePaymentResult>(api.post(`/api/storefront/orders/${token}/payment`, b)),
      // the new charge's status / checkout link / PIX QR / expiry go straight into the order on screen
      targets: [
        {
          queryKey: commerceKeys.publicOrder(token ?? ''),
          commit: (old: PublicOrder | undefined, res: RegeneratePaymentResult) =>
            mergeInto(old, Object.fromEntries(Object.entries(res).filter(([, v]) => v !== undefined)) as Partial<PublicOrder>),
        },
      ],
    });
  }
  function useAccessLink() {
    return useMutation({ // noc-allow: invalidate-only — emails the buyer an access link: no cached read changes
      mutationFn: (b: AccessLinkRequest) => api.post('/api/storefront/orders/access-link', b),
    });
  }
  function usePrivacyRequest() {
    return useMutation({ // noc-allow: invalidate-only — files a privacy request: no cached read changes
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
    useCreateRefund,
    useFiscal,
    useFiscalMutations,
    useOrderInvoices,
    useInvoiceMutations,
    useStorefront,
    useCatalog,
    useStorefrontProduct,
    useQuote,
    useCheckout,
    usePublicOrder,
    useRegeneratePayment,
    useAccessLink,
    usePrivacyRequest,
  };
}

export type CommerceHooks = ReturnType<typeof createCommerceHooks>;
