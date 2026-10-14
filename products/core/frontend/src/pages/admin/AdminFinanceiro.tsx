/**
 * AdminFinanceiro -- NOC's own books: the seed finance organ (`@noctusai/lib` FinanceShell) mounted at
 * `/admin/financeiro/*`, on the `/api/finance` API (platform admins only; `CoreLayout` already gates `/admin/*`).
 * `isAdmin` is a UX gate only -- the server enforces every write.
 * NOC-REMEDIATE[core-finance-billing-bridge]: nothing feeds the books yet (billing/licensing -> fin entries) -- 2026-10-14.
 */
import { useLocation, useNavigate } from 'react-router-dom';
import { FinanceShell, createFinanceHooks, financeSectionFromPath, financeSectionPath } from '@noctusai/lib';
import { api } from '../../lib/api';
import { useAuth } from '../../lib/auth-context';

const BASE = '/admin/financeiro';
const hooks = createFinanceHooks(api);

export function AdminFinanceiro() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { isAdmin } = useAuth();
  const section = financeSectionFromPath(pathname.startsWith(BASE) ? pathname.slice(BASE.length) : '');

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Financeiro da plataforma</h1>
      <FinanceShell
        hooks={hooks}
        isAdmin={isAdmin}
        section={section}
        onSectionChange={(key) => navigate(`${BASE}/${financeSectionPath(key)}`.replace(/\/+$/, ''))}
      />
    </div>
  );
}
