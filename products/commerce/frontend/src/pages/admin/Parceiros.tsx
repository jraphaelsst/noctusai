/**
 * `/admin/parceiros` — customers, suppliers and other partners: the seed `PartiesTable` (search, role / kind
 * filters, editor dialog, CSV export / import). Writes are for org admins (UX; the server enforces).
 */
import { PartiesTable } from "@noctusai/lib";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { AdminFrame } from "@/components/AdminFrame";
import { staffParties } from "@/lib/backoffice";

export default function Parceiros() {
  const isAdmin = useIsOrgAdmin();
  return (
    <AdminFrame titleKey="admin.parties_title" introKey="admin.parties_intro">
      <PartiesTable hooks={staffParties} canWrite={isAdmin} />
    </AdminFrame>
  );
}
