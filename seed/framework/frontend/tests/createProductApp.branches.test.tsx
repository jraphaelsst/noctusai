/**
 * Tests that `createProductApp` selects the correct auth wiring at
 * construction time based on which config fields are present:
 *   - `authProvider` present  → custom path (core)
 *   - `supabase + useAuthStore` present → default Supabase path
 *
 * We verify by checking that the returned App component can be rendered
 * without errors in each configuration. The full routing surface is
 * exercised separately in `createProductApp.routes.test.tsx`.
 */
import React from "react";
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { createProductApp } from "../src/app";
import { mockSupabaseAuth, mockAuthProvider } from "./fixtures";

describe("createProductApp — auth branch selection", () => {
  it("builds an App when given supabase + useAuthStore (default branch)", () => {
    const { supabase, useAuthStore } = mockSupabaseAuth();
    const App = createProductApp({
      supabase,
      useAuthStore,
    });
    // Rendering should not throw — the default branch wires
    // createAuthProvider(supabase, useAuthStore) internally.
    const { container } = render(<App />);
    expect(container).toBeTruthy();
  });

  it("builds an App when given a custom authProvider (control-plane branch)", () => {
    const auth = mockAuthProvider({ user: null, isInitialized: true });
    const App = createProductApp({
      authProvider: auth,
      unauthRedirect: "/login",
    });
    const { container } = render(<App />);
    expect(container).toBeTruthy();
  });

  it("prefers authProvider when BOTH authProvider AND supabase are provided", () => {
    // The custom AuthProvider records whether it was rendered; if the
    // framework picked the Supabase path by accident, this wouldn't fire.
    let customRendered = false;
    const auth: ReturnType<typeof mockAuthProvider> = {
      AuthProvider: ({ children }) => {
        customRendered = true;
        return <>{children}</>;
      },
      useAuth: () => ({ user: null, isInitialized: true }),
      _set: () => {},
    };
    const { supabase, useAuthStore } = mockSupabaseAuth();
    const App = createProductApp({
      authProvider: auth,
      // @ts-expect-error — supplying both to prove authProvider wins.
      supabase,
      useAuthStore,
    });
    render(<App />);
    expect(customRendered).toBe(true);
  });
});
