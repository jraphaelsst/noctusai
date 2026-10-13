/**
 * The commerce organ's hooks, bound once for this product.
 *
 * - `staffCommerce` — the back office (`/admin/*`): the seed `ApiClient`
 *   (auth header, org context, 401/403 handling) against `/api/commerce/*`.
 * - `storefrontCommerce` — the public storefront: plain same-origin `fetch`
 *   (no login) against `/api/storefront/*`; the backend resolves the store
 *   from the `Host` header (CONTRACT §4).
 *
 * Pages import these; they never call `createCommerceHooks` themselves, so
 * every page shares one query-key space per audience.
 */
import { createCommerceHooks, createFetchTransport } from "@noctusai/lib";

import { api } from "@/lib/api";

export const staffCommerce = createCommerceHooks(api);

/** Same-origin base: the house container serves the SPA and `/api/*` together. */
export const STOREFRONT_API_BASE = "";

/** Public transport — exported for the product hooks that cover A1 routes the organ does not wrap yet. */
export const storefrontTransport = createFetchTransport(STOREFRONT_API_BASE);

export const storefrontCommerce = createCommerceHooks(storefrontTransport);
