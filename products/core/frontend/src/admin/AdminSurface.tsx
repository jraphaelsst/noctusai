/**
 * The generic admin surface (shell + routes + nav). It carries NO route table or labels of its own: the
 * platform bundle and the website bundle each hand it theirs, so a marketing user never receives a
 * platform-admin string. Routes are registered through `canReach` (the same predicate the sidebar is
 * pruned with). A path no registered route claims renders the plain `NotFound`, with no admin chrome.
 */
import { matchPath, useLocation, Route, Routes } from 'react-router-dom';
import { Suspense, type ComponentType, type ReactNode } from 'react';
import { PageSkeleton } from '@noctusai/lib/design-system';
import { ErrorBoundary } from '@noctusai/lib';
import { Layout as AdminShell } from '../components/layout/Layout';
import { NotFound } from '../pages/NotFound';
import type { NavGroup, NavItem } from '@noctusai/lib/design-system';
import { canReach, type AdminRole } from './access';
import type { AdminRoute } from './types';

export interface AdminSurfaceProps {
  role: AdminRole;
  routes: AdminRoute[];
  navGroups: NavGroup[];
  standaloneItems?: NavItem[];
  /** Bundle-owned context providers (e.g. the platform admin API clients) wrapped around the routes. */
  Providers?: ComponentType<{ children: ReactNode }>;
}

export function AdminSurface({ role, routes: allRoutes, navGroups, standaloneItems = [], Providers }: AdminSurfaceProps) {
  const { pathname } = useLocation();
  const routes = allRoutes.filter((r) => canReach(role, r.path));
  const Wrap = Providers ?? (({ children }: { children: ReactNode }) => <>{children}</>);
  if (!routes.some((r) => matchPath({ path: r.path, end: true }, pathname))) return <NotFound />;
  return (
    <>
      <AdminShell role={role} navGroups={navGroups} standaloneItems={standaloneItems}>
        <Wrap>
        <ErrorBoundary>
          <Suspense fallback={<PageSkeleton />}>
            <Routes>
              {routes.map(({ path, component: Component }) => (
                <Route key={path} path={path} element={<Component />} />
              ))}
            </Routes>
          </Suspense>
        </ErrorBoundary>
        </Wrap>
      </AdminShell>
    </>
  );
}
