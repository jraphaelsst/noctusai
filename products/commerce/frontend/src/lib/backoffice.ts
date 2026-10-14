/**
 * The back-office organ hooks beyond commerce, bound once for this product (staff = the seed `ApiClient`:
 * auth header, org context, 401/403 handling). One instance per organ so every page shares one query-key
 * space.
 *
 * - `staffFinance`   → `/api/finance` (mounted: accounts, entries, reports, reconciliation, DRE, exports)
 * - `staffItems`     → `/api/items` (mounted: SKU catalog + fiscal data)
 * - `staffParties`   → `/api/parties`
 * - `staffInventory` → `/api/inventory`
 *
 * NOC-REMEDIATE[commerce-purchasing-mount]: `createPurchasingHooks` + the `/admin/compras` page land with the
 * purchasing mount (see app/routers/commerce_routers.py) — 2026-10-14.
 */
import { createFinanceHooks, createInventoryHooks, createItemsHooks, createPartiesHooks } from "@noctusai/lib";

import { api } from "@/lib/api";

export const staffFinance = createFinanceHooks(api);
export const staffItems = createItemsHooks(api);
export const staffParties = createPartiesHooks(api);
export const staffInventory = createInventoryHooks(api);
