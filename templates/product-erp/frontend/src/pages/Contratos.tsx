/**
 * `/contratos` -- the contracts organ (billing models, versions/aditivos, readjustment, termination; billing job in the backend).
 * `canWrite` is the UX gate only; the server enforces org-admin on every write.
 */
import { ContractsTable } from "@noctusai/lib";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { contractsHooks } from "@/lib/erpHooks";

export default function Contratos() {
  const isAdmin = useIsOrgAdmin();
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-foreground">Contratos</h1>
      <ContractsTable hooks={contractsHooks} canWrite={isAdmin} />
    </div>
  );
}
