/**
 * `createProductApp` must bind the SSO redemption to THIS product's audience:
 * the `/sso` route passes `productSlug` (VITE_PRODUCT_SLUG, injected by
 * createViteConfig) to SSOCallback, and an empty slug fails loudly.
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { createProductApp } from "../src/app";
import { mockSupabaseAuth } from "./fixtures";

describe("createProductApp — SSO audience binding", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("sends product_slug in the /sso redeem body", async () => {
    vi.stubEnv("VITE_PRODUCT_SLUG", "demo-product");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      headers: new Headers(),
      json: async () => ({ detail: "nope" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    window.history.replaceState({}, "", "/sso#token=abc.def.ghi");

    const { supabase, useAuthStore } = mockSupabaseAuth();
    const App = createProductApp({ supabase, useAuthStore, routes: [], unauthRedirect: "/login" });
    render(<App />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body).toEqual({ token: "abc.def.ghi", product_slug: "demo-product" });
  });

  it("fails loudly (console.error) when the product slug is not derivable", () => {
    vi.stubEnv("VITE_PRODUCT_SLUG", "");
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    const { supabase, useAuthStore } = mockSupabaseAuth();
    createProductApp({ supabase, useAuthStore, routes: [], unauthRedirect: "/login" });
    expect(err.mock.calls.some((c) => String(c[0]).includes("VITE_PRODUCT_SLUG"))).toBe(true);
  });
});
