/**
 * Route test: the seed finance organ page mounted at `/financeiro/*` -- the shell renders its section nav, the section
 * follows the URL (and writes it back), and the page talks to `/api/finance` through the product's `api` client.
 * The organ's own URL sync is covered in `seed/lib` (`FinanceRoutedPage.test.tsx`); this pins the product wiring.
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

const { api } = vi.hoisted(() => ({
  api: {
    get: vi.fn((_path: string) => new Promise(() => {})),
    post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn(), upload: vi.fn(), download: vi.fn(),
  },
}));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/lib/design-system", async (orig) => ({ ...(await orig<object>()), useIsOrgAdmin: () => true }));

import Financeiro from "../Financeiro";

function Where() {
  return <span data-testid="where">{useLocation().pathname}</span>;
}

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/financeiro/*" element={<><Financeiro /><Where /></>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  api.get.mockClear();
});

describe("Financeiro route", () => {
  it("renders the finance shell navigation at the overview", () => {
    renderAt("/financeiro");
    expect(screen.getByRole("navigation", { name: "Financeiro" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Visão geral" })).toHaveAttribute("aria-current", "page");
  });

  it("follows the URL segment to the matching section and reads from /api/finance", () => {
    renderAt("/financeiro/receber");
    expect(screen.getByRole("button", { name: "Contas a receber" })).toHaveAttribute("aria-current", "page");
    expect(api.get.mock.calls.some(([p]) => String(p).startsWith("/api/finance/"))).toBe(true);
  });

  it("section changes write the URL back (the overview returns to /financeiro)", () => {
    renderAt("/financeiro/dre");
    fireEvent.click(screen.getByRole("button", { name: "Contas a pagar" }));
    expect(screen.getByTestId("where").textContent).toBe("/financeiro/pagar");
    fireEvent.click(screen.getByRole("button", { name: "Visão geral" }));
    expect(screen.getByTestId("where").textContent).toBe("/financeiro");
  });
});
