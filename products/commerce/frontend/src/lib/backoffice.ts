/**
 * The back-office organ hooks beyond commerce, bound once for this product (staff = the seed `ApiClient`:
 * auth header, org context, 401/403 handling). One instance per organ so every page shares one query-key
 * space.
 *
 * - `staffFinance`   → `/api/finance` (mounted: accounts, entries, reports, reconciliation, DRE, exports)
 * - `staffItems`     → `/api/items` (mounted: SKU catalog + fiscal data)
 * - `staffParties`   → `/api/parties`
 * - `staffInventory` → `/api/inventory`
 * - `staffPurchasing` → `/api/purchasing` (orders, receipts, approvers; a receipt also moves stock + payables, so the
 *                       page invalidates those reads — `PurchaseReceiveDialog.onDone`)
 * - `staffQuotes`    → `/api/quotes`; `publicQuotes` → `/api/public/quotes/{token}` (the customer's signed link: plain
 *                       same-origin fetch, the token IS the credential)
 * - `staffContracts` → `/api/contracts`
 * - `staffTeam`      → `/api/team` (the roster, to name the purchase approvers)
 */
import {
  createContractsHooks,
  createFinanceHooks,
  createInventoryHooks,
  createItemsHooks,
  createPartiesHooks,
  createPurchasingHooks,
  createQuotesHooks,
  createQuotesPublicHooks,
  createTeamHooks,
} from "@noctusai/lib";

import { api } from "@/lib/api";
import { STOREFRONT_API_BASE } from "@/lib/commerce";

export const staffFinance = createFinanceHooks(api);
export const staffItems = createItemsHooks(api);
export const staffParties = createPartiesHooks(api);
export const staffInventory = createInventoryHooks(api);
export const staffPurchasing = createPurchasingHooks(api);
export const staffQuotes = createQuotesHooks(api);
export const publicQuotes = createQuotesPublicHooks(STOREFRONT_API_BASE);
export const staffContracts = createContractsHooks(api);
export const staffTeam = createTeamHooks(api);
