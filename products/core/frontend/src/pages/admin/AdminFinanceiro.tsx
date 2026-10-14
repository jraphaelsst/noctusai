/**
 * AdminFinanceiro -- NOC's own books: the seed finance organ (`@noctusai/lib` FinanceRoutedPage) mounted at
 * `/admin/financeiro/*`, on the `/api/finance` API (platform admins only; `CoreLayout` already gates `/admin/*`).
 * `isAdmin` is a UX gate only -- the server enforces every write.
 * NOC-REMEDIATE[core-finance-billing-bridge]: nothing feeds the books yet (billing/licensing -> fin entries) -- 2026-10-14.
 */
import { FinanceRoutedPage } from '@noctusai/lib';
import { api } from '../../lib/api';
import { useAuth } from '../../lib/auth-context';

export function AdminFinanceiro() {
  const { isAdmin } = useAuth();
  return <FinanceRoutedPage basePath="/admin/financeiro" api={api} isAdmin={isAdmin} title="Financeiro da plataforma" className="space-y-4" />;
}
