/** The platform admin bundle (default export, lazy). Owns the platform route table, nav and labels. */
import { AdminApis } from './AdminApis';
import { AdminSurface } from './AdminSurface';
import { ADMIN_NAV_GROUPS, ADMIN_STANDALONE_ITEMS } from './navConfig';
import { ADMIN_ROUTES } from './routes';

export default function PlatformAdminApp() {
  return (
    <AdminSurface role="admin" routes={ADMIN_ROUTES} navGroups={ADMIN_NAV_GROUPS} standaloneItems={ADMIN_STANDALONE_ITEMS} Providers={AdminApis} />
  );
}
