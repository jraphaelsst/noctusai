/**
 * AccountSwitcher — compact client + account selection bar.
 *
 * Shows:
 *   [Client dropdown] → [Account dropdown (filtered by client)] → current status badge
 *
 * Reads/writes the `useActiveAccountStore` so changes propagate to
 * Dashboard, Videos, and any other hook reading this provider's selection.
 *
 * The selection is per-provider (see `state/useActiveAccount.ts`), so this
 * component needs the provider SLUG — not just the display label — to read
 * and write the right slot. Picking a YouTube account must not re-point the
 * n8n page.
 *
 * Props:
 *   - accounts: all integration accounts for the provider (pre-fetched by parent)
 *   - clients: all clients (pre-fetched by parent)
 *   - provider: provider slug the selection is keyed under (e.g. "youtube")
 *   - providerLabel: human-readable name shown in the account dropdown
 *
 * Status badge uses `resolveStatusBadge` from @noctusai/lib for consistency.
 */
import { useMemo } from "react";
import { Users, Youtube, ChevronDown } from "lucide-react";
import { resolveStatusBadge } from "@noctusai/lib";

import type { IntegrationAccount } from "@/hooks/useIntegrationAccounts";
import type { Marca } from "@/hooks/useMarcas";
import { useActiveAccountId, useActiveAccountStore } from "@/state/useActiveAccount";

interface AccountSwitcherProps {
  accounts: IntegrationAccount[];
  marcas: Marca[];
  /** Provider slug the selection is keyed under (e.g. "youtube", "n8n"). */
  provider?: string;
  /** Human-readable provider name used only for "All accounts" label. */
  providerLabel?: string;
  className?: string;
}

export function AccountSwitcher({
  accounts,
  marcas,
  provider = "youtube",
  providerLabel = "YouTube",
  className = "",
}: AccountSwitcherProps) {
  const activeMarcaId = useActiveAccountStore((s) => s.activeMarcaId);
  const setActiveMarca = useActiveAccountStore((s) => s.setActiveMarca);
  const setActiveAccount = useActiveAccountStore((s) => s.setActiveAccount);
  const activeAccountId = useActiveAccountId(provider);

  // Accounts visible in the account dropdown: filtered by the active client
  const filteredAccounts = useMemo(() => {
    if (!activeMarcaId) return accounts;
    return accounts.filter((a) => a.marca_id === activeMarcaId);
  }, [accounts, activeMarcaId]);

  // When the selected account is no longer in filtered list, we treat it as cleared.
  const resolvedAccountId = filteredAccounts.some((a) => a.id === activeAccountId)
    ? activeAccountId
    : null;

  const activeAccount = accounts.find((a) => a.id === resolvedAccountId) ?? null;

  // Derive status badge for the active account
  const badge = activeAccount ? resolveStatusBadge(activeAccount.status) : null;

  return (
    <div
      className={`flex flex-wrap items-center gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2 ${className}`}
      role="group"
      aria-label="Seletor de conta ativa"
    >
      {/* Client selector */}
      {marcas.length > 0 && (
        <div className="flex items-center gap-1.5">
          <Users className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <label htmlFor="sw-client-select" className="text-xs text-muted-foreground sr-only">
            Cliente
          </label>
          <div className="relative">
            <select
              id="sw-client-select"
              value={activeMarcaId ?? ""}
              onChange={(e) => setActiveMarca(e.target.value || null)}
              className="h-7 appearance-none rounded-md border border-input bg-background pr-7 pl-2.5 text-xs ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              aria-label="Selecionar marca"
            >
              <option value="">Todos os marcas</option>
              {marcas.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <ChevronDown
              className="pointer-events-none absolute right-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
          </div>
        </div>
      )}

      {/* Separator */}
      {marcas.length > 0 && <span className="text-muted-foreground/40" aria-hidden="true">/</span>}

      {/* Account selector */}
      <div className="flex items-center gap-1.5">
        <Youtube className="h-3.5 w-3.5 shrink-0 text-red-500" aria-hidden="true" />
        <label htmlFor="sw-account-select" className="text-xs text-muted-foreground sr-only">
          Conta {providerLabel}
        </label>
        <div className="relative">
          <select
            id="sw-account-select"
            value={resolvedAccountId ?? ""}
            onChange={(e) => setActiveAccount(provider, e.target.value || null)}
            className="h-7 appearance-none rounded-md border border-input bg-background pr-7 pl-2.5 text-xs ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            aria-label={`Selecionar conta ${providerLabel}`}
            disabled={filteredAccounts.length === 0}
          >
            <option value="">
              {filteredAccounts.length === 0
                ? `Sem contas ${providerLabel}`
                : `Conta padrão ${providerLabel}`}
            </option>
            {filteredAccounts.map((a) => (
              <option key={a.id} value={a.id}>
                {(a.channel_info?.["title"] as string | undefined) || a.account_label}
                {a.is_default ? " (padrão)" : ""}
              </option>
            ))}
          </select>
          <ChevronDown
            className="pointer-events-none absolute right-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
        </div>
      </div>

      {/* Status badge for active account */}
      {badge && activeAccount && (
        <span
          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${badge.className}`}
          aria-label={`Status: ${badge.label}`}
        >
          {badge.label}
        </span>
      )}
    </div>
  );
}

export default AccountSwitcher;
