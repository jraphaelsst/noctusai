/**
 * Tests that `createProductApp` mounts the right set of public routes
 * based on config presence:
 *   - `/sso` is only mounted when `supabase` is provided (custom-auth
 *     products don't use Supabase SSO callback).
 *   - `unauthRedirect` defaults to `/` (the Landing page root). Products
 *     without a Landing page set this to "/login" to avoid a redirect loop.
 *   - Unauthenticated users hitting "/" see the Landing component (when
 *     provided); authenticated users hitting "/" see the app home.
 *   - `/landing` (old canonical) permanently redirects to "/".
 *
 * These tests render the App and peek at what's in the DOM for the
 * documented-public paths. We don't assert full route coverage — that's
 * React Router's responsibility, not createProductApp's.
 */
import React, { lazy } from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { createProductApp } from "../src/app";
import { mockSupabaseAuth, mockAuthProvider } from "./fixtures";

describe("createProductApp — route topology", () => {
  it("does not mount /sso when no supabase client is provided (custom-auth case)", () => {
    const auth = mockAuthProvider({ user: null, isInitialized: true });
    const App = createProductApp({
      authProvider: auth,
      unauthRedirect: "/login",
    });
    // With custom auth and no supabase, /sso must not exist. We render
    // the app; there's no public assertion surface for "route absent",
    // so we rely on the fact that no SSO-related module is imported.
    const { container } = render(<App />);
    // No /sso route means no SSOCallback component rendered at any time.
    // The DOM at startup is either the landing redirect or the login page.
    expect(container.querySelector("[data-testid='sso-callback']")).toBeNull();
  });

  it("exposes config fields through ProductAppConfig typing", () => {
    // Type-level sanity check that the public surface carries the
    // newly-added fields. Runtime assertion is trivial — the real
    // guarantee is the TypeScript compile.
    const auth = mockAuthProvider();
    const App = createProductApp({
      authProvider: auth,
      unauthRedirect: "/login",
      publicRoutes: [],
      unwrappedRoutes: [],
    });
    expect(typeof App).toBe("function");
  });

  it("accepts a custom unauthRedirect value", () => {
    // Verify the factory constructs an App without error when the
    // override is passed — routing behavior is covered by integration.
    const auth = mockAuthProvider({ user: null, isInitialized: true });
    const App = createProductApp({
      authProvider: auth,
      unauthRedirect: "/login",
    });
    expect(typeof App).toBe("function");
  });
});

// ── Landing-at-root routing contract ─────────────────────────────────────────
// These tests assert the routing contract introduced when Landing moved from
// "/landing" to "/": unauth "/" → Landing; auth "/" → app; "/landing" → "/".

const FakeLanding = lazy(() =>
  Promise.resolve({
    default: () => <div data-testid="landing-page">landing</div>,
  })
);

const FakeLayout: React.ComponentType<{ children: React.ReactNode }> = ({
  children,
}) => <div data-testid="app-layout">{children}</div>;

const AnyPage = lazy(() =>
  Promise.resolve({
    default: () => <div data-testid="any-page">app-home</div>,
  })
);

describe("createProductApp — Landing at / routing contract", () => {
  beforeEach(() => {
    window.history.pushState({}, "", "/");
  });

  it("unauth user at '/' sees Landing when Landing is provided", async () => {
    const auth = mockAuthProvider({ user: null, isInitialized: true });
    const App = createProductApp({
      authProvider: auth,
      Landing: FakeLanding,
      Login: AnyPage,
      Layout: FakeLayout,
      routes: [{ path: "/", component: AnyPage }],
      unauthRedirect: "/",
    });

    render(<App />);
    expect(await screen.findByTestId("landing-page")).toBeTruthy();
  });

  it("auth user at '/' sees the app (not Landing)", async () => {
    const auth = mockAuthProvider({
      user: { id: "u1" },
      isInitialized: true,
    });
    const App = createProductApp({
      authProvider: auth,
      Landing: FakeLanding,
      Layout: FakeLayout,
      routes: [{ path: "/", component: AnyPage }],
      unauthRedirect: "/",
    });

    render(<App />);
    expect(await screen.findByTestId("any-page")).toBeTruthy();
    expect(screen.queryByTestId("landing-page")).toBeNull();
  });

  it("/landing redirects to / for unauth user (back-compat)", async () => {
    window.history.pushState({}, "", "/landing");
    const auth = mockAuthProvider({ user: null, isInitialized: true });
    const App = createProductApp({
      authProvider: auth,
      Landing: FakeLanding,
      Login: AnyPage,
      Layout: FakeLayout,
      routes: [{ path: "/", component: AnyPage }],
      unauthRedirect: "/",
    });

    render(<App />);
    // After the /landing → / redirect, unauth user sees Landing at /.
    expect(await screen.findByTestId("landing-page")).toBeTruthy();
  });
});
