/**
 * `/admin/integracoes` — the store's Asaas API key + webhook token through the
 * seed `ApiKeysPanel` (masked hint, set / replace / test / remove). The panel
 * does not gate on role by design; the org-admin UX gate is here (the server
 * enforces `admin_obrigatorio` on writes regardless).
 */
import { ApiKeysPanel } from "@noctusai/lib/components";
import { EmptyState, useIsOrgAdmin } from "@noctusai/lib/design-system";

import { AdminFrame } from "@/components/AdminFrame";
import { commerceApiKeys } from "@/hooks/useCommerceApiKeys";
import { usePageT } from "@/lib/i18n";

function KeysBody() {
  const { t } = usePageT();
  const isAdmin = useIsOrgAdmin();
  if (!isAdmin) return <EmptyState message={t("admin.keys_admin_only")} />;
  return <ApiKeysPanel hooks={commerceApiKeys} title={t("admin.keys_title")} />;
}

export default function ApiKeys() {
  return (
    <AdminFrame titleKey="admin.keys_title" introKey="admin.keys_intro">
      <KeysBody />
    </AdminFrame>
  );
}
