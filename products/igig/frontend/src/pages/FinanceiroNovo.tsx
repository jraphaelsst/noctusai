/**
 * Financeiro (novo) -- the seed finance organ (`@noctusai/lib` FinanceRoutedPage) mounted at `/financeiro-novo/*`, on the `/api/finance` API.
 * `isAdmin` is a UX gate only -- the server enforces every write.
 */
import { FinanceRoutedPage } from "@noctusai/lib";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";
import { api } from "@/lib/api";

export default function FinanceiroNovo() {
  return <FinanceRoutedPage basePath="/financeiro-novo" api={api} isAdmin={useIsOrgAdmin()} title="Financeiro (novo)" className="space-y-4 p-4" />;
}
