/** Financeiro -- the URL is the tab; the seed organs render the money screens. */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom";

vi.mock("@noctusai/seed/infra", () => {
  const noop = () => {};
  const api = { get: noop, post: noop, patch: noop, put: noop, delete: noop };
  return { api, supabase: {}, appConfig: {}, useAuthStore: () => ({ user: null }), default: { api } };
});
vi.mock("@/components/ChargesPanel", () => ({ ChargesPanel: ({ isAdmin }: { isAdmin: boolean }) => <div data-testid="charges" data-admin={String(isAdmin)} /> }));
vi.mock("@noctusai/lib", async (orig) => ({
  ...(await orig<typeof import("@noctusai/lib")>()),
  ContractsTable: ({ canWrite }: { canWrite: boolean }) => <div data-testid="contracts" data-write={String(canWrite)} />,
  RemindersPage: ({ isAdmin }: { isAdmin: boolean }) => <div data-testid="reminders" data-admin={String(isAdmin)} />,
  FinanceRoutedPage: ({ basePath, isAdmin }: { basePath: string; isAdmin: boolean }) => <div data-testid="finance" data-base={basePath} data-admin={String(isAdmin)} />,
}));
vi.mock("@noctusai/lib/design-system", async (orig) => ({ ...(await orig<typeof import("@noctusai/lib/design-system")>()), useIsOrgAdmin: () => true }));

import Financeiro, { tabFromPath } from "../Financeiro";

const at = (path: string) => render(<MemoryRouter initialEntries={[path]}><Financeiro /></MemoryRouter>);

describe("tabFromPath", () => {
  it.each([
    ["/financeiro", "financeiro"], ["/financeiro/receber", "financeiro"], ["/financeiro/contratos", "contratos"],
    ["/financeiro/contratos/", "contratos"], ["/financeiro/cobrancas", "cobrancas"], ["/financeiro/lembretes", "lembretes"], ["/financeiro/dre", "financeiro"],
  ])("%s -> %s", (path, tab) => expect(tabFromPath(path)).toBe(tab));
});

describe("Financeiro", () => {
  it("/financeiro mounts the seed finance organ under the splat base", () => {
    at("/financeiro/receber");
    expect(screen.getByTestId("finance")).toHaveAttribute("data-base", "/financeiro");
    expect(screen.getByTestId("finance")).toHaveAttribute("data-admin", "true");
    expect(screen.queryByTestId("contracts")).not.toBeInTheDocument();
  });

  it("/financeiro/contratos mounts the seed contracts organ", () => {
    at("/financeiro/contratos");
    expect(screen.getByTestId("contracts")).toHaveAttribute("data-write", "true");
    expect(screen.queryByTestId("finance")).not.toBeInTheDocument();
  });

  it("/financeiro/cobrancas mounts the gateway charges view", () => {
    at("/financeiro/cobrancas");
    expect(screen.getByTestId("charges")).toHaveAttribute("data-admin", "true");
  });

  it("/financeiro/lembretes mounts the seed billing-reminders page", () => {
    at("/financeiro/lembretes");
    expect(screen.getByTestId("reminders")).toHaveAttribute("data-admin", "true");
    expect(screen.queryByTestId("charges")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Lembretes" })).toHaveAttribute("aria-current", "page");
  });

  it("the tab bar marks the current section and links to the others", () => {
    at("/financeiro/contratos");
    expect(screen.getByRole("link", { name: "Contratos" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Cobranças" })).toHaveAttribute("href", "/financeiro/cobrancas");
    expect(screen.getByRole("link", { name: "Financeiro" })).not.toHaveAttribute("aria-current");
  });
});
