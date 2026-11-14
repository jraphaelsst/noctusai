/**
 * `/financeiro/*` -- the seed finance organ (`FinanceRoutedPage`): receivables, payables, cash flow, DRE,
 * bank reconciliation, registers and the accountant pack, over this product's `/api/finance/*`
 * (mounted by `mount_finance` in `app/main.py`). The URL <-> section sync is the organ's own.
 * `isAdmin` is the UX gate only -- the server enforces `admin_obrigatorio` on every write and export.
 */
import { FinanceRoutedPage } from "@noctusai/lib";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { api } from "@/lib/api";

export default function Financeiro() {
  return <FinanceRoutedPage basePath="/financeiro" api={api} isAdmin={useIsOrgAdmin()} />;
}
