/**
 * AccountSwitcher — "no conta padrão" regression tests.
 *
 * Direct user request (2026-08-13): there is no "default account" concept in
 * any social-media provider — accounts are purely scoped by marca — and the
 * old placeholder ("Conta padrão {provider}", value="") was the daily
 * friction: it looked selected but meant nothing was, so the user had to
 * swap to the only real account every time.
 *
 * Coverage:
 *   1. Zero accounts — disabled select, honest "Sem contas" label.
 *   2. Exactly one account — auto-selected, no placeholder option at all.
 *   3. More than one account (constructed — live data has no such case
 *      today, but the selector must not be incapable of it) — an explicit,
 *      honestly-labelled placeholder; no auto-select.
 *   4. `is_default` is never read for labelling, in any of the above.
 *
 * Renders the REAL component against the real zustand store (mirrors the
 * "AccountSwitcher" describe block in Conexoes.test.tsx), reset per test.
 *
 * No jest-dom matchers — this product's vitest setup does not wire them (see
 * Conexoes.test.tsx's plain `.toBeTruthy()` / `.length` assertions).
 */
import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";

import { AccountSwitcher } from "./AccountSwitcher";
import { useActiveAccountStore } from "@/state/useActiveAccount";
import type { IntegrationAccount } from "@/hooks/useIntegrationAccounts";

afterEach(() => {
  cleanup();
  useActiveAccountStore.setState({
    activeAccountIdByProvider: {},
    activeMarcaId: null,
  });
});

function acct(
  id: string,
  overrides: Partial<IntegrationAccount> = {},
): IntegrationAccount {
  return {
    id,
    org_id: "org-1",
    provider: "youtube",
    account_label: id,
    marca_id: null,
    status: "validated",
    channel_info: {},
    metadata: {},
    is_default: false,
    last_synced_at: null,
    created_at: "2026-01-01",
    updated_at: "2026-01-01",
    ...overrides,
  };
}

function getAccountSelect(): HTMLSelectElement {
  return screen.getByLabelText(/Selecionar conta YouTube/i) as HTMLSelectElement;
}

// ── 1. Zero accounts ─────────────────────────────────────────────────────────

describe("AccountSwitcher — zero accounts", () => {
  it("renders a disabled select with the honest empty label", () => {
    render(<AccountSwitcher accounts={[]} marcas={[]} providerLabel="YouTube" />);
    const select = getAccountSelect();
    expect(select.disabled).toBe(true);
    expect(select.options.length).toBe(1);
    expect(select.textContent).toContain("Sem contas YouTube");
    expect(select.textContent).not.toMatch(/padrão/i);
  });
});

// ── 2. Exactly one account ────────────────────────────────────────────────────

describe("AccountSwitcher — exactly one account", () => {
  it("auto-selects the sole account, with no placeholder option", () => {
    const account = acct("acc-1", { account_label: "Canal Único" });
    render(
      <AccountSwitcher
        accounts={[account]}
        marcas={[]}
        provider="youtube"
        providerLabel="YouTube"
      />,
    );
    const select = getAccountSelect();
    // No placeholder — the single account is the only option, and it's the
    // one shown, immediately (no flash of an unselected state).
    expect(select.options.length).toBe(1);
    expect(select.value).toBe("acc-1");
    expect(select.textContent).not.toMatch(/padrão/i);
    expect(select.disabled).toBe(false);
  });

  it("commits the auto-selection to the provider-scoped store", () => {
    const account = acct("acc-1");
    render(
      <AccountSwitcher
        accounts={[account]}
        marcas={[]}
        provider="youtube"
        providerLabel="YouTube"
      />,
    );
    expect(
      useActiveAccountStore.getState().activeAccountIdByProvider["youtube"],
    ).toBe("acc-1");
  });

  it("never renders the '(padrão)' suffix even when is_default is true", () => {
    const account = acct("acc-1", {
      account_label: "Canal Único",
      is_default: true,
    });
    render(
      <AccountSwitcher
        accounts={[account]}
        marcas={[]}
        provider="youtube"
        providerLabel="YouTube"
      />,
    );
    expect(screen.getByText("Canal Único")).toBeTruthy();
    expect(screen.queryByText(/padrão/i)).toBeNull();
  });
});

// ── 3. More than one account (constructed) ────────────────────────────────────

describe("AccountSwitcher — multiple accounts (constructed; no live case today)", () => {
  it("shows an honest placeholder that forces an explicit choice — never 'Conta padrão'", () => {
    const a = acct("acc-1", { account_label: "Canal A" });
    const b = acct("acc-2", { account_label: "Canal B" });
    render(
      <AccountSwitcher
        accounts={[a, b]}
        marcas={[]}
        provider="youtube"
        providerLabel="YouTube"
      />,
    );
    const select = getAccountSelect();
    expect(select.value).toBe("");
    expect(select.options.length).toBe(3); // placeholder + 2 accounts
    expect(screen.getByText("Selecione uma conta YouTube")).toBeTruthy();
    expect(screen.queryByText(/Conta padrão/i)).toBeNull();
  });

  it("does not auto-select any account when the choice is ambiguous", () => {
    const a = acct("acc-1");
    const b = acct("acc-2");
    render(
      <AccountSwitcher
        accounts={[a, b]}
        marcas={[]}
        provider="youtube"
        providerLabel="YouTube"
      />,
    );
    expect(
      useActiveAccountStore.getState().activeAccountIdByProvider["youtube"] ?? null,
    ).toBeNull();
  });

  it("never renders the '(padrão)' suffix on any option even when one account is_default", () => {
    const a = acct("acc-1", { account_label: "Canal A", is_default: true });
    const b = acct("acc-2", { account_label: "Canal B" });
    render(
      <AccountSwitcher
        accounts={[a, b]}
        marcas={[]}
        provider="youtube"
        providerLabel="YouTube"
      />,
    );
    expect(screen.getByText("Canal A")).toBeTruthy();
    expect(screen.getByText("Canal B")).toBeTruthy();
    expect(screen.queryByText(/\(padrão\)/i)).toBeNull();
  });

  it("respects an explicit persisted selection instead of the placeholder", () => {
    useActiveAccountStore.setState({
      activeAccountIdByProvider: { youtube: "acc-2" },
      activeMarcaId: null,
    });
    const a = acct("acc-1");
    const b = acct("acc-2");
    render(
      <AccountSwitcher
        accounts={[a, b]}
        marcas={[]}
        provider="youtube"
        providerLabel="YouTube"
      />,
    );
    expect(getAccountSelect().value).toBe("acc-2");
  });
});
