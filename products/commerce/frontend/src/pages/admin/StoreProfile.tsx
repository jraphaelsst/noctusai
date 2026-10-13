/** `/admin/loja` — store profile (CNPJ, tax regime, locale/currency, brand) via the organ's `StoreProfileForm`. */
import { StoreProfileForm } from "@noctusai/lib";

import { AdminFrame } from "@/components/AdminFrame";
import { useIsPlatformAdmin } from "@/hooks/useStorefrontHosts";
import { staffCommerce } from "@/lib/commerce";

export default function StoreProfile() {
  const isPlatformAdmin = useIsPlatformAdmin();
  return (
    <AdminFrame titleKey="admin.profile_title" introKey="admin.profile_intro">
      <StoreProfileForm hooks={staffCommerce} isPlatformAdmin={isPlatformAdmin} />
    </AdminFrame>
  );
}
