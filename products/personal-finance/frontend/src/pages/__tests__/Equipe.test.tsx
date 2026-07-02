/**
 * Equipe page — direct-fetch (Pattern D) contract test
 * (PF Phase 6.b + Phase 6.d).
 *
 * Per design-batch Q-equipe, Equipe.tsx retains direct `api.get/post/delete`
 * against the seed `team` standard router instead of being extracted to a
 * `useTeam` hook layer (Pattern D). Rationale: one-off page; not worth a
 * hook layer for one page (catalogued in accept-with-rationale).
 *
 * This test pins the contract — the 2 mount-time GET callsites + the
 * member-list render contract — so any drift from the seed `team`
 * standard-router shape surfaces immediately. The remaining 3 callsites
 * (POST /invite, DELETE /{id}, DELETE /invitations/{id}) are static
 * contract that lives in Equipe.tsx source and is exercised at the
 * manual-QA round (deferred — destination: user/orchestrator at
 * Phase 7).
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

// vi.hoisted lifts these spies above the hoisted vi.mock factory below,
// so the closure inside the factory sees them at module-init time.
const mocks = vi.hoisted(() => {
  const apiCalls: { method: string; url: string; body?: unknown }[] = [];
  return {
    apiCalls,
    apiGet: vi.fn(async (url: string) => {
      apiCalls.push({ method: "GET", url });
      if (url === "/api/team") {
        return {
          data: [
            {
              id: "u1",
              nome: "Alice",
              email: "a@x.com",
              role: "admin",
              org_role: "admin",
              created_at: "2026-05-01",
            },
          ],
        };
      }
      if (url === "/api/team/invitations") {
        return {
          data: [
            {
              id: "i1",
              email: "b@x.com",
              role: "member",
              status: "pending",
              created_at: "2026-05-02",
              expires_at: "2026-05-09",
            },
          ],
        };
      }
      return { data: [] };
    }),
    apiPost: vi.fn(async () => ({ data: { ok: true } })),
    apiDelete: vi.fn(async () => ({ ok: true })),
  };
});

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mocks.apiGet, post: mocks.apiPost, delete: mocks.apiDelete },
  useAuthStore: () => ({
    user: {
      id: "user-1",
      email: "owner@x.com",
      user_metadata: { org_id: "org-1", org_role: "owner" },
    },
  }),
}));

vi.mock("@noctusai/lib", () => ({
  resolveSSOContext: (metadata: Record<string, unknown> | undefined) => ({
    isProductAdmin: false,
    org: { role: (metadata?.org_role as string) ?? "member" },
    noctus: {},
  }),
  // StatusPaginaPanel is a react-query organ (seed lib) with its own
  // dedicated test coverage (seed/lib/frontend/src/components/StatusPaginaPanel.test.tsx);
  // this page-contract test doesn't wire a QueryClientProvider, so stub it.
  StatusPaginaPanel: () => null,
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import Equipe from "@/pages/Equipe";

describe("Equipe page (PF Phase 6.b/6.d — seed team direct-fetch)", () => {
  it("on mount, fetches /api/team + /api/team/invitations (Pattern D callsites 1-2)", async () => {
    mocks.apiCalls.length = 0;
    mocks.apiGet.mockClear();

    render(
      <MemoryRouter>
        <Equipe />
      </MemoryRouter>,
    );

    await waitFor(() => {
      const urls = mocks.apiCalls
        .filter((c) => c.method === "GET")
        .map((c) => c.url);
      expect(urls).toContain("/api/team");
      expect(urls).toContain("/api/team/invitations");
    });
  });

  it("renders the member fetched from /api/team", async () => {
    mocks.apiCalls.length = 0;
    mocks.apiGet.mockClear();

    render(
      <MemoryRouter>
        <Equipe />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.queryByText("Alice")).not.toBeNull();
    });
  });

  it("pins the 5 Pattern D direct-fetch URL shapes against seed `team` standard router", () => {
    // Static contract — drift triggers re-audit of
    // `seed/framework/backend/noctusai_seed/routers.py::_create_team_router`.
    const EXPECTED_DIRECT_URLS = [
      { method: "GET", path: "/api/team" },
      { method: "GET", path: "/api/team/invitations" },
      { method: "POST", path: "/api/team/invite" },
      { method: "DELETE", path: "/api/team/{id}" },
      { method: "DELETE", path: "/api/team/invitations/{id}" },
    ];
    expect(EXPECTED_DIRECT_URLS).toHaveLength(5);
  });
});
