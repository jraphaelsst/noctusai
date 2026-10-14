/**
 * `/parceiros` -- the parties organ (PF/PJ, CPF/CNPJ, roles customer / supplier / employee / carrier).
 * `canWrite` is the UX gate only; the server enforces org-admin on every write.
 */
import { PartiesTable } from "@noctusai/lib";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { partiesHooks } from "@/lib/erpHooks";

export default function Parceiros() {
  const isAdmin = useIsOrgAdmin();
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-foreground">Parceiros</h1>
      <PartiesTable hooks={partiesHooks} canWrite={isAdmin} />
    </div>
  );
}
