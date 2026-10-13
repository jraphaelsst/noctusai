/** `/admin/cupons` — coupon CRUD via the organ's `CouponsEditor` (currency from the store profile). */
import { CouponsEditor } from "@noctusai/lib";

import { AdminFrame } from "@/components/AdminFrame";
import { staffCommerce } from "@/lib/commerce";

export default function Coupons() {
  const profile = staffCommerce.useProfile();
  return (
    <AdminFrame titleKey="admin.coupons_title">
      <CouponsEditor hooks={staffCommerce} currency={profile.data?.currency ?? "BRL"} />
    </AdminFrame>
  );
}
