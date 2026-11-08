/**
 * Fallback for every path no regular route claims.
 *
 * A server-confirmed platform admin gets the code-split platform bundle, the marketing role the website-only
 * bundle; each matches the path against ITS OWN route table. Anyone else gets the plain `NotFound` — byte-identical
 * to a path that never existed. Nothing here names an admin path, label or page: those live only in
 * the admin chunk, which a non-admin never downloads.
 */
import { Suspense, lazy } from 'react';
import { PageSkeleton } from '@noctusai/lib/design-system';
import { useAuth } from '../lib/auth-context';
import { ServiceUnavailable } from '../components/ServiceUnavailable';
import { NotFound } from './NotFound';

// Two privileged bundles, chosen by the server-confirmed role: marketing is never delivered the platform one.
const PlatformAdminApp = lazy(() => import('../admin/PlatformAdminApp'));
const WebsiteAdminApp = lazy(() => import('../admin/WebsiteAdminApp'));

export default function CatchAll() {
  const { isAdmin, isMarketing, loading, unavailable, refresh } = useAuth();
  if (loading) return <PageSkeleton />;
  if (unavailable) return <ServiceUnavailable onRetry={refresh} />;
  if (!isAdmin && !isMarketing) return <NotFound />;
  return (
    <Suspense fallback={<PageSkeleton />}>
      {isAdmin ? <PlatformAdminApp /> : <WebsiteAdminApp />}
    </Suspense>
  );
}
