/**
 * The platform admin surface, loaded lazily by `CatchAll` only for a server-confirmed role.
 *
 * Routes are registered per role through `canReach` (the same predicate the sidebar is pruned with),
 * so a marketing user has exactly the website routes and no others. A path no registered route claims
 * renders the plain `NotFound`, with no admin chrome.
 */
import { matchPath, useLocation, Route, Routes } from 'react-router-dom';
import { Suspense } from 'react';
import { PageSkeleton } from '@noctusai/lib/design-system';
import { ErrorBoundary } from '@noctusai/lib';
import { Layout as AdminShell } from '../components/layout/Layout';
import { NotFound } from '../pages/NotFound';
import { canReach, type AdminRole } from './access';
import { ADMIN_ROUTES } from './routes';

export default function AdminApp({ role }: { role: AdminRole }) {
  const { pathname } = useLocation();
  const routes = ADMIN_ROUTES.filter((r) => canReach(role, r.path));
  if (!routes.some((r) => matchPath({ path: r.path, end: true }, pathname))) return <NotFound />;
  return (
    <>
      <AdminShell role={role}>
        <ErrorBoundary>
          <Suspense fallback={<PageSkeleton />}>
            <Routes>
              {routes.map(({ path, component: Component }) => (
                <Route key={path} path={path} element={<Component />} />
              ))}
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </AdminShell>
    </>
  );
}
