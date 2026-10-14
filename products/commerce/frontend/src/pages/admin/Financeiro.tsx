/**
 * `/admin/financeiro/*` — the seed `FinanceShell` (visão geral · receber · pagar · fluxo de caixa · DRE ·
 * conciliação · cadastros · contador) over `/api/finance`. The URL segment ⇄ section mapping is the organ's
 * (`financeSectionFromPath` / `financeSectionPath`), so a section is deep-linkable and the browser back button
 * works; an unknown segment redirects to the base. Write actions are offered to org admins only (UX — the
 * server enforces every write again).
 */
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { FinanceShell, financeSectionFromPath, financeSectionPath, type FinanceSectionKey } from "@noctusai/lib";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { AdminFrame } from "@/components/AdminFrame";
import { staffFinance } from "@/lib/backoffice";

export const FINANCE_BASE_PATH = "/admin/financeiro";

const pathFor = (key: FinanceSectionKey) => {
  const seg = financeSectionPath(key);
  return seg ? `${FINANCE_BASE_PATH}/${seg}` : FINANCE_BASE_PATH;
};

export default function Financeiro() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const isAdmin = useIsOrgAdmin();
  const segment = pathname.slice(FINANCE_BASE_PATH.length).replace(/^\/+|\/+$/g, "");
  const section = financeSectionFromPath(segment);
  // A segment the organ does not know (typo, stale bookmark) goes to the canonical URL of the section it maps to.
  if (segment !== financeSectionPath(section)) return <Navigate to={pathFor(section)} replace />;
  return (
    <AdminFrame titleKey="admin.finance_title" introKey="admin.finance_intro">
      <FinanceShell hooks={staffFinance} isAdmin={isAdmin} section={section} onSectionChange={(key) => navigate(pathFor(key))} />
    </AdminFrame>
  );
}
