import { useMemo } from 'react';
import { Zap } from 'lucide-react';
import { CoreHeader } from './CoreHeader';
import { AppShell, Sidebar } from '@noctusai/lib/design-system';
import { ADMIN_NAV_GROUPS, ADMIN_STANDALONE_ITEMS } from '../../admin/navConfig';
import { pruneNavGroups, pruneNavItems, type AdminRole } from '../../admin/access';

/**
 * Admin shell (sidebar + header). Renders the seed `Sidebar` organ with core's module-group config,
 * pruned by `canReach(role, href)` -- the SAME predicate that registers the routes. Only ever
 * imported from the code-split admin chunk.
 */
export function Layout({ children, role }: { children?: React.ReactNode; role: AdminRole }) {
  const navGroups = useMemo(() => pruneNavGroups(ADMIN_NAV_GROUPS, role), [role]);
  const standaloneItems = useMemo(() => pruneNavItems(ADMIN_STANDALONE_ITEMS, role), [role]);

  return (
    <AppShell
      navGroups={navGroups}
      standaloneItems={standaloneItems}
      sidebar={
        <Sidebar
          brandIcon={Zap}
          brandTitle="NoctusAI"
          brandSubtitle={role === 'admin' ? 'Admin' : 'Marketing'}
          brandHref="/"
          storageKey="core"
          navGroups={navGroups}
          standaloneItems={standaloneItems}
        />
      }
      header={({ onMenuToggle }) => (
        <CoreHeader onMenuToggle={onMenuToggle} profileEditable />
      )}
    >
      <div className="p-4 sm:p-6 lg:p-8">{children}</div>
    </AppShell>
  );
}
