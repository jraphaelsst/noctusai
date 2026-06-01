/**
 * ConnectedAccountSwitcher — the data-wired wrapper around the pure
 * <AccountSwitcher>. Self-fetches the org's YouTube accounts + clients and
 * feeds them to the switcher, which reads/writes the shared
 * `useActiveAccountStore`. Mount this on any data view (YouTube, Dashboard)
 * to expose live account/client switching that re-points every hook reading
 * `activeAccountId` (useDashboardStats / useTopVideos / useRecentUploads /
 * useVideos) — the "few-clicks data switching" requirement.
 *
 * Renders nothing until there is at least one connected account (no point
 * showing an empty switcher on a freshly-connected org).
 *
 * The pure <AccountSwitcher> stays props-driven (unit-tested in isolation);
 * this wrapper owns the data-fetching so pages mount it as a one-liner.
 */
import { useIntegrationAccounts } from "@/hooks/useIntegrationAccounts";
import { useClients } from "@/hooks/useClients";
import { AccountSwitcher } from "@/components/AccountSwitcher";

interface ConnectedAccountSwitcherProps {
  className?: string;
}

export function ConnectedAccountSwitcher({ className }: ConnectedAccountSwitcherProps) {
  const { data: accounts } = useIntegrationAccounts({ provider: "youtube" });
  const { data: clients } = useClients();

  // Don't render an empty switcher — only show it once an account exists.
  if (!accounts || accounts.length === 0) return null;

  return (
    <AccountSwitcher
      accounts={accounts}
      clients={clients ?? []}
      providerLabel="YouTube"
      className={className}
    />
  );
}

export default ConnectedAccountSwitcher;
