/**
 * Configurações > Integrações (`/admin/configuracoes/integracoes`) — the store's Asaas API key + webhook token through the
 * seed `ApiKeysPanel` (masked hint, set / replace / test / remove). The panel
 * does not gate on role by design; the org-admin UX gate is here (the server
 * enforces `admin_obrigatorio` on writes regardless).
 */
import { ApiKeysPanel } from "@noctusai/lib/components";
import { EmptyState, useIsOrgAdmin } from "@noctusai/lib/design-system";

import { commerceApiKeys } from "@/hooks/useCommerceApiKeys";
import { usePageT } from "@/lib/i18n";

export function KeysBody() {
  const { t } = usePageT();
  const isAdmin = useIsOrgAdmin();
  if (!isAdmin) return <EmptyState message={t("admin.keys_admin_only")} />;
  return <ApiKeysPanel hooks={commerceApiKeys} title={t("admin.keys_title")} />;
}
