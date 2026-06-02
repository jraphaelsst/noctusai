/**
 * ConnectedAccountSwitcher — stale-selection reconcile tests.
 *
 * Regression guard for the zero-data root cause: a persisted
 * `activeAccountId` (zustand persist → localStorage) that no longer matches
 * any live account would be sent verbatim as `account_id=` by every data
 * hook, silently filtering ALL channel data to a dead account. The wrapper
 * must reconcile the STORE (not just the display) once accounts load.
 *
 * Mock strategy mirrors Conexoes.test.tsx: real zustand store
 * (setState/getState), data hooks vi.fn()'d, the pure <AccountSwitcher>
 * stubbed (we assert the wrapper's effect, not the child's UI — and the stub
 * sidesteps the @noctusai/lib dual-React render pipeline).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const mockIntegrationAccounts = vi.fn();
vi.mock("@/hooks/useIntegrationAccounts", () => ({
  useIntegrationAccounts: mockIntegrationAccounts,
}));

const mockClients = vi.fn();
vi.mock("@/hooks/useClients", () => ({
  useClients: mockClients,
}));

vi.mock("@/components/AccountSwitcher", () => ({
  AccountSwitcher: () => null,
}));

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
  const { useActiveAccountStore } = await import("@/state/useActiveAccount");
  useActiveAccountStore.setState({ activeAccountId: null, activeClientId: null });
});

function acct(id: string) {
  return {
    id,
    org_id: "org-1",
    provider: "youtube",
    account_label: id,
    client_id: null,
    status: "validated",
    channel_info: {},
    metadata: {},
    is_default: true,
    last_synced_at: null,
    created_at: "",
    updated_at: "",
  };
}

describe("ConnectedAccountSwitcher stale-selection reconcile", () => {
  beforeEach(() => {
    mockClients.mockReturnValue({ data: [] });
  });

  it("clears a stale persisted activeAccountId absent from the live accounts", async () => {
    const { useActiveAccountStore } = await import("@/state/useActiveAccount");
    useActiveAccountStore.setState({ activeAccountId: "dead-account", activeClientId: null });
    mockIntegrationAccounts.mockReturnValue({ data: [acct("c15341f9")] });

    const { render } = await import("@testing-library/react");
    const { ConnectedAccountSwitcher } = await import("@/components/ConnectedAccountSwitcher");
    render(<ConnectedAccountSwitcher />);

    await vi.waitFor(() => {
      expect(useActiveAccountStore.getState().activeAccountId).toBeNull();
    });
  });

  it("keeps a valid persisted activeAccountId that matches a live account", async () => {
    const { useActiveAccountStore } = await import("@/state/useActiveAccount");
    useActiveAccountStore.setState({ activeAccountId: "c15341f9", activeClientId: null });
    mockIntegrationAccounts.mockReturnValue({ data: [acct("c15341f9")] });

    const { render } = await import("@testing-library/react");
    const { ConnectedAccountSwitcher } = await import("@/components/ConnectedAccountSwitcher");
    render(<ConnectedAccountSwitcher />);

    await new Promise((r) => setTimeout(r, 0));
    expect(useActiveAccountStore.getState().activeAccountId).toBe("c15341f9");
  });

  it("does not clear while accounts are still loading (data undefined)", async () => {
    const { useActiveAccountStore } = await import("@/state/useActiveAccount");
    useActiveAccountStore.setState({ activeAccountId: "pending-id", activeClientId: null });
    mockIntegrationAccounts.mockReturnValue({ data: undefined });

    const { render } = await import("@testing-library/react");
    const { ConnectedAccountSwitcher } = await import("@/components/ConnectedAccountSwitcher");
    render(<ConnectedAccountSwitcher />);

    await new Promise((r) => setTimeout(r, 0));
    expect(useActiveAccountStore.getState().activeAccountId).toBe("pending-id");
  });
});
