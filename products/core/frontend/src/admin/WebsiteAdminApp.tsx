/** The website-admin bundle for the `marketing` role (default export, lazy): website routes and nav only. */
import { AdminSurface } from './AdminSurface';
import { WEBSITE_NAV_GROUPS, WEBSITE_ROUTES } from './websiteConfig';

export default function WebsiteAdminApp() {
  return <AdminSurface role="marketing" routes={WEBSITE_ROUTES} navGroups={WEBSITE_NAV_GROUPS} />;
}
