/**
 * `/financeiro/*` -- the seed finance organ (`FinanceShell`): receivables, payables, cash flow, DRE,
 * bank reconciliation, registers and the accountant pack, over this product's `/api/finance/*`
 * (mounted by `mount_finance` in `app/main.py`).
 *
 * The section lives in the URL (`/financeiro/receber`, `/financeiro/dre`, ...) via the organ's
 * `financeSectionFromPath` / `financeSectionPath`. `isAdmin` is the UX gate only -- the server
 * enforces `admin_obrigatorio` on every write and export.
 */
import { useNavigate, useParams } from "react-router-dom";
import {
  FinanceShell,
  createFinanceHooks,
  financeSectionFromPath,
  financeSectionPath,
  type FinanceSectionKey,
} from "@noctusai/lib";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { api } from "@/lib/api";

const financeHooks = createFinanceHooks(api);

export default function Financeiro() {
  const params = useParams();
  const navigate = useNavigate();
  const isAdmin = useIsOrgAdmin();
  const section = financeSectionFromPath(params["*"]);

  const onSectionChange = (key: FinanceSectionKey) => {
    const segment = financeSectionPath(key);
    navigate(segment ? `/financeiro/${segment}` : "/financeiro");
  };

  return (
    <FinanceShell hooks={financeHooks} isAdmin={isAdmin} section={section} onSectionChange={onSectionChange} />
  );
}
