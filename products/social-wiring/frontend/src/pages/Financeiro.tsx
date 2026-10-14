/**
 * Financeiro -- the seed finance organ (`@noctusai/lib` FinanceShell) mounted at `/financeiro/*`, on the `/api/finance` API.
 * The URL segment <-> section mapping is the organ's own (`financeSectionFromPath`); the shell stays product-agnostic.
 * `isAdmin` is a UX gate only -- the server enforces every write.
 */
import { useLocation, useNavigate } from "react-router-dom";
import { FinanceShell, createFinanceHooks, financeSectionFromPath, financeSectionPath } from "@noctusai/lib";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";
import { api } from "@/lib/api";

const BASE = "/financeiro";
const hooks = createFinanceHooks(api);

export default function Financeiro() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const isAdmin = useIsOrgAdmin();
  const section = financeSectionFromPath(pathname.startsWith(BASE) ? pathname.slice(BASE.length) : "");

  return (
    <div className="space-y-4 p-4">
      <h1 className="text-2xl font-semibold">Financeiro</h1>
      <FinanceShell
        hooks={hooks}
        isAdmin={isAdmin}
        section={section}
        onSectionChange={(key) => navigate(`${BASE}/${financeSectionPath(key)}`.replace(/\/+$/, ""))}
      />
    </div>
  );
}
