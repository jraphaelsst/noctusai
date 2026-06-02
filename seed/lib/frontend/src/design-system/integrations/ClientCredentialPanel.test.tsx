/**
 * Tests for the ClientCredentialPanel organ.
 *
 * Coverage:
 *   1. Loading state — skeleton with aria-busy
 *   2. Error state — alert with message
 *   3. Empty state (no accounts, no clients) — empty message
 *   4. Success: accounts rendered as IntegrationCards
 *   5. Tab selector rendered when clients are present
 *   6. All tab shows all accounts
 *   7. Client tab filters accounts to that client
 *   8. "Sem cliente" tab filters to unassigned accounts
 *   9. Tab badges show correct counts
 *  10. Add button fires onAdd with correct clientId (All tab → null)
 *  11. Add button fires onAdd with correct clientId (client tab → clientId)
 *  12. Add button fires onAdd with null for "Sem cliente" tab
 *  13. onDelete propagated from card
 *  14. onSetDefault propagated from card
 *  15. busyAccountId disables the matching card
 *
 * Dual-React gap: resolved in the noctusai monorepo (NOC-REMEDIATE resolved
 * 2026-05-29). Full render tests are safe here.
 */
/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";

import { ClientCredentialPanel } from "./ClientCredentialPanel";
import type { IntegrationAccount } from "./types";
import type { ClientRef } from "./ClientCredentialPanel";

afterEach(cleanup);

// ── Fixtures ─────────────────────────────────────────────────────────────────

const clientA: ClientRef = { id: "client-a", name: "Acme Corp", slug: "acme" };
const clientB: ClientRef = { id: "client-b", name: "Beta LLC", slug: "beta" };

function makeAccount(
  id: string,
  clientId: string | null,
  label = "Canal Teste",
): IntegrationAccount {
  return {
    id,
    org_id: "org-1",
    provider: "youtube",
    account_label: label,
    client_id: clientId,
    status: "validated",
    channel_info: {
      title: `Channel ${id}`,
      subscriber_count: 1000,
      video_count: 10,
      view_count: 5000,
    },
    metadata: {},
    is_default: false,
    last_synced_at: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

const accountA1 = makeAccount("acc-a1", "client-a", "Acme Canal 1");
const accountA2 = makeAccount("acc-a2", "client-a", "Acme Canal 2");
const accountB1 = makeAccount("acc-b1", "client-b", "Beta Canal 1");
const accountUnassigned = makeAccount("acc-u1", null, "Canal Sem Cliente");

// ── 1. Loading state ──────────────────────────────────────────────────────────

describe("ClientCredentialPanel: loading", () => {
  it("renders skeleton with aria-busy", () => {
    const { container } = render(
      <ClientCredentialPanel
        accounts={[]}
        clients={[]}
        provider="youtube"
        isLoading
      />,
    );
    const el = container.querySelector('[aria-busy="true"]');
    expect(el).not.toBeNull();
  });
});

// ── 2. Error state ────────────────────────────────────────────────────────────

describe("ClientCredentialPanel: error", () => {
  it("renders error alert with message", () => {
    render(
      <ClientCredentialPanel
        accounts={[]}
        clients={[]}
        provider="youtube"
        error={new Error("Falha ao buscar credenciais")}
      />,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/Falha ao buscar credenciais/)).toBeInTheDocument();
  });
});

// ── 3. Empty state (no accounts, no clients) ──────────────────────────────────

describe("ClientCredentialPanel: empty", () => {
  it("renders empty state message when no accounts", () => {
    render(
      <ClientCredentialPanel accounts={[]} clients={[]} provider="youtube" />,
    );
    expect(
      screen.getByLabelText(/Nenhuma conta youtube encontrada/i),
    ).toBeInTheDocument();
  });
});

// ── 4. Success: accounts rendered ────────────────────────────────────────────

describe("ClientCredentialPanel: success", () => {
  it("renders an IntegrationCard per account", () => {
    render(
      <ClientCredentialPanel
        accounts={[accountA1, accountB1]}
        clients={[clientA, clientB]}
        provider="youtube"
      />,
    );
    // Cards render with the channel title (from channel_info.title)
    expect(screen.getByText("Channel acc-a1")).toBeInTheDocument();
    expect(screen.getByText("Channel acc-b1")).toBeInTheDocument();
  });
});

// ── 5. Tab selector when clients are present ──────────────────────────────────

describe("ClientCredentialPanel: tab selector", () => {
  it("renders tabs when clients list is non-empty", () => {
    render(
      <ClientCredentialPanel
        accounts={[accountA1]}
        clients={[clientA]}
        provider="youtube"
      />,
    );
    expect(screen.getByRole("tablist")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Todos/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Acme Corp/i })).toBeInTheDocument();
  });

  it("does not render tablist when clients list is empty", () => {
    render(
      <ClientCredentialPanel
        accounts={[accountA1]}
        clients={[]}
        provider="youtube"
      />,
    );
    expect(screen.queryByRole("tablist")).toBeNull();
  });
});

// ── 6. All tab shows all accounts ─────────────────────────────────────────────

describe("ClientCredentialPanel: All tab", () => {
  it("shows all accounts by default (All tab is active)", () => {
    render(
      <ClientCredentialPanel
        accounts={[accountA1, accountB1, accountUnassigned]}
        clients={[clientA, clientB]}
        provider="youtube"
      />,
    );
    expect(screen.getByText("Channel acc-a1")).toBeInTheDocument();
    expect(screen.getByText("Channel acc-b1")).toBeInTheDocument();
    expect(screen.getByText("Channel acc-u1")).toBeInTheDocument();
  });
});

// ── 7. Client tab filters accounts ───────────────────────────────────────────

describe("ClientCredentialPanel: client tab filter", () => {
  it("clicking a client tab shows only that client's accounts", () => {
    render(
      <ClientCredentialPanel
        accounts={[accountA1, accountA2, accountB1]}
        clients={[clientA, clientB]}
        provider="youtube"
      />,
    );
    fireEvent.click(screen.getByRole("tab", { name: /Acme Corp/i }));
    expect(screen.getByText("Channel acc-a1")).toBeInTheDocument();
    expect(screen.getByText("Channel acc-a2")).toBeInTheDocument();
    // Beta account should NOT be visible
    expect(screen.queryByText("Channel acc-b1")).toBeNull();
  });
});

// ── 8. "Sem cliente" tab filters unassigned ───────────────────────────────────

describe("ClientCredentialPanel: Sem cliente tab", () => {
  it("shows only unassigned accounts", () => {
    render(
      <ClientCredentialPanel
        accounts={[accountA1, accountUnassigned]}
        clients={[clientA]}
        provider="youtube"
      />,
    );
    fireEvent.click(screen.getByRole("tab", { name: /Sem cliente/i }));
    expect(screen.getByText("Channel acc-u1")).toBeInTheDocument();
    expect(screen.queryByText("Channel acc-a1")).toBeNull();
  });
});

// ── 9. Tab badges show counts ─────────────────────────────────────────────────

describe("ClientCredentialPanel: tab badges", () => {
  it("Todos tab badge shows total account count", () => {
    render(
      <ClientCredentialPanel
        accounts={[accountA1, accountA2, accountB1]}
        clients={[clientA, clientB]}
        provider="youtube"
      />,
    );
    // The Todos tab contains the count "3" as a badge
    const allTab = screen.getByRole("tab", { name: /Todos/i });
    expect(allTab.textContent).toMatch("3");
  });

  it("client tab badge shows that client's account count", () => {
    render(
      <ClientCredentialPanel
        accounts={[accountA1, accountA2, accountB1]}
        clients={[clientA, clientB]}
        provider="youtube"
      />,
    );
    const acmeTab = screen.getByRole("tab", { name: /Acme Corp/i });
    expect(acmeTab.textContent).toMatch("2");
  });
});

// ── 10. onAdd fires with null on All tab ──────────────────────────────────────

describe("ClientCredentialPanel: onAdd", () => {
  it("calls onAdd(null) when adding from the All tab", () => {
    const onAdd = vi.fn();
    render(
      <ClientCredentialPanel
        accounts={[]}
        clients={[clientA]}
        provider="youtube"
        onAdd={onAdd}
      />,
    );
    // Default tab is All
    fireEvent.click(screen.getByRole("button", { name: /Adicionar conta/i }));
    expect(onAdd).toHaveBeenCalledWith(null);
  });

  it("calls onAdd(clientId) when adding from a client tab", () => {
    const onAdd = vi.fn();
    render(
      <ClientCredentialPanel
        accounts={[]}
        clients={[clientA]}
        provider="youtube"
        onAdd={onAdd}
      />,
    );
    fireEvent.click(screen.getByRole("tab", { name: /Acme Corp/i }));
    fireEvent.click(screen.getByRole("button", { name: /Adicionar conta/i }));
    expect(onAdd).toHaveBeenCalledWith("client-a");
  });

  it("calls onAdd(null) when adding from the Sem cliente tab", () => {
    const onAdd = vi.fn();
    render(
      <ClientCredentialPanel
        accounts={[]}
        clients={[clientA]}
        provider="youtube"
        onAdd={onAdd}
      />,
    );
    fireEvent.click(screen.getByRole("tab", { name: /Sem cliente/i }));
    fireEvent.click(screen.getByRole("button", { name: /Adicionar conta/i }));
    expect(onAdd).toHaveBeenCalledWith(null);
  });
});

// ── 13. onDelete propagated ───────────────────────────────────────────────────

describe("ClientCredentialPanel: onDelete propagated", () => {
  it("fires onDelete callback when the card's delete action is triggered", () => {
    const onDelete = vi.fn();
    render(
      <ClientCredentialPanel
        accounts={[accountA1]}
        clients={[]}
        provider="youtube"
        onDelete={onDelete}
      />,
    );
    // Open the actions menu and click Remove
    fireEvent.click(screen.getByRole("button", { name: /Mais ações/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /Remover/i }));
    expect(onDelete).toHaveBeenCalledWith(accountA1);
  });
});

// ── 14. onSetDefault propagated ───────────────────────────────────────────────

describe("ClientCredentialPanel: onSetDefault propagated", () => {
  it("fires onSetDefault callback from card actions menu", () => {
    const onSetDefault = vi.fn();
    const nonDefault = { ...accountA1, is_default: false };
    render(
      <ClientCredentialPanel
        accounts={[nonDefault]}
        clients={[]}
        provider="youtube"
        onSetDefault={onSetDefault}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Mais ações/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /Definir como padrão/i }));
    expect(onSetDefault).toHaveBeenCalledWith(nonDefault);
  });
});

// ── 15. busyAccountId disables the correct card ───────────────────────────────

describe("ClientCredentialPanel: busyAccountId", () => {
  it("card with busyAccountId shows busy overlay (disables controls)", () => {
    render(
      <ClientCredentialPanel
        accounts={[accountA1]}
        clients={[]}
        provider="youtube"
        busyAccountId="acc-a1"
        onDelete={vi.fn()}
      />,
    );
    // The busy overlay disables buttons — the actions button should be disabled
    const moreBtn = screen.getByRole("button", { name: /Mais ações/i });
    expect(moreBtn).toBeDisabled();
  });
});
