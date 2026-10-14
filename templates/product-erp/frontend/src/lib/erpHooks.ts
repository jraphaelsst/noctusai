/** The ERP organ hooks of {{PRODUCT_NAME}}, built once over this product's authenticated api client. */
import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  createContractsHooks,
  createFinanceHooks,
  createInventoryHooks,
  createItemsHooks,
  createPartiesHooks,
  createPurchasingHooks,
  createQuotesHooks,
  financeKeys,
  inventoryKeys,
} from "@noctusai/lib";

import { api } from "@/lib/api";

export const financeHooks = createFinanceHooks(api);
export const partiesHooks = createPartiesHooks(api);
export const itemsHooks = createItemsHooks(api);
export const inventoryHooks = createInventoryHooks(api);
export const contractsHooks = createContractsHooks(api);
export const quotesHooks = createQuotesHooks(api);

/**
 * Purchasing hooks bound to the app's query client: a posted receipt moves stock and books a payable, so both
 * organs' reads are invalidated (`onReceived` is the organ's seam for exactly that).
 */
export function usePurchasingHooks() {
  const qc = useQueryClient();
  return React.useMemo(
    () =>
      createPurchasingHooks(api, {
        onReceived: () =>
          Promise.all([
            qc.invalidateQueries({ queryKey: inventoryKeys.all }),
            qc.invalidateQueries({ queryKey: financeKeys.all }),
          ]),
      }),
    [qc],
  );
}
