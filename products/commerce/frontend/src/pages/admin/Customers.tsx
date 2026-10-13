/**
 * `/admin/clientes` — customers via the organ's `CustomersTable` (search,
 * pagination, detail with field provenance, orders, consents, and the
 * `PrivacyActions` export / anonymize). This is ALSO the privacy-request
 * desk: P3 stores verified data-subject requests on the customer record and
 * has no org-wide queue endpoint.
 *
 * NOC-REMEDIATE[commerce-privacy-queue]: add the organ's request queue here
 * once `GET /api/commerce/privacy-requests` + resolve exist (CONTRACT-DELTAS D4).
 */
import { CustomersTable } from "@noctusai/lib";

import { AdminFrame } from "@/components/AdminFrame";
import { staffCommerce } from "@/lib/commerce";
import { usePageT } from "@/lib/i18n";

function PrivacyNote() {
  const { t } = usePageT();
  return (
    <aside className="rounded-md border bg-muted/40 p-3 text-sm" aria-label={t("admin.privacy_title")}>
      <p className="font-medium">{t("admin.privacy_title")}</p>
      <p className="text-muted-foreground">{t("admin.privacy_intro")}</p>
    </aside>
  );
}

export default function Customers() {
  return (
    <AdminFrame titleKey="admin.customers_title" introKey="admin.customers_intro">
      <PrivacyNote />
      <CustomersTable hooks={staffCommerce} />
    </AdminFrame>
  );
}
