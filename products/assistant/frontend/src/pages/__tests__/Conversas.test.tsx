/** Route test: `/conversas` -- admin-only inbox over the seed organ; no-connection state links to Conexão. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

const admin = { value: true };
const conns: { value: { data: unknown; showSkeleton: boolean; error: unknown; refetch: () => void } } = {
  value: { data: [{ id: "c1" }], showSkeleton: false, error: null, refetch: () => {} },
};
vi.mock("@noctusai/lib/design-system", async (orig) => ({ ...(await orig<object>()), useIsOrgAdmin: () => admin.value }));
vi.mock("@noctusai/lib/components", async (orig) => ({
  ...(await orig<object>()),
  WhatsAppInbox: ({ connectionId, enableAgentPause, allowDeleteChat }: { connectionId: string; enableAgentPause?: boolean; allowDeleteChat?: boolean }) => (
    <div data-testid="organ" data-pause={String(!!enableAgentPause)} data-delete={String(!!allowDeleteChat)}>{connectionId}</div>
  ),
}));
vi.mock("@/lib/whatsapp", () => ({ connectionsHooks: { useConnections: () => conns.value }, inboxHooks: {} }));

import Conversas from "../Conversas";

const view = () => render(<MemoryRouter><Conversas /></MemoryRouter>);
afterEach(cleanup);

describe("Conversas", () => {
  it("renders the inbox organ for an admin over the first connection", () => {
    admin.value = true;
    conns.value = { data: [{ id: "c1" }], showSkeleton: false, error: null, refetch: () => {} };
    view();
    expect(screen.getByTestId("organ")).toHaveTextContent("c1");
  });

  it("turns the per-chat agent pause and the LGPD delete on for the admin", () => {
    admin.value = true;
    conns.value = { data: [{ id: "c1" }], showSkeleton: false, error: null, refetch: () => {} };
    view();
    expect(screen.getByTestId("organ")).toHaveAttribute("data-pause", "true");
    expect(screen.getByTestId("organ")).toHaveAttribute("data-delete", "true");
  });

  it("points to Conexão when no line is connected", () => {
    admin.value = true;
    conns.value = { data: [], showSkeleton: false, error: null, refetch: () => {} };
    view();
    expect(screen.getByTestId("conversas-sem-conexao")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /conectar o número/i })).toHaveAttribute("href", "/conexao");
    expect(screen.queryByTestId("organ")).toBeNull();
  });

  it("shows a skeleton on the first load, never an empty state", () => {
    admin.value = true;
    conns.value = { data: undefined, showSkeleton: true, error: null, refetch: () => {} };
    view();
    expect(screen.getByTestId("conversas-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("conversas-sem-conexao")).toBeNull();
  });

  it("says so when the line cannot be loaded", () => {
    admin.value = true;
    conns.value = { data: undefined, showSkeleton: false, error: new Error("x"), refetch: () => {} };
    view();
    expect(screen.getByTestId("conversas-erro")).toBeInTheDocument();
  });

  it("refuses a non-admin", () => {
    admin.value = false;
    view();
    expect(screen.getByTestId("conversas-acesso-restrito")).toBeInTheDocument();
    expect(screen.queryByTestId("organ")).toBeNull();
  });
});
