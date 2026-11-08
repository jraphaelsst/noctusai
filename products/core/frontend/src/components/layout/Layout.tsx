import { useMemo } from 'react';
import type { NavGroup, NavItem } from '@noctusai/lib/design-system';
import { Zap } from 'lucide-react';
import { CoreHeader } from './CoreHeader';
import { AppShell, Sidebar } from '@noctusai/lib/design-system';
import { pruneNavGroups, pruneNavItems, type AdminRole } from '../../admin/access';

/**
 * Admin shell (sidebar + header). Renders the seed `Sidebar` organ with the module-group config its bundle hands it,
 * pruned by `canReach(role, href)` -- the SAME predicate that registers the routes. Only ever
 * imported from the code-split admin chunk.
 */
export function Layout({
  children,
  role,
  navGroups: allGroups,
  standaloneItems: allStandalone = [],
}: {
  children?: React.ReactNode;
  role: AdminRole;
  navGroups: NavGroup[];
  standaloneItems?: NavItem[];
}) {
  const navGroups = useMemo(() => pruneNavGroups(allGroups, role), [allGroups, role]);
  const standaloneItems = useMemo(() => pruneNavItems(allStandalone, role), [allStandalone, role]);

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
