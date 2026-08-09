/**
 * ConnectedAccountSwitcher — the data-wired wrapper around the pure
 * <AccountSwitcher>. Self-fetches the org's accounts + clients for a given
 * `provider` and feeds them to the switcher, which reads/writes this
 * provider's slot in `useActiveAccountStore`. Mount this on any data view
 * (YouTube, Meta, n8n, Dashboard) to expose live account/client switching
 * that re-points every hook reading that provider's selection — the
 * "few-clicks data switching" requirement.
 *
 * `provider` defaults to "youtube" (back-compat with the original
 * single-provider callers); pass `provider="meta"` for the Meta dashboard.
 * The store keys the selection BY provider, so two switchers for different
 * providers — side-by-side or across a navigation — cannot overwrite each
 * other's choice.
 *
 * Renders nothing until there is at least one connected account (no point
 * showing an empty switcher on a freshly-connected org).
 *
 * The pure <AccountSwitcher> stays props-driven (unit-tested in isolation);
 * this wrapper owns the data-fetching so pages mount it as a one-liner.
 *
 * Stale-selection reconcile: the selection is persisted to localStorage
 * (zustand persist). An id that no longer matches any live account — e.g.
 * from an earlier session, since deleted or re-created — would otherwise be
 * sent verbatim as `account_id=` by every data hook (useVideos /
 * useDashboardStats / useChannelTrend / useMeta*), silently filtering ALL
 * data to a dead account → zeros everywhere while the switcher innocently
 * shows the default option. The pure <AccountSwitcher> reconciles this for
 * DISPLAY only; here we reconcile the STORE so the hooks fall back to the
 * org default. Runs once accounts load.
 *
 * Note what this reconcile can and cannot do. It repairs a DEAD id, and
 * only after the accounts query resolves — the data hooks have already
 * fired by then. It never had to repair a WRONG-PROVIDER id, because the
 * store now keys by provider and this component only ever reads its own
 * slot; that class of bug is gone at the state layer rather than patched
 * here. (Before provider-keying it did have to, and it lost the race —
 * the live n8n 404 on 2026-07-31.)
 */
import { useEffect } from "react";
import { useIntegrationAccounts } from "@/hooks/useIntegrationAccounts";
import { useMarcas } from "@/hooks/useMarcas";
import { AccountSwitcher } from "@/components/AccountSwitcher";
import { useActiveAccountId, useActiveAccountStore } from "@/state/useActiveAccount";

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
  const { data: marcas } = useMarcas();
  const activeAccountId = useActiveAccountId(provider);
  const setActiveAccount = useActiveAccountStore((s) => s.setActiveAccount);

  // Reconcile a stale persisted selection against server truth. Only once
  // accounts have actually loaded (accounts !== undefined) — never clear
  // while the query is still in flight.
  useEffect(() => {
    if (!accounts) return;
    if (activeAccountId && !accounts.some((a) => a.id === activeAccountId)) {
      setActiveAccount(provider, null);
    }
  }, [accounts, activeAccountId, provider, setActiveAccount]);

  // Don't render an empty switcher — only show it once an account exists.
  if (!accounts || accounts.length === 0) return null;

  return (
    <AccountSwitcher
      accounts={accounts}
      marcas={marcas ?? []}
      provider={provider}
      providerLabel={
        providerLabel ?? provider.charAt(0).toUpperCase() + provider.slice(1)
      }
      className={className}
    />
  );
}

export default ConnectedAccountSwitcher;
