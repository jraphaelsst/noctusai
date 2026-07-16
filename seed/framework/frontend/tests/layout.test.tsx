/**
 * Tests for `createProductLayout`'s dual auth mode: the default
 * `supabase`-based path (unchanged — backward compat) and the
 * `sessionAuth` cookie-session sibling (`erp-httponly-cookie-session-2026-07`
 * roadmap, Slice-3 blocker finding).
 *
 * The load-bearing test in this file is "session mode — clicking logout
 * calls sessionAuth.onLogout and never touches supabase.auth.signOut": it
 * proves the seam actually prevents the silent-no-op logout bug (session
 * mode is constructed with NO `supabase` client at all, so a wrong branch
 * that fell through to `supabase!.auth.signOut()` would throw a
 * `TypeError` on `undefined.auth` — the test would fail loudly, not
 * silently pass with the wrong handler having (not) fired).
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Home } from "lucide-react";
import { createProductLayout, type ProductLayoutConfig, type LayoutSessionAuth } from "../src/layout";
import type { NavGroupWithRoute } from "@noctusai/lib";
import type { NavGroup } from "@noctusai/lib/design-system";

// ── Fixtures ────────────────────────────────────────────────────────────────

const NAV_GROUPS: NavGroupWithRoute[] = [
  {
    key: "main",
    label: "Main",
    items: [
      { name: "Dashboard", href: "/dashboard", route: "dashboard" },
      { name: "Reports", href: "/reports", route: "reports" },
    ],
  },
];

const NAV_FALLBACK: NavGroup[] = [
  {
    key: "main",
    label: "Main",
    items: [
      { name: "Dashboard", href: "/dashboard" },
      { name: "Reports", href: "/reports" },
    ],
  },
];

const NotificationBell = () => <span data-testid="notification-bell-stub" />;

function baseConfig(): Omit<ProductLayoutConfig, "supabase" | "sessionAuth"> {
  return {
    brandIcon: Home,
    brandTitle: "Test Product",
    navGroups: NAV_GROUPS,
    navGroupsFallback: NAV_FALLBACK,
    useAuthStore: () => ({ user: { id: "u1", email: "u1@example.com" } }),
    NotificationBell,
  };
}

/** Fake Supabase client — the minimum `.auth`/`.from` surface layout.tsx touches. */
function makeSupabaseClient() {
  return {
    auth: {
      signOut: vi.fn().mockResolvedValue({ error: null }),
      updateUser: vi.fn().mockResolvedValue({ error: null }),
      refreshSession: vi.fn().mockResolvedValue({ data: { session: null }, error: null }),
    },
    from: vi.fn(() => ({
      select: vi.fn().mockResolvedValue({ data: [] }),
    })),
  };
}

/** Fake `sessionAuth` — every required field is a spy so tests can prove
 * invocation, not just presence. */
function makeSessionAuth(): LayoutSessionAuth {
  return {
    onLogout: vi.fn().mockResolvedValue(undefined),
    onUpdatePassword: vi.fn().mockResolvedValue(undefined),
    onUpdateProfile: vi.fn().mockResolvedValue(undefined),
    onExtend: vi.fn().mockResolvedValue(undefined),
  };
}

function renderLayout(Layout: React.ComponentType<{ children: React.ReactNode }>) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <Layout>
        <div data-testid="child-content">child</div>
      </Layout>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  // Prevent jsdom's "Not implemented: navigation" noise when handleLogout /
  // InactivityWarning.onExpired assign `window.location.href`.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  delete (window as any).location;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (window as any).location = { href: "" };
});

// ── Construction validation ──────────────────────────────────────────────────

describe("createProductLayout — construction validation", () => {
  it("throws when neither `supabase` nor `sessionAuth` is provided", () => {
    expect(() => createProductLayout({ ...baseConfig() } as ProductLayoutConfig)).toThrow(
      /must provide either `sessionAuth`.*or `supabase`/,
    );
  });
});

// ── Supabase mode (backward compat — existing ~10 products, unchanged) ──────

describe("createProductLayout — supabase mode (backward compat)", () => {
  it("renders successfully with only `supabase` (the pre-existing config shape)", () => {
    const supabase = makeSupabaseClient();
    const Layout = createProductLayout({ ...baseConfig(), supabase });
    renderLayout(Layout);
    expect(screen.getByTestId("child-content")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-brand")).toHaveTextContent("Test Product");
  });

  it("clicking logout calls supabase.auth.signOut() and redirects", async () => {
    const supabase = makeSupabaseClient();
    const Layout = createProductLayout({ ...baseConfig(), supabase });
    renderLayout(Layout);

    fireEvent.click(screen.getByTestId("logout-button"));

    await waitFor(() => expect(supabase.auth.signOut).toHaveBeenCalledTimes(1));
  });

  it("clicking update-password calls supabase.auth.updateUser({ password })", async () => {
    const supabase = makeSupabaseClient();
    const Layout = createProductLayout({ ...baseConfig(), supabase });
    renderLayout(Layout);

    fireEvent.click(screen.getByTestId("update-password-button"));

    await waitFor(() =>
      expect(supabase.auth.updateUser).toHaveBeenCalledWith({ password: "new-pass-123" }),
    );
  });

  it("clicking update-profile (no enrichment override) calls the default supabase.auth.updateUser", async () => {
    const supabase = makeSupabaseClient();
    const Layout = createProductLayout({ ...baseConfig(), supabase });
    renderLayout(Layout);

    fireEvent.click(screen.getByTestId("update-profile-button"));

    await waitFor(() =>
      expect(supabase.auth.updateUser).toHaveBeenCalledWith({
        data: { full_name: "New Name", phone: "555" },
      }),
    );
  });

  it("InactivityWarning.onExtend calls supabase.auth.refreshSession()", async () => {
    const supabase = makeSupabaseClient();
    const Layout = createProductLayout({ ...baseConfig(), supabase });
    renderLayout(Layout);

    fireEvent.click(screen.getByTestId("inactivity-extend-button"));

    await waitFor(() => expect(supabase.auth.refreshSession).toHaveBeenCalledTimes(1));
  });
});

// ── Session mode (cookie-session sibling — `sessionAuth`) ───────────────────

describe("createProductLayout — session mode (sessionAuth)", () => {
  it("renders successfully with only `sessionAuth` (no supabase client at all)", () => {
    const sessionAuth = makeSessionAuth();
    const Layout = createProductLayout({ ...baseConfig(), sessionAuth });
    renderLayout(Layout);
    expect(screen.getByTestId("child-content")).toBeInTheDocument();
  });

  it(
    "clicking logout calls sessionAuth.onLogout and NEVER touches supabase.auth.signOut " +
      "(the silent no-op bug this seam exists to prevent)",
    async () => {
      const sessionAuth = makeSessionAuth();
      // No `supabase` is passed at all — if handleLogout's branch were wrong
      // and fell through to `supabase!.auth.signOut()`, this would throw
      // (reading `.auth` off `undefined`) instead of silently no-op'ing.
      const Layout = createProductLayout({ ...baseConfig(), sessionAuth });
      renderLayout(Layout);

      fireEvent.click(screen.getByTestId("logout-button"));

      await waitFor(() => expect(sessionAuth.onLogout).toHaveBeenCalledTimes(1));
    },
  );

  it("clicking update-password calls sessionAuth.onUpdatePassword with the new password", async () => {
    const sessionAuth = makeSessionAuth();
    const Layout = createProductLayout({ ...baseConfig(), sessionAuth });
    renderLayout(Layout);

    fireEvent.click(screen.getByTestId("update-password-button"));

    await waitFor(() =>
      expect(sessionAuth.onUpdatePassword).toHaveBeenCalledWith("new-pass-123"),
    );
  });

  it("clicking update-profile (no enrichment override) calls sessionAuth.onUpdateProfile", async () => {
    const sessionAuth = makeSessionAuth();
    const Layout = createProductLayout({ ...baseConfig(), sessionAuth });
    renderLayout(Layout);

    fireEvent.click(screen.getByTestId("update-profile-button"));

    await waitFor(() =>
      expect(sessionAuth.onUpdateProfile).toHaveBeenCalledWith({
        name: "New Name",
        email: "new@example.com",
        phone: "555",
      }),
    );
  });

  it("a `useLayoutEnrichment.onUpdateProfile` override still wins over sessionAuth.onUpdateProfile", async () => {
    const sessionAuth = makeSessionAuth();
    const enrichmentOverride = vi.fn().mockResolvedValue(undefined);
    const Layout = createProductLayout({
      ...baseConfig(),
      sessionAuth,
      useLayoutEnrichment: () => ({ onUpdateProfile: enrichmentOverride }),
    });
    renderLayout(Layout);

    fireEvent.click(screen.getByTestId("update-profile-button"));

    await waitFor(() => expect(enrichmentOverride).toHaveBeenCalledTimes(1));
    expect(sessionAuth.onUpdateProfile).not.toHaveBeenCalled();
  });

  it("InactivityWarning.onExtend calls sessionAuth.onExtend", async () => {
    const sessionAuth = makeSessionAuth();
    const Layout = createProductLayout({ ...baseConfig(), sessionAuth });
    renderLayout(Layout);

    fireEvent.click(screen.getByTestId("inactivity-extend-button"));

    await waitFor(() => expect(sessionAuth.onExtend).toHaveBeenCalledTimes(1));
  });

  it("falls back to unfiltered `navGroupsFallback` when `useStatusPaginas` is omitted", () => {
    const sessionAuth = makeSessionAuth(); // no useStatusPaginas
    const Layout = createProductLayout({ ...baseConfig(), sessionAuth });
    renderLayout(Layout);

    expect(screen.getByTestId("sidebar-nav-group-count")).toHaveTextContent("1");
    expect(screen.getByTestId("sidebar-nav-item-count")).toHaveTextContent("2");
  });

  it("filters nav via `useStatusPaginas` when the product supplies one", () => {
    const sessionAuth: LayoutSessionAuth = {
      ...makeSessionAuth(),
      useStatusPaginas: () => ({
        data: [{ id: "1", nome_pagina: "dashboard", status: "producao" }],
      }),
    };
    const Layout = createProductLayout({ ...baseConfig(), sessionAuth });
    renderLayout(Layout);

    // Only "dashboard" is listed — "reports" is unlisted and therefore
    // hidden (`isPageVisible`'s documented "unlisted pages are hidden" rule).
    expect(screen.getByTestId("sidebar-nav-group-count")).toHaveTextContent("1");
    expect(screen.getByTestId("sidebar-nav-item-count")).toHaveTextContent("1");
  });

  it("prefers `sessionAuth` when BOTH `sessionAuth` and `supabase` are provided", async () => {
    const supabase = makeSupabaseClient();
    const sessionAuth = makeSessionAuth();
    const Layout = createProductLayout({ ...baseConfig(), supabase, sessionAuth });
    renderLayout(Layout);

    fireEvent.click(screen.getByTestId("logout-button"));

    await waitFor(() => expect(sessionAuth.onLogout).toHaveBeenCalledTimes(1));
    expect(supabase.auth.signOut).not.toHaveBeenCalled();
  });
});
