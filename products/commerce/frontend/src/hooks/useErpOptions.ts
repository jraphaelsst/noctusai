/**
 * Picker options the ERP pages hand to organs that only take arrays (quotes, the product editor's item link).
 *
 * Both lists are the FIRST 100 active rows (the API's page-size cap): a catalog or customer base larger than that needs a
 * searchable picker in the organ.
 * NOC-REMEDIATE[erp-picker-search]: `QuotesTable` / `ProductEditor` take option arrays; a typeahead picker belongs in the
 * organs (like `PurchaseOrderEditor`'s `partiesHooks` / `itemsHooks` search) — 2026-10-14.
 */
import { useQuery } from "@tanstack/react-query";
import type { Item, Party, QuoteItemOption, QuotePartyOption } from "@noctusai/lib";

import { api } from "@/lib/api";

interface Page<T> {
  data: T[];
}

const PAGE = 100;

export function useItemOptions(enabled = true) {
  return useQuery({
    queryKey: ["erp-options", "items"],
    enabled,
    queryFn: async () => (await api.get<Page<Item>>("/api/items", { active: "true", page_size: PAGE })).data,
    staleTime: 60_000,
  });
}

/** Active customers (a party can be customer + supplier at once). */
export function useCustomerOptions(enabled = true) {
  return useQuery({
    queryKey: ["erp-options", "customers"],
    enabled,
    queryFn: async () => (await api.get<Page<Party>>("/api/parties", { role: "customer", active: "true", page_size: PAGE })).data,
    staleTime: 60_000,
  });
}

export function useQuoteOptions(): { parties: QuotePartyOption[]; items: QuoteItemOption[] } {
  const parties = useCustomerOptions().data ?? [];
  const items = useItemOptions().data ?? [];
  return {
    parties: parties.map((p) => ({ id: p.id, name: p.trade_name || p.legal_name, email: p.email })),
    items: items.map((i) => ({
      id: i.id,
      name: `${i.sku} · ${i.name}`,
      unit: i.unit,
      price_cents: i.price_cents,
      kind: i.item_type === "service" ? ("service" as const) : ("goods" as const),
    })),
  };
}
