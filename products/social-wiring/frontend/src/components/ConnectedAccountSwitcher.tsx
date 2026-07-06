/**
 * ConnectedAccountSwitcher — the data-wired wrapper around the pure
 * <AccountSwitcher>. Self-fetches the org's accounts + clients for a given
 * `provider` and feeds them to the switcher, which reads/writes the shared
 * `useActiveAccountStore`. Mount this on any data view (YouTube, Meta,
 * Dashboard) to expose live account/client switching that re-points every
 * hook reading `activeAccountId` — the "few-clicks data switching"
 * requirement.
 *
 * `provider` defaults to "youtube" (back-compat with the original
 * single-provider callers); pass `provider="meta"` for the Meta dashboard.
 * The store itself is already provider-agnostic (one `activeAccountId`
 * selection) — a product surfacing 2+ live provider switchers side-by-side
 * simultaneously would need per-provider store slices, out of scope here.
 *
 * Renders nothing until there is at least one connected account (no point
 * showing an empty switcher on a freshly-connected org).
 *
 * The pure <AccountSwitcher> stays props-driven (unit-tested in isolation);
 * this wrapper owns the data-fetching so pages mount it as a one-liner.
 *
 * Stale-selection reconcile: `activeAccountId` is persisted to localStorage
 * (zustand persist). A selection that no longer matches any live account —
 * e.g. an account id from an earlier session that has since been
 * re-created/deleted — would otherwise be sent verbatim as `account_id=` by
 * every data hook (useVideos / useDashboardStats / useChannelTrend / useMeta*),
 * silently filtering ALL channel data to a dead account → zeros everywhere
 * while the switcher innocently shows the default option. The pure
 * <AccountSwitcher> reconciles this for DISPLAY only; here we reconcile the
 * STORE so the hooks fall back to the org default. Runs once accounts load.
 */
import { useEffect } from "react";
import { useIntegrationAccounts } from "@/hooks/useIntegrationAccounts";
import { useClients } from "@/hooks/useClients";
import { AccountSwitcher } from "@/components/AccountSwitcher";
import { useActiveAccountStore } from "@/state/useActiveAccount";

interface ConnectedAccountSwitcherProps {
  className?: string;
  /** Provider to fetch accounts for; defaults to "youtube" for back-compat. */
  provider?: string;
  /** Human-readable label shown in the account dropdown; derived from
   * `provider` when omitted (capitalized). */
  providerLabel?: string;
}

export function ConnectedAccountSwitcher({
  className,
  provider = "youtube",
  providerLabel,
}: ConnectedAccountSwitcherProps) {
  const { data: accounts } = useIntegrationAccounts({ provider });
  const { data: clients } = useClients();
  const activeAccountId = useActiveAccountStore((s) => s.activeAccountId);
  const setActiveAccount = useActiveAccountStore((s) => s.setActiveAccount);

  // Reconcile a stale persisted selection against server truth. Only once
  // accounts have actually loaded (accounts !== undefined) — never clear
  // while the query is still in flight.
  useEffect(() => {
    if (!accounts) return;
    if (activeAccountId && !accounts.some((a) => a.id === activeAccountId)) {
      setActiveAccount(null);
    }
  }, [accounts, activeAccountId, setActiveAccount]);

  // Don't render an empty switcher — only show it once an account exists.
  if (!accounts || accounts.length === 0) return null;

  return (
    <AccountSwitcher
      accounts={accounts}
      clients={clients ?? []}
      providerLabel={
        providerLabel ?? provider.charAt(0).toUpperCase() + provider.slice(1)
      }
      className={className}
    />
  );
}

export default ConnectedAccountSwitcher;
