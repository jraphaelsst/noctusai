/**
 * `<SocialDashboardShell/>` — the shared spine for a social-account
 * dashboard page. Extracted from `pages/YouTube.tsx` + `pages/MetaDashboard.tsx`
 * in `products/social-wiring` (N=2 at extraction time; the upcoming WhatsApp
 * page is the N=3 that formalizes the recurrence rule).
 *
 * Every one of these pages shares the same spine:
 *   - `container max-w-7xl` header: title + subtitle, an account-switcher
 *     slot on the right, and (for multi-network pages) a segmented network
 *     toggle.
 *   - config-driven Radix `<Tabs>` subtabs, one `TabsTrigger`+`TabsContent`
 *     pair per entry in `subtabs`.
 *
 * Subtab selection is internal, uncontrolled state (`defaultSubtab`, falling
 * back to the first entry) — the shell also self-heals when the active key
 * drops out of the current `subtabs` set (e.g. MetaDashboard's Facebook
 * network has no "dms" subtab): it resets to `defaultSubtab` / the first
 * remaining subtab rather than rendering a dead tab. This absorbed a
 * `useEffect` that both YouTube's and MetaDashboard's page files used to
 * hand-roll.
 *
 * Network selection (`activeNetwork` / `onNetworkChange`), by contrast, is
 * held by the CALLER — the caller typically recomputes its `subtabs` array
 * from the active network (see `MetaDashboard.tsx`), so the shell can't own
 * that state itself.
 *
 * `accountSwitcher` is a slot, not a shell-rendered component: the shell
 * lives in `@noctusai/lib` and must stay decoupled from any product's data
 * layer, but the account/client switcher (`ConnectedAccountSwitcher` in
 * social-wiring) is product-local — it reads org-scoped integration-account
 * hooks + a product-local Zustand store. Pass the already-wired element:
 *
 *   <SocialDashboardShell
 *     accountSwitcher={<ConnectedAccountSwitcher provider="meta" providerLabel="Meta" />}
 *     ...
 *   />
 */
import { useEffect, useState, type ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "../ui/tabs";
import { Button } from "../ui/Button";

export interface SocialDashboardNetwork {
  /** Stable key, e.g. "instagram" / "facebook". */
  key: string;
  /** Toggle button label. */
  label: string;
  icon: LucideIcon;
}

export interface SocialDashboardSubtab {
  /** Stable key, matches the Radix Tabs `value`. */
  key: string;
  label: string;
  icon: LucideIcon;
  /**
   * Invoked once per render while this subtab's `TabsContent` is mounted.
   * Wrap the returned node in your own `<Suspense>` for a code-split panel
   * (same pattern as `pages/Upload.tsx`) — the shell has no opinion on lazy
   * loading, it just calls `render()`.
   */
  render: () => ReactNode;
}

export interface SocialDashboardShellProps {
  title: string;
  subtitle?: string;
  /**
   * Rendered top-right of the header — typically a product-local, data-wired
   * account/client switcher. Omit for a page with no switcher yet.
   */
  accountSwitcher?: ReactNode;
  /**
   * Segmented network toggle (Instagram|Facebook-style). Omit for a
   * single-network page (e.g. YouTube) — no toggle renders.
   */
  networks?: SocialDashboardNetwork[];
  /** Required together with `onNetworkChange` when `networks` is set. */
  activeNetwork?: string;
  onNetworkChange?: (key: string) => void;
  /** Config-driven subtabs — at least one entry. */
  subtabs: SocialDashboardSubtab[];
  /** Uncontrolled default subtab key; falls back to `subtabs[0]`. */
  defaultSubtab?: string;
  /** Extra header content, rendered after `accountSwitcher`. */
  headerExtra?: ReactNode;
}

export function SocialDashboardShell({
  title,
  subtitle,
  accountSwitcher,
  networks,
  activeNetwork,
  onNetworkChange,
  subtabs,
  defaultSubtab,
  headerExtra,
}: SocialDashboardShellProps) {
  // `defaultSubtab` only wins while it's actually present in the CURRENT
  // `subtabs` set — otherwise a stale default (e.g. "dms" after switching to
  // a network whose subtabs don't include it) would loop back onto a dead
  // key instead of healing.
  const fallbackSubtab = () =>
    (defaultSubtab && subtabs.some((tab) => tab.key === defaultSubtab)
      ? defaultSubtab
      : subtabs[0]?.key) ?? "";
  const [activeSubtab, setActiveSubtab] = useState<string>(fallbackSubtab);

  // Self-heal when the current subtabs set no longer contains the active
  // key — e.g. switching MetaDashboard's network to Facebook drops "dms".
  // Never render a dead tab.
  useEffect(() => {
    if (!subtabs.some((tab) => tab.key === activeSubtab)) {
      setActiveSubtab(fallbackSubtab());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subtabs, activeSubtab, defaultSubtab]);

  return (
    <div className="container max-w-7xl space-y-6 py-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{title}</h1>
          {subtitle ? (
            <p className="text-sm text-muted-foreground">{subtitle}</p>
          ) : null}
        </div>
        {accountSwitcher}
        {headerExtra}
      </div>

      {networks && networks.length > 0 ? (
        <div
          className="inline-flex rounded-md border border-border bg-muted/30 p-1"
          role="group"
          aria-label="Rede social"
          data-testid="social-dashboard-network-toggle"
        >
          {networks.map(({ key, label, icon: Icon }) => (
            <Button
              key={key}
              variant={activeNetwork === key ? "primary" : "ghost"}
              size="sm"
              data-testid={`social-dashboard-network-${key}`}
              onClick={() => onNetworkChange?.(key)}
            >
              <Icon className="mr-2 h-4 w-4" />
              {label}
            </Button>
          ))}
        </div>
      ) : null}

      <Tabs value={activeSubtab} onValueChange={setActiveSubtab}>
        <TabsList className="flex-wrap h-auto gap-0.5">
          {subtabs.map(({ key, label, icon: Icon }) => (
            <TabsTrigger key={key} value={key}>
              <Icon className="mr-2 h-4 w-4" />
              {label}
            </TabsTrigger>
          ))}
        </TabsList>

        {subtabs.map(({ key, render }) => (
          <TabsContent key={key} value={key} className="mt-4">
            {render()}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
