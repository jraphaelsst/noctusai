/**
 * Top-level Layout consumed by `createProductApp`. Branches at render time:
 * - Admin paths (`/admin/*`): enforce admin role, wrap in AdminShell (Sidebar+Header+NotificationBell).
 * - Everything else: render children directly (pages already manage their own chrome).
 *
 * Core never had a global layout on non-admin routes — this keeps that
 * behavior unchanged while still letting the framework own routing.
 */
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../lib/auth-context';
import { isAuthenticated, api, getRefreshToken, setToken, setRefreshToken } from '../../lib/api';
import { InactivityWarning } from '@noctusai/lib/design-system/InactivityWarning';
import { Layout as AdminShell } from './Layout';

export function CoreLayout({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const { isAdmin, logout } = useAuth();

  const onExtend = async () => {
    const rt = getRefreshToken();
    if (!rt) return;
    const res = await api.post('/api/auth/refresh', { refresh_token: rt });
    if (res.access_token) setToken(res.access_token);
    if (res.refresh_token) setRefreshToken(res.refresh_token);
  };

  const onExpired = () => {
    logout();
    window.location.href = '/login';
  };

  if (location.pathname.startsWith('/admin')) {
    if (!isAdmin) return <Navigate to="/" replace />;
    return (
      <>
        <AdminShell>{children}</AdminShell>
        {isAuthenticated() && <InactivityWarning onExtend={onExtend} onExpired={onExpired} />}
      </>
    );
  }

  return (
    <>
      {children}
      {isAuthenticated() && <InactivityWarning onExtend={onExtend} onExpired={onExpired} />}
    </>
  );
}
