/**
 * The back-office organ hooks beyond commerce, bound once for this product (staff = the seed `ApiClient`:
 * auth header, org context, 401/403 handling). One instance per organ so every page shares one query-key
 * space.
 *
 * - `staffFinance`   → `/api/finance` (mounted: accounts, entries, reports, reconciliation, DRE, exports)
 * - `staffItems`     → `/api/items` (mounted: SKU catalog + fiscal data)
 * - `staffParties`   → `/api/parties` (NOT mounted in this host yet)
 * - `staffInventory` → `/api/inventory` (NOT mounted in this host yet)
 *
 * NOC-REMEDIATE[commerce-parties-inventory-mount]: mount the parties + inventory routers in
 * `products/commerce/backend/app/main.py` (with their migrations), then promote the `parceiros` / `estoque`
 * `status_pagina` rows to `producao` (migration 019 leaves them `desenvolvimento`) — 2026-10-14.
 */
import { createFinanceHooks, createInventoryHooks, createItemsHooks, createPartiesHooks } from "@noctusai/lib";

import { api } from "@/lib/api";

export const staffFinance = createFinanceHooks(api);
export const staffItems = createItemsHooks(api);
export const staffParties = createPartiesHooks(api);
export const staffInventory = createInventoryHooks(api);
