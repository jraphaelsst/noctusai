/**
 * Top-level Layout consumed by `createProductApp`. Core has no global chrome: pages manage their own,
 * and the admin surface wraps itself (`admin/AdminApp`, code-split, mounted by `pages/CatchAll`).
 *
 * There is deliberately NO admin gate and no admin path in here: the admin routes are not registered
 * for anyone but a server-confirmed platform admin (or `marketing`, website only), so a visitor who is
 * not one gets the same NotFound as any unknown path. The access rule lives in `admin/access.ts`.
 */
import { useAuth } from '../../lib/auth-context';
import { isAuthenticated, refreshCoreSession } from '../../lib/api';
import { InactivityWarning } from '@noctusai/lib/design-system/InactivityWarning';
import { endSessionLocally } from '@noctusai/lib/auth';

export function CoreLayout({ children }: { children: React.ReactNode }) {
  const { endLocally } = useAuth();

  const onExtend = refreshCoreSession;

  // Inactivity is an ending the user did not ask for: LOCAL only, never a server
  // logout. 2026-10-23 this called the global logout; 2026-10-24 its scope=local
  // successor still revoked server-side the session every core tab shares, and an
  // idle core tab signed the user out. The timer is shared across core tabs
  // (InactivityWarning), so it fires only when every core tab is idle.
  const onExpired = () => {
    endSessionLocally({ clearLocal: endLocally, redirectTo: '/login' });
  };

  return (
    <>
      {children}
      {isAuthenticated() && <InactivityWarning onExtend={onExtend} onExpired={onExpired} />}
    </>
  );
}
