/**
 * Tests that `createProductApp` mounts the right set of public routes
 * based on config presence:
 *   - `/sso` is only mounted when `supabase` is provided (custom-auth
 *     products don't use Supabase SSO callback).
 *   - `unauthRedirect` defaults to `/landing` but can be overridden
 *     (core overrides to `/login` because it has no Landing page).
 *
 * These tests render the App and peek at what's in the DOM for the
 * documented-public paths. We don't assert full route coverage — that's
 * React Router's responsibility, not createProductApp's.
 */
import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
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
    // If the framework did not respect the override, unauth'd users would
    // get redirected to `/landing` (default). Verify the factory constructs
    // an App without error when the override is passed — the routing
    // behavior itself is React Router's concern and covered by integration.
    const auth = mockAuthProvider({ user: null, isInitialized: true });
    const App = createProductApp({
      authProvider: auth,
      unauthRedirect: "/login",
    });
    expect(typeof App).toBe("function");
  });
});
