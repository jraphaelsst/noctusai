/**
 * Configurações > Loja (`/admin/configuracoes/loja`) — store settings: the profile (CNPJ, tax regime, locale/currency, brand) via the organ's
 * `StoreProfileForm`, the card installments (D33/D41) via `InstallmentsSettings` and the fiscal data (IM/IE,
 * NFS-e mode, A1 certificate, Nacional cutover) via `FiscalSettingsForm`. The money sections write only for org
 * admins (UX hint — the server enforces).
 */
import { FiscalSettingsForm, InstallmentsSettings, StoreProfileForm } from "@noctusai/lib";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { useIsPlatformAdmin } from "@/hooks/useStorefrontHosts";
import { staffCommerce } from "@/lib/commerce";
import { usePageT } from "@/lib/i18n";

export function StoreProfileBody() {
  const { t } = usePageT();
  const isPlatformAdmin = useIsPlatformAdmin();
  const isAdmin = useIsOrgAdmin();
  return (
    <div className="space-y-6">
      <StoreProfileForm hooks={staffCommerce} isPlatformAdmin={isPlatformAdmin} />
      <section aria-label={t("admin.settings_installments")} className="border-t pt-6">
        <InstallmentsSettings hooks={staffCommerce} isAdmin={isAdmin} />
      </section>
      <section aria-label={t("admin.settings_fiscal")} className="border-t pt-6">
        <FiscalSettingsForm hooks={staffCommerce} isAdmin={isAdmin} />
      </section>
    </div>
  );
}
