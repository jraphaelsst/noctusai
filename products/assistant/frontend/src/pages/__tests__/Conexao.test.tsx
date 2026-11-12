/** Route test: `/conexao` -- admin-only pairing page over the seed organ; the read-only notice is always shown. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

const admin = { value: true };
vi.mock("@noctusai/lib/design-system", async (orig) => ({ ...(await orig<object>()), useIsOrgAdmin: () => admin.value }));
vi.mock("@noctusai/lib/components", async (orig) => ({
  ...(await orig<object>()),
  WhatsAppConnectionsPage: ({ banner, emptyState }: { banner: React.ReactNode; emptyState: React.ReactNode }) => (
    <div data-testid="organ">{banner}{emptyState}</div>
  ),
}));
vi.mock("@/lib/whatsapp", () => ({ connectionsHooks: {} }));

import Conexao from "../Conexao";

afterEach(cleanup);

describe("Conexao", () => {
  it("renders the organ with the read-only notice for an admin", () => {
    admin.value = true;
    render(<Conexao />);
    expect(screen.getByTestId("organ")).toBeInTheDocument();
    expect(screen.getByTestId("conexao-resposta")).toHaveTextContent("número é permitido");
  });

  it("refuses a non-admin", () => {
    admin.value = false;
    render(<Conexao />);
    expect(screen.getByTestId("conexao-acesso-restrito")).toBeInTheDocument();
    expect(screen.queryByTestId("organ")).toBeNull();
  });
});
