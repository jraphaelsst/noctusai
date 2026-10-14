/**
 * `/admin/contratos` — contracts with recurring billing: the list (status / model filters) and, through the table's
 * built-in `ContractEditor`, a contract's terms, the upcoming receivables it will book into finance
 * (`ContractBillingPreview`), the append-only history of amendments (`ContractTimeline`) and the lifecycle actions
 * (activate, suspend, terminate, amend, readjust). A contract born from an accepted SERVICES quote opens here as a DRAFT
 * to be reviewed and activated. The customer comes from the parties organ (customers). Writes are for org admins (UX; the
 * server enforces).
 */
import { ContractsTable } from "@noctusai/lib";
import { Select, useIsOrgAdmin } from "@noctusai/lib/design-system";

import { AdminFrame } from "@/components/AdminFrame";
import { useCustomerOptions } from "@/hooks/useErpOptions";
import { staffContracts } from "@/lib/backoffice";

/** The editor's party seam: pick one of the org's customers (or leave the customer typed by name). */
function PartyPicker({ value, onPick }: { value: string | null; onPick: (party: { id: string; name: string } | null) => void }) {
  const customers = useCustomerOptions().data ?? [];
  return (
    <Select
      aria-label="Cliente"
      value={value ?? ""}
      onChange={(e) => {
        const found = customers.find((c) => c.id === e.target.value);
        onPick(found ? { id: found.id, name: found.trade_name || found.legal_name } : null);
      }}
    >
      <option value="">—</option>
      {customers.map((c) => (
        <option key={c.id} value={c.id}>{c.trade_name || c.legal_name}</option>
      ))}
    </Select>
  );
}

export default function Contratos() {
  const isAdmin = useIsOrgAdmin();
  return (
    <AdminFrame titleKey="admin.contracts_title" introKey="admin.contracts_intro">
      <ContractsTable hooks={staffContracts} canWrite={isAdmin} renderPartyPicker={(props) => <PartyPicker {...props} />} />
    </AdminFrame>
  );
}
