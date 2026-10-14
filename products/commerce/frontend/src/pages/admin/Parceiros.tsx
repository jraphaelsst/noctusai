/**
 * `/admin/parceiros` — customers, suppliers and other partners: the seed `PartiesTable` (search, role / kind
 * filters, editor dialog, CSV export / import). Writes are for org admins (UX; the server enforces).
 *
 * NOC-REMEDIATE[commerce-parties-inventory-mount]: `/api/parties` is not mounted in this host's backend yet, so
 * the page's `status_pagina` row (migration 019) is `desenvolvimento` (owner/dev/admin only) and the list shows
 * its error state until the router is mounted — 2026-10-14. See `@/lib/backoffice`.
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
