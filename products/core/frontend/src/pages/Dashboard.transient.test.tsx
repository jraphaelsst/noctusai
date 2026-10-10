/**
 * 2026-10-10: a core redeploy made `/api/auth/me` fail for a few seconds and
 * the Dashboard's bare `catch` called the GLOBAL logout — revoking every
 * product session and the acting org. A failed /me must keep the session and
 * show a retry state; a dead session is the api client's 401 path, not this.
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Dashboard } from "./Dashboard";

const logout = vi.fn();
const get = vi.fn();

vi.mock("../lib/auth-context", () => {
  const auth = {
    user: { id: "u1" },
    organization: { id: "org-1", category: "client" },
    isAdmin: false,
    loading: false,
    unavailable: false,
    refresh: async () => {},
    logout: (...a: unknown[]) => logout(...a),
  };
  return { useAuth: () => auth };
});
vi.mock("../components/layout/CoreHeader", () => ({ CoreHeader: () => null }));
vi.mock("../lib/api", () => ({ api: { get: (...a: unknown[]) => get(...a), post: vi.fn() } }));

afterEach(() => { cleanup(); get.mockReset(); logout.mockReset(); });

describe("Dashboard on a transient /api/auth/me failure", () => {
  it("shows the retry state and never logs out", async () => {
    get.mockImplementation((url: string) =>
      url === "/api/auth/me" ? Promise.reject(new Error("[502] Bad Gateway")) : Promise.resolve({ data: null }));
    render(<MemoryRouter><Dashboard /></MemoryRouter>);
    expect(await screen.findByText(/temporariamente indisponível/)).toBeTruthy();
    expect(logout).not.toHaveBeenCalled();
  });

  it("'Tentar novamente' re-reads /me and renders the dashboard once it answers", async () => {
    let fail = true;
    get.mockImplementation((url: string) => {
      if (url === "/api/auth/me") {
        return fail ? Promise.reject(new Error("network")) : Promise.resolve({ products: [] });
      }
      return Promise.resolve({ data: null, deployed: {} });
    });
    render(<MemoryRouter><Dashboard /></MemoryRouter>);
    const retry = await screen.findByRole("button", { name: "Tentar novamente" });
    fail = false;
    fireEvent.click(retry);
    await waitFor(() => expect(screen.queryByText(/temporariamente indisponível/)).toBeNull());
    expect(logout).not.toHaveBeenCalled();
  });
});
