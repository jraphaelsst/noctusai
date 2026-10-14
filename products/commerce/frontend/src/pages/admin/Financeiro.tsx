/**
 * `/admin/financeiro/*` — the seed `FinanceRoutedPage` (visão geral · receber · pagar · fluxo de caixa · DRE ·
 * conciliação · cadastros · contador) over `/api/finance`. The organ owns the URL ⇄ section sync (deep links, back
 * button, unknown segment redirects to the base). Write actions are offered to org admins only (UX — the
 * server enforces every write again).
 */
import { FinanceRoutedPage } from "@noctusai/lib";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { AdminFrame } from "@/components/AdminFrame";
import { staffFinance } from "@/lib/backoffice";

export const FINANCE_BASE_PATH = "/admin/financeiro";

export default function Financeiro() {
  const isAdmin = useIsOrgAdmin();
  return (
    <AdminFrame titleKey="admin.finance_title" introKey="admin.finance_intro">
      <FinanceRoutedPage basePath={FINANCE_BASE_PATH} hooks={staffFinance} isAdmin={isAdmin} />
    </AdminFrame>
  );
}
