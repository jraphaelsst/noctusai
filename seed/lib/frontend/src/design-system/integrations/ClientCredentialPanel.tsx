/**
 * `<ClientCredentialPanel/>` — per-client credential CRUD panel for a single
 * integration provider.
 *
 * Driven by an array of `IntegrationAccount` (all belonging to one provider)
 * and a `Client[]` list for the selector. The panel lets the user:
 *   - Switch the active client filter (All / specific client).
 *   - View, add, edit, set-default, sync, and delete credentials per client.
 *
 * All data-fetching and mutations live in the consuming product; the panel
 * is a purely presentational + interaction shell (same contract as
 * `IntegrationCard`).
 *
 * States rendered:
 *   - loading:           skeleton shimmer (accounts or clients loading)
 *   - error:             inline destructive callout
 *   - empty (no clients): prompt to add accounts directly (global scope)
 *   - empty (client):    per-client empty state with "Add account" CTA
 *   - success:           client tabs + IntegrationCard per account
 *
 * Props:
 *   accounts        All IntegrationAccount rows for this provider (unfiltered).
 *   clients         Client[] for the org; used to build the tab selector.
 *   provider        Provider id string (e.g. "youtube").
 *   isLoading       True while accounts or clients are being fetched.
 *   error           Surfaced when fetch fails.
 *   busy            Account id that is currently mutating (disables its card).
 *   onAdd           Called when user triggers "Add account" (client_id | null).
 *   onSave          Called with (account, patch) when inline-edit is saved.
 *   onDelete        Called with (account) when user confirms delete.
 *   onSetDefault    Called with (account) to set as default.
 *   onSync          Called with (account) to trigger sync/re-validate.
 *   onOpenModal     Called with (account) to open the detail modal.
 *
 * The organ MUST NOT import from any `products/` path.
 */
import * as React from "react";
import { Plus, AlertCircle, Loader2, Users, Layers } from "lucide-react";

import { cn } from "../../utils";
import { Button } from "../ui/Button";
import { IntegrationCard } from "./IntegrationCard";
import type {
  IntegrationAccount,
  IntegrationAccountPatch,
} from "./types";
import type { ProviderCardConfig } from "./providerCardConfig";
import { getProviderConfig } from "./providerCardConfig";

// ── Client type (minimal, provider-agnostic) ──────────────────────────────────

/** A client row as returned by GET /api/clients. */
export interface ClientRef {
  id: string;
  name: string;
  slug: string;
}

// ── Tab selector ──────────────────────────────────────────────────────────────

const ALL_TAB = "__all__" as const;
type TabId = typeof ALL_TAB | string;

interface TabSelectorProps {
  clients: ClientRef[];
  active: TabId;
  onChange: (id: TabId) => void;
  accountCountPerClient: Map<string, number>;
  totalCount: number;
}

function TabSelector({
  clients,
  active,
  onChange,
  accountCountPerClient,
  totalCount,
}: TabSelectorProps) {
  return (
    <div
      role="tablist"
      aria-label="Filtrar por cliente"
      className="flex flex-wrap gap-1 pb-3"
    >
      <button
        role="tab"
        aria-selected={active === ALL_TAB}
        type="button"
        onClick={() => onChange(ALL_TAB)}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-sm font-medium transition-colors",
          active === ALL_TAB
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-muted-foreground hover:bg-accent hover:text-foreground",
        )}
      >
        <Layers className="h-3.5 w-3.5" aria-hidden="true" />
        Todos
        {totalCount > 0 && (
          <span className="ml-0.5 rounded-full px-1 text-[10px] font-bold leading-4 opacity-70">
            {totalCount}
          </span>
        )}
      </button>

      {clients.map((c) => {
        const count = accountCountPerClient.get(c.id) ?? 0;
        return (
          <button
            key={c.id}
            role="tab"
            aria-selected={active === c.id}
            type="button"
            onClick={() => onChange(c.id)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-sm font-medium transition-colors",
              active === c.id
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:bg-accent hover:text-foreground",
            )}
          >
            {c.name}
            {count > 0 && (
              <span className="ml-0.5 rounded-full px-1 text-[10px] font-bold leading-4 opacity-70">
                {count}
              </span>
            )}
          </button>
        );
      })}

      {/* "Sem cliente" tab for unassigned accounts */}
      <button
        role="tab"
        aria-selected={active === ""}
        type="button"
        onClick={() => onChange("")}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-sm font-medium transition-colors",
          active === ""
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-muted-foreground hover:bg-accent hover:text-foreground",
        )}
      >
        <Users className="h-3.5 w-3.5" aria-hidden="true" />
        Sem cliente
      </button>
    </div>
  );
}

// ── Account grid ──────────────────────────────────────────────────────────────

interface AccountGridProps {
  accounts: IntegrationAccount[];
  config: ProviderCardConfig | undefined;
  busyAccountId: string | null;
  onSave?: (account: IntegrationAccount, patch: IntegrationAccountPatch) => void;
  onDelete?: (account: IntegrationAccount) => void;
  onSetDefault?: (account: IntegrationAccount) => void;
  onSync?: (account: IntegrationAccount) => void;
  onOpenModal?: (account: IntegrationAccount) => void;
}

function AccountGrid({
  accounts,
  config,
  busyAccountId,
  onSave,
  onDelete,
  onSetDefault,
  onSync,
  onOpenModal,
}: AccountGridProps) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {accounts.map((acc) => (
        <IntegrationCard
          key={acc.id}
          account={acc}
          config={config}
          busy={busyAccountId === acc.id}
          onSave={onSave ? (patch) => onSave(acc, patch) : undefined}
          onDelete={onDelete}
          onSetDefault={onSetDefault}
          onSync={onSync}
          onOpenModal={onOpenModal}
        />
      ))}
    </div>
  );
}

// ── ClientCredentialPanel ─────────────────────────────────────────────────────

export interface ClientCredentialPanelProps {
  /** All accounts for this provider (from the consuming product). */
  accounts: IntegrationAccount[];
  /** All org clients (used to build the tab selector). */
  clients: ClientRef[];
  /** Provider id string — used to look up the ProviderCardConfig. */
  provider: string;
  /** Override the ProviderCardConfig (falls back to registry lookup). */
  config?: ProviderCardConfig;
  /** True while accounts or clients are loading. */
  isLoading?: boolean;
  /** Error to surface if fetch fails. */
  error?: Error | null;
  /**
   * The account id currently mutating (disables that card's controls).
   * null when no mutation is in-flight.
   */
  busyAccountId?: string | null;
  /**
   * Called when the user clicks "Add account".
   * Receives the currently selected client_id (null for "Sem cliente" tab,
   * undefined for "All" tab which also resolves to null server-side).
   */
  onAdd?: (clientId: string | null) => void;
  /** Called with (account, patch) when inline-edit is saved. */
  onSave?: (account: IntegrationAccount, patch: IntegrationAccountPatch) => void;
  /** Called when the user triggers delete. */
  onDelete?: (account: IntegrationAccount) => void;
  /** Called when the user triggers set-default. */
  onSetDefault?: (account: IntegrationAccount) => void;
  /** Called when the user triggers sync/re-validate. */
  onSync?: (account: IntegrationAccount) => void;
  /** Called when the user opens the detail modal. */
  onOpenModal?: (account: IntegrationAccount) => void;
  /** Optional extra className on the wrapper. */
  className?: string;
}

export function ClientCredentialPanel({
  accounts,
  clients,
  provider,
  config: configProp,
  isLoading = false,
  error = null,
  busyAccountId = null,
  onAdd,
  onSave,
  onDelete,
  onSetDefault,
  onSync,
  onOpenModal,
  className,
}: ClientCredentialPanelProps) {
  const [activeTab, setActiveTab] = React.useState<TabId>(ALL_TAB);

  const config = configProp ?? getProviderConfig(provider);

  // Count accounts per client for the tab badges.
  const accountCountPerClient = React.useMemo(() => {
    const map = new Map<string, number>();
    for (const acc of accounts) {
      if (acc.client_id) {
        map.set(acc.client_id, (map.get(acc.client_id) ?? 0) + 1);
      }
    }
    return map;
  }, [accounts]);

  // Filter accounts based on the active tab.
  const visibleAccounts = React.useMemo(() => {
    if (activeTab === ALL_TAB) return accounts;
    if (activeTab === "") return accounts.filter((a) => !a.client_id);
    return accounts.filter((a) => a.client_id === activeTab);
  }, [accounts, activeTab]);

  // The client_id to pass to onAdd when the user clicks "Add account".
  const addClientId: string | null =
    activeTab === ALL_TAB ? null : activeTab === "" ? null : activeTab;

  // ── Loading ──────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div
        className={cn("space-y-3", className)}
        aria-busy="true"
        aria-label="Carregando credenciais"
      >
        {/* Skeleton tabs */}
        <div className="flex gap-2 pb-3">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-7 w-20 animate-pulse rounded-md bg-muted"
            />
          ))}
        </div>
        {/* Skeleton cards */}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2].map((i) => (
            <div
              key={i}
              className="rounded-lg border border-border bg-card p-4"
              aria-hidden="true"
            >
              <div className="flex items-start gap-3">
                <div className="h-9 w-9 animate-pulse rounded-full bg-muted" />
                <div className="flex-1 space-y-1.5">
                  <div className="h-4 w-32 animate-pulse rounded bg-muted" />
                  <div className="h-3 w-20 animate-pulse rounded bg-muted" />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ── Error ────────────────────────────────────────────────────────────────
  if (error) {
    return (
      <div
        role="alert"
        className={cn(
          "inline-flex items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive",
          className,
        )}
      >
        <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span>
          {error.message || "Não foi possível carregar as credenciais."}
        </span>
      </div>
    );
  }

  // ── Success ──────────────────────────────────────────────────────────────
  const showTabs = clients.length > 0;
  const displayName = config?.displayName ?? provider;

  return (
    <div className={cn("space-y-2", className)}>
      {/* Client tabs (only when org has clients) */}
      {showTabs && (
        <TabSelector
          clients={clients}
          active={activeTab}
          onChange={setActiveTab}
          accountCountPerClient={accountCountPerClient}
          totalCount={accounts.length}
        />
      )}

      {/* Add account button + count header */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {visibleAccounts.length > 0
            ? `${visibleAccounts.length} conta${visibleAccounts.length !== 1 ? "s" : ""} — ${displayName}`
            : `Sem contas ${displayName} ${
                activeTab !== ALL_TAB && activeTab !== ""
                  ? "para este cliente"
                  : activeTab === "" ? "sem cliente" : ""
              }`}
        </p>
        {onAdd && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => onAdd(addClientId)}
            aria-label={`Adicionar conta ${displayName}`}
          >
            <Plus className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
            Adicionar conta
          </Button>
        )}
      </div>

      {/* Empty state */}
      {visibleAccounts.length === 0 ? (
        <div
          aria-label={`Nenhuma conta ${displayName} encontrada`}
          className="rounded-md border border-dashed bg-muted/20 py-8 text-center text-sm text-muted-foreground"
        >
          {activeTab === ALL_TAB
            ? "Nenhuma conta ainda. Clique em Adicionar conta para comecar."
            : activeTab === ""
            ? "Nenhuma conta sem cliente. Clique em Adicionar conta para criar uma."
            : "Nenhuma conta para este cliente. Clique em Adicionar conta para criar uma."}
        </div>
      ) : (
        <AccountGrid
          accounts={visibleAccounts}
          config={config}
          busyAccountId={busyAccountId}
          onSave={onSave}
          onDelete={onDelete}
          onSetDefault={onSetDefault}
          onSync={onSync}
          onOpenModal={onOpenModal}
        />
      )}
    </div>
  );
}

export default ClientCredentialPanel;
