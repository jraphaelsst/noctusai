/**
 * Route test: the seed finance organ page mounted at `/admin/financeiro` -- the shell renders its section nav, the section
 * follows the URL, and the page talks to the `/api/finance` API through the product's `api` client.
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const { api } = vi.hoisted(() => ({
  api: {
    get: vi.fn((_path: string) => new Promise(() => {})),
    post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn(), upload: vi.fn(), download: vi.fn(),
  },
}));
vi.mock("../../lib/api", () => ({ api }));
const auth = vi.hoisted(() => ({ isAdmin: true }));
vi.mock("../../lib/auth-context", () => ({ useAuth: () => ({ isAdmin: auth.isAdmin }) }));

import { AdminFinanceiro } from "./AdminFinanceiro";
import { FinanceiroLigacoes } from "./FinanceiroLigacoes";

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <AdminFinanceiro />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  auth.isAdmin = true;
  cleanup();
  api.get.mockClear();
});

describe("AdminFinanceiro route", () => {
  it("renders the finance shell navigation", () => {
    renderAt("/admin/financeiro");
    const nav = screen.getByRole("navigation", { name: "Financeiro" });
    expect(nav).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Contas a receber" })).toBeInTheDocument();
  });

  it("follows the URL segment to the matching section and reads from /api/finance", () => {
    renderAt("/admin/financeiro/receber");
    expect(screen.getByRole("button", { name: "Contas a receber" })).toHaveAttribute("aria-current", "page");
    expect(api.get.mock.calls.some(([p]) => String(p).startsWith("/api/finance/"))).toBe(true);
  });

  it("shows the no-permission card (and calls nothing) for a non-admin", () => {
    auth.isAdmin = false;
    renderAt("/admin/financeiro");
    expect(screen.getByRole("heading", { name: "Esta área é só para administradores da plataforma" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Financeiro" })).not.toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalled();
  });
});

describe("FinanceiroLigacoes", () => {
  it("lists the four bridges with their real state", () => {
    render(<FinanceiroLigacoes />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(4);
    expect(items[0]).toHaveTextContent("Faturamento (Stripe) → Contas a receber");
    expect(items[0]).toHaveTextContent("Não ligada");
    expect(items[1]).toHaveTextContent("Não existe ainda");
    expect(items[2]).toHaveTextContent("Não existe ainda");
    expect(items[3]).toHaveTextContent("Já existe");
  });
});
