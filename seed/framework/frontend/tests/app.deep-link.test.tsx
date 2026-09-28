/**
 * Deep-link-preserving login redirect (`app.tsx` `_rememberIntendedPath` /
 * `_consumeIntendedPath`).
 *
 * Before this fix, an unauthenticated visitor opening an internal URL
 * (bookmark, shared link) was bounced to Landing/Login and, after signing
 * in, ALWAYS landed on "/" — the deep link was silently discarded. The
 * fix lives in the seed route guard (`createProductApp`'s `AppContent`),
 * not per product, so every consumer inherits it.
 */
import React, { lazy } from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { createProductApp } from "../src/app";
import { mockAuthProvider } from "./fixtures";

const FakeLanding = lazy(() =>
  Promise.resolve({
    default: () => <div data-testid="landing-page">landing</div>,
  })
);

const FakeLayout: React.ComponentType<{ children: React.ReactNode }> = ({
  children,
}) => <div data-testid="app-layout">{children}</div>;

const Home = lazy(() =>
  Promise.resolve({ default: () => <div data-testid="home-page">home</div> })
);

const ClienteDetail = lazy(() =>
  Promise.resolve({
    default: () => <div data-testid="cliente-detail">cliente detail</div>,
  })
);

const INTENDED_PATH_KEY = "noctus:intended-path";

describe("createProductApp — deep-link-preserving login redirect", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("remembers a deep link hit while unauthenticated, then restores it once authenticated", async () => {
    window.history.pushState({}, "", "/clientes/123");
    const auth = mockAuthProvider({ user: null, isInitialized: true });
    const App = createProductApp({
      authProvider: auth,
      Landing: FakeLanding,
      Layout: FakeLayout,
      routes: [
        { path: "/", component: Home },
        { path: "/clientes/:id", component: ClienteDetail },
      ],
      unauthRedirect: "/",
    });

    const { rerender } = render(<App />);

    // Unauthenticated deep link → bounced to Landing at "/", and the
    // intended path is captured (not just "left in the URL" — the whole
    // point is that the product's own Login page always `navigate("/")`s
    // post-success, discarding the URL).
    expect(await screen.findByTestId("landing-page")).toBeTruthy();
    expect(window.sessionStorage.getItem(INTENDED_PATH_KEY)).toBe("/clientes/123");

    // Simulate the post-login landing spot every product's Login page (and
    // the seed's own SSOCallback) navigates to: "/".
    window.history.pushState({}, "", "/");
    auth._set({ id: "u1" }, true);
    act(() => rerender(<App />));

    expect(await screen.findByTestId("cliente-detail")).toBeTruthy();
    // Consumed — a second landing at "/" must not redirect again.
    expect(window.sessionStorage.getItem(INTENDED_PATH_KEY)).toBeNull();
  });

  it("does not remember the root path itself", async () => {
    window.history.pushState({}, "", "/");
    const auth = mockAuthProvider({ user: null, isInitialized: true });
    const App = createProductApp({
      authProvider: auth,
      Landing: FakeLanding,
      Layout: FakeLayout,
      routes: [{ path: "/", component: Home }],
      unauthRedirect: "/",
    });

    render(<App />);
    expect(await screen.findByTestId("landing-page")).toBeTruthy();
    expect(window.sessionStorage.getItem(INTENDED_PATH_KEY)).toBeNull();
  });

  it("falls back to the default redirect when nothing was remembered", async () => {
    window.history.pushState({}, "", "/");
    const auth = mockAuthProvider({ user: { id: "u1" }, isInitialized: true });
    const App = createProductApp({
      authProvider: auth,
      Layout: FakeLayout,
      routes: [{ path: "/", component: Home }],
      unauthRedirect: "/login",
    });

    render(<App />);
    expect(await screen.findByTestId("home-page")).toBeTruthy();
  });

  it("ignores a protocol-relative value (defense in depth against an open redirect)", async () => {
    window.sessionStorage.setItem(INTENDED_PATH_KEY, "//evil.example.com");
    window.history.pushState({}, "", "/");
    const auth = mockAuthProvider({ user: { id: "u1" }, isInitialized: true });
    const App = createProductApp({
      authProvider: auth,
      Layout: FakeLayout,
      routes: [{ path: "/", component: Home }],
      unauthRedirect: "/login",
    });

    render(<App />);
    // Never followed — falls through to the default "/" content instead.
    expect(await screen.findByTestId("home-page")).toBeTruthy();
  });

  it("never overrides a path the authenticated visitor already navigated to on their own", async () => {
    window.sessionStorage.setItem(INTENDED_PATH_KEY, "/clientes/123");
    window.history.pushState({}, "", "/other-page");
    const auth = mockAuthProvider({ user: { id: "u1" }, isInitialized: true });
    const App = createProductApp({
      authProvider: auth,
      Layout: FakeLayout,
      routes: [
        { path: "/", component: Home },
        { path: "/other-page", component: ClienteDetail },
        { path: "/clientes/:id", component: () => <div data-testid="should-not-render" /> },
      ],
      unauthRedirect: "/login",
    });

    render(<App />);
    expect(await screen.findByTestId("cliente-detail")).toBeTruthy();
    // The stray stored value is left alone — this path never consumes it.
    expect(window.sessionStorage.getItem(INTENDED_PATH_KEY)).toBe("/clientes/123");
  });
});
