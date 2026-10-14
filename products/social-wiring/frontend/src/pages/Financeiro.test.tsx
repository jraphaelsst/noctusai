/**
 * Route test: the seed finance organ page mounted at `/financeiro` -- the shell renders its section nav, the section
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
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/lib/design-system", async (orig) => ({ ...(await orig<object>()), useIsOrgAdmin: () => true }));

import Financeiro from "./Financeiro";

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Financeiro />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  api.get.mockClear();
});

describe("Financeiro route", () => {
  it("renders the finance shell navigation", () => {
    renderAt("/financeiro");
    const nav = screen.getByRole("navigation", { name: "Financeiro" });
    expect(nav).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Contas a receber" })).toBeInTheDocument();
  });

  it("follows the URL segment to the matching section and reads from /api/finance", () => {
    renderAt("/financeiro/receber");
    expect(screen.getByRole("button", { name: "Contas a receber" })).toHaveAttribute("aria-current", "page");
    expect(api.get.mock.calls.some(([p]) => String(p).startsWith("/api/finance/"))).toBe(true);
  });
});
