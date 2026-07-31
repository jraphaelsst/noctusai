/**
 * ConnectedAccountSwitcher — stale-selection reconcile + provider-scoping tests.
 *
 * Regression guard for the zero-data root cause: a persisted selection
 * (zustand persist → localStorage) that no longer matches any live account
 * would be sent verbatim as `account_id=` by every data hook, silently
 * filtering ALL channel data to a dead account. The wrapper must reconcile
 * the STORE (not just the display) once accounts load.
 *
 * Also guards the SECOND failure mode this component could not fix on its
 * own: a selection belonging to a DIFFERENT provider. The reconcile effect
 * only runs after the accounts query resolves, by which point the data
 * hooks have already fired the bad request — the live n8n 404 on
 * 2026-07-31. That one is closed at the state layer (the store keys the
 * selection by provider), so the tests below assert the switcher reads and
 * writes only its OWN provider's slot and leaves its neighbours untouched.
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
  useActiveAccountStore.setState({ activeAccountIdByProvider: {}, activeClientId: null });
});

function acct(id: string, provider = "youtube") {
  return {
    id,
    org_id: "org-1",
    provider,
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

  it("defaults to provider='youtube' for back-compat callers", async () => {
    mockIntegrationAccounts.mockReturnValue({ data: [] });
    const { render } = await import("@testing-library/react");
    const { ConnectedAccountSwitcher } = await import("@/components/ConnectedAccountSwitcher");
    render(<ConnectedAccountSwitcher />);
    expect(mockIntegrationAccounts).toHaveBeenCalledWith({ provider: "youtube" });
  });

  it("threads a custom provider (e.g. 'meta') through to useIntegrationAccounts", async () => {
    mockIntegrationAccounts.mockReturnValue({ data: [] });
    const { render } = await import("@testing-library/react");
    const { ConnectedAccountSwitcher } = await import("@/components/ConnectedAccountSwitcher");
    render(<ConnectedAccountSwitcher provider="meta" />);
    expect(mockIntegrationAccounts).toHaveBeenCalledWith({ provider: "meta" });
  });

  it("clears a stale persisted selection absent from the live accounts", async () => {
    const { useActiveAccountStore } = await import("@/state/useActiveAccount");
    useActiveAccountStore.setState({
      activeAccountIdByProvider: { youtube: "dead-account" },
      activeClientId: null,
    });
    mockIntegrationAccounts.mockReturnValue({ data: [acct("c15341f9")] });

    const { render } = await import("@testing-library/react");
    const { ConnectedAccountSwitcher } = await import("@/components/ConnectedAccountSwitcher");
    render(<ConnectedAccountSwitcher />);

    await vi.waitFor(() => {
      expect(
        useActiveAccountStore.getState().activeAccountIdByProvider["youtube"],
      ).toBeNull();
    });
  });

  it("keeps a valid persisted selection that matches a live account", async () => {
    const { useActiveAccountStore } = await import("@/state/useActiveAccount");
    useActiveAccountStore.setState({
      activeAccountIdByProvider: { youtube: "c15341f9" },
      activeClientId: null,
    });
    mockIntegrationAccounts.mockReturnValue({ data: [acct("c15341f9")] });

    const { render } = await import("@testing-library/react");
    const { ConnectedAccountSwitcher } = await import("@/components/ConnectedAccountSwitcher");
    render(<ConnectedAccountSwitcher />);

    await new Promise((r) => setTimeout(r, 0));
    expect(useActiveAccountStore.getState().activeAccountIdByProvider["youtube"]).toBe(
      "c15341f9",
    );
  });

  it("does not clear while accounts are still loading (data undefined)", async () => {
    const { useActiveAccountStore } = await import("@/state/useActiveAccount");
    useActiveAccountStore.setState({
      activeAccountIdByProvider: { youtube: "pending-id" },
      activeClientId: null,
    });
    mockIntegrationAccounts.mockReturnValue({ data: undefined });

    const { render } = await import("@testing-library/react");
    const { ConnectedAccountSwitcher } = await import("@/components/ConnectedAccountSwitcher");
    render(<ConnectedAccountSwitcher />);

    await new Promise((r) => setTimeout(r, 0));
    expect(useActiveAccountStore.getState().activeAccountIdByProvider["youtube"]).toBe(
      "pending-id",
    );
  });

  // ─── Provider scoping — the live n8n 404 of 2026-07-31 ──────────────────
  //
  // Before the selection was keyed by provider these two behaviours were
  // impossible: one global id meant the n8n switcher's reconcile judged the
  // Meta selection against the n8n account list and cleared it, and any
  // switcher's write clobbered every other page's choice.

  it("leaves another provider's selection alone when reconciling its own", async () => {
    const { useActiveAccountStore } = await import("@/state/useActiveAccount");
    // The exact live shape: a Meta account selected, then the user navigates
    // to the n8n page, whose only account is a different row entirely.
    useActiveAccountStore.setState({
      activeAccountIdByProvider: { meta: "25efa048", n8n: "dead-n8n-account" },
      activeClientId: null,
    });
    mockIntegrationAccounts.mockReturnValue({ data: [acct("12c04443", "n8n")] });

    const { render } = await import("@testing-library/react");
    const { ConnectedAccountSwitcher } = await import("@/components/ConnectedAccountSwitcher");
    render(<ConnectedAccountSwitcher provider="n8n" />);

    await vi.waitFor(() => {
      expect(useActiveAccountStore.getState().activeAccountIdByProvider["n8n"]).toBeNull();
    });
    // Meta's selection survives — the n8n switcher has no business touching it.
    expect(useActiveAccountStore.getState().activeAccountIdByProvider["meta"]).toBe(
      "25efa048",
    );
  });

  it("does not clear a selection merely because another provider owns it", async () => {
    const { useActiveAccountStore } = await import("@/state/useActiveAccount");
    // n8n has NO selection of its own; Meta's must not be read as n8n's and
    // then sent to /api/n8n/workflows — the 404 that started all this.
    useActiveAccountStore.setState({
      activeAccountIdByProvider: { meta: "25efa048" },
      activeClientId: null,
    });
    mockIntegrationAccounts.mockReturnValue({ data: [acct("12c04443", "n8n")] });

    const { render } = await import("@testing-library/react");
    const { ConnectedAccountSwitcher } = await import("@/components/ConnectedAccountSwitcher");
    render(<ConnectedAccountSwitcher provider="n8n" />);

    await new Promise((r) => setTimeout(r, 0));
    const state = useActiveAccountStore.getState().activeAccountIdByProvider;
    expect(state["n8n"] ?? null).toBeNull();
    expect(state["meta"]).toBe("25efa048");
  });
});
