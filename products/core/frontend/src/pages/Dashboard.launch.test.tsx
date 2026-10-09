/**
 * Dashboard launch (SSO P2.1): the card opens the SERVER-built `redirect_url`
 * verbatim, with `noopener`. The frontend never recomputes the token transport
 * (fragment vs query) -- that is the catalog-derived regime, decided in core.
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Dashboard } from "./Dashboard";

const post = vi.fn();

// Stable identities: a fresh object per render would re-fire the page effects forever.
vi.mock("../lib/auth-context", () => {
  const auth = {
    user: { id: "u1" },
    organization: { id: "org-1", category: "client" },
    isAdmin: false,
    loading: false,
    logout: () => {},
  };
  return { useAuth: () => auth };
});

vi.mock("../components/layout/CoreHeader", () => ({ CoreHeader: () => null }));

vi.mock("../lib/api", () => ({
  api: {
    get: vi.fn().mockImplementation((url: string) => {
      if (url === "/api/auth/me") {
        return Promise.resolve({
          products: [
            {
              id: "p1", nome: "Prod Um", slug: "prod-um", descricao: "d", icone: "Box",
              url_base: "http://stale-db-url", cor: "#000", has_access: true,
              ativo: true, deploy_scope: "live",
            },
          ],
        });
      }
      return Promise.resolve({ data: null });
    }),
    post: (...a: unknown[]) => post(...a),
  },
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  post.mockReset();
});

describe("Dashboard launchProduct", () => {
  it("opens res.redirect_url with noopener (no client-built ?token= URL)", async () => {
    post.mockResolvedValue({
      sso_token: "TOK",
      product_slug: "prod-um",
      redirect_url: "https://prod-um.example/sso#token=TOK",
    });
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    render(<MemoryRouter><Dashboard /></MemoryRouter>);
    fireEvent.click(await screen.findByText("Prod Um"));
    await waitFor(() => expect(open).toHaveBeenCalled());
    expect(post).toHaveBeenCalledWith("/api/sso/token", { product_slug: "prod-um" });
    expect(open).toHaveBeenCalledWith("https://prod-um.example/sso#token=TOK", "_blank", "noopener");
  });
});
