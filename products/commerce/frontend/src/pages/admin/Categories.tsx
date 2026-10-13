/** `/admin/categorias` — category tree CRUD via the organ's `CategoryManager`. */
import { CategoryManager } from "@noctusai/lib";

import { AdminFrame } from "@/components/AdminFrame";
import { staffCommerce } from "@/lib/commerce";

export default function Categories() {
  return (
    <AdminFrame titleKey="admin.categories_title">
      <CategoryManager hooks={staffCommerce} />
    </AdminFrame>
  );
}
