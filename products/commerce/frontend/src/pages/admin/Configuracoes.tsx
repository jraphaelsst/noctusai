/**
 * `/admin/configuracoes/*` -- store settings, one tab per sub-route (the seed `SectionTabsPage`): Loja (profile,
 * installments, fiscal), Endereços (storefront hostnames) and Integrações (Asaas keys). Replaces the three separate
 * back-office pages; the old `/admin/loja|enderecos|integracoes` paths redirect here (see `App.tsx`).
 * Runs inside the store's locale (same as `AdminFrame`) so the organ components and the copy speak its language.
 */
import { CommerceLocaleProvider } from "@noctusai/lib";
import { SectionTabsPage, type SectionTab } from "@noctusai/lib/components";
import { Building2, Globe, KeyRound } from "lucide-react";

import { useStoreLocale } from "@/components/AdminFrame";
import { usePageT } from "@/lib/i18n";
import { KeysBody } from "./ApiKeys";
import { HostsBody } from "./StorefrontHosts";
import { StoreProfileBody } from "./StoreProfile";

export default function Configuracoes() {
  const { t } = usePageT();
  const locale = useStoreLocale();
  const sections: SectionTab[] = [
    { key: "loja", label: t("admin.profile_title"), icon: <Building2 className="h-4 w-4" />, render: () => <StoreProfileBody /> },
    { key: "enderecos", label: t("admin.hosts_title"), icon: <Globe className="h-4 w-4" />, render: () => <HostsBody /> },
    { key: "integracoes", label: t("admin.keys_title"), icon: <KeyRound className="h-4 w-4" />, render: () => <KeysBody /> },
  ];
  return (
    <CommerceLocaleProvider locale={locale}>
      <SectionTabsPage basePath="/admin/configuracoes" title={t("admin.settings_title")} description={t("admin.settings_intro")} sections={sections} />
    </CommerceLocaleProvider>
  );
}
