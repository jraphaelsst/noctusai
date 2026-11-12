/**
 * SSO session lifecycle S4: the unauthenticated branch is a `ReentryGate`, and the seed-owned
 * `/login` + `/forgot-password` redirect to core's central login.
 */
import React, { lazy } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { clearLeaving, clearSessionLost, markLeaving, markSessionLost } from "@noctusai/lib";
import { createProductApp } from "../src/app";
import { goToProductLanding } from "../src/product-landing";
import { mockSupabaseAuth } from "./fixtures";

const Landing = lazy(() => Promise.resolve({ default: () => <div data-testid="landing-page">landing</div> }));
const Home = lazy(() => Promise.resolve({ default: () => <div data-testid="home-page">home</div> }));
const Clientes = lazy(() => Promise.resolve({ default: () => <div data-testid="clientes">clientes</div> }));
const Layout = ({ children }: { children: React.ReactNode }) => <div>{children}</div>;
const LegacyLogin = lazy(() => Promise.resolve({ default: () => <div data-testid="legacy-login" /> }));

const CORE = "http://localhost:8000"; // env.CORE_URL default (no VITE_CORE_URL in tests)

function setVisibility(state: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
  document.dispatchEvent(new Event("visibilitychange"));
}

function buildApp(extra: Record<string, unknown> = {}) {
  const navigate = vi.fn();
  const { supabase, useAuthStore } = mockSupabaseAuth();
  const App = createProductApp({
    supabase,
    useAuthStore,
    Landing,
    Layout,
    routes: [
      { path: "/", component: Home },
      { path: "/clientes/:id", component: Clientes },
    ],
    coreNavigate: navigate,
    ...extra,
  });
  return { App, navigate };
}

describe("createProductApp — ReentryGate (S4)", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_PRODUCT_SLUG", "demo-product");
    localStorage.clear();
    window.sessionStorage.clear();
    clearSessionLost();
    setVisibility("visible");
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
    clearSessionLost();
    setVisibility("visible");
  });

  it("fresh visit, protected path, no session -> core prompt=login with the path", async () => {
    window.history.pushState({}, "", "/clientes/7?tab=a");
    const { App, navigate } = buildApp();
    render(<App />);
    await waitFor(() => expect(navigate).toHaveBeenCalledTimes(1));
    expect(navigate).toHaveBeenCalledWith(`${CORE}/login?produto=demo-product&next=%2Fclientes%2F7%3Ftab%3Da&prompt=login`);
    expect(screen.queryByTestId("landing-page")).toBeNull();
  });

  it("fresh visit to '/' with no marker (a stranger or a crawler) shows the Landing and never bounces", async () => {
    window.history.pushState({}, "", "/");
    const { App, navigate } = buildApp();
    render(<App />);
    expect(await screen.findByTestId("landing-page")).toBeTruthy();
    expect(navigate).not.toHaveBeenCalled();
  });

  it("fresh visit to '/' with marker signed-out shows the Landing", async () => {
    localStorage.setItem("noctus:entry", "signed-out");
    window.history.pushState({}, "", "/");
    const { App, navigate } = buildApp();
    render(<App />);
    expect(await screen.findByTestId("landing-page")).toBeTruthy();
    expect(navigate).not.toHaveBeenCalled();
  });

  it.each(["left", "active"])("fresh visit to '/' with marker %s -> core prompt=none", async (marker) => {
    localStorage.setItem("noctus:entry", marker);
    window.history.pushState({}, "", "/");
    const { App, navigate } = buildApp();
    render(<App />);
    await waitFor(() => expect(navigate).toHaveBeenCalledTimes(1));
    expect(navigate).toHaveBeenCalledWith(`${CORE}/login?produto=demo-product&prompt=none`);
  });

  it("a tab that lost its session (marker active) waits for visibility, then goes to core prompt=login keeping the path", async () => {
    localStorage.setItem("noctus:entry", "active");
    window.history.pushState({}, "", "/clientes/9");
    markSessionLost();
    setVisibility("hidden");
    const { App, navigate } = buildApp();
    render(<App />);
    // hidden: settle delay elapses, still nothing
    await new Promise((r) => setTimeout(r, 400));
    expect(navigate).not.toHaveBeenCalled();
    setVisibility("visible");
    await waitFor(() => expect(navigate).toHaveBeenCalledTimes(1));
    expect(navigate).toHaveBeenCalledWith(`${CORE}/login?produto=demo-product&next=%2Fclientes%2F9&prompt=login`);
  });

  it("Voltar: THIS tab (leaving for core) never bounces itself back through core's login", async () => {
    localStorage.setItem("noctus:entry", "left");
    window.history.pushState({}, "", "/clientes/9");
    markLeaving();
    markSessionLost();
    try {
      const { App, navigate } = buildApp();
      render(<App />);
      await new Promise((r) => setTimeout(r, 400));
      expect(navigate).not.toHaveBeenCalled();
      expect(screen.queryByTestId("landing-page")).toBeNull();
    } finally {
      clearLeaving();
    }
  });

  it("Voltar: a SIBLING tab (session lost, marker left) re-enters through core prompt=login keeping its path", async () => {
    localStorage.setItem("noctus:entry", "left");
    window.history.pushState({}, "", "/clientes/9");
    markSessionLost();
    const { App, navigate } = buildApp();
    render(<App />);
    await waitFor(() => expect(navigate).toHaveBeenCalledTimes(1));
    expect(navigate).toHaveBeenCalledWith(`${CORE}/login?produto=demo-product&next=%2Fclientes%2F9&prompt=login`);
  });

  it("Sair: the other tab (session lost, marker signed-out) goes to '/' (Landing), not to core", async () => {
    window.history.pushState({}, "", "/clientes/9");
    localStorage.setItem("noctus:entry", "active");
    // Tab 1 clicks Sair -> marker signed-out (shared storage) ...
    goToProductLanding(vi.fn());
    // ... tab 2 receives the confirmed SIGNED_OUT.
    markSessionLost();
    const { App, navigate } = buildApp();
    render(<App />);
    expect(await screen.findByTestId("landing-page")).toBeTruthy();
    expect(window.location.pathname).toBe("/");
    expect(navigate).not.toHaveBeenCalled();
  });

  it("#sso=login_required shows the Landing, sets signed-out, strips the fragment, no error and no round trip", async () => {
    localStorage.setItem("noctus:entry", "left");
    window.history.pushState({}, "", "/#sso=login_required");
    const { App, navigate } = buildApp();
    render(<App />);
    expect(await screen.findByTestId("landing-page")).toBeTruthy();
    expect(localStorage.getItem("noctus:entry")).toBe("signed-out");
    expect(window.location.hash).toBe("");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(navigate).not.toHaveBeenCalled();
  });

  it("loop guard: after 3 round trips in 2 min the gate stops and offers 'Entrar'", async () => {
    localStorage.setItem("noctus:entry", "active");
    const now = Date.now();
    window.sessionStorage.setItem("noctus:reentry-trips", JSON.stringify([now - 30_000, now - 20_000, now - 10_000]));
    window.history.pushState({}, "", "/");
    const { App, navigate } = buildApp();
    render(<App />);
    const entrar = await screen.findByRole("link", { name: "Entrar" });
    expect(entrar.getAttribute("href")).toBe(`${CORE}/login?produto=demo-product&prompt=login`);
    expect(navigate).not.toHaveBeenCalled();
  });

  it("two mounts (two visible tabs) -> one navigation while the 60 s inflight stamp is fresh", async () => {
    localStorage.setItem("noctus:entry", "active");
    window.history.pushState({}, "", "/");
    const { App, navigate } = buildApp();
    const a = render(<App />);
    await waitFor(() => expect(navigate).toHaveBeenCalledTimes(1));
    a.unmount();
    const b = render(<App />);
    await new Promise((r) => setTimeout(r, 100));
    expect(navigate).toHaveBeenCalledTimes(1);
    b.unmount();
  });
});

describe("createProductApp — seed-owned /login and /forgot-password (S4)", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_PRODUCT_SLUG", "demo-product");
    window.sessionStorage.clear();
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("/login goes to the core URL with the slug and a path-only next", async () => {
    window.history.pushState({}, "", "/login?next=/clientes/3");
    const { App, navigate } = buildApp();
    render(<App />);
    await waitFor(() => expect(navigate).toHaveBeenCalledTimes(1));
    expect(navigate).toHaveBeenCalledWith(`${CORE}/login?produto=demo-product&next=%2Fclientes%2F3`);
  });

  it.each(["//evil.example/x", "https://evil.example"])("/login drops a non-path next (%s)", async (bad) => {
    window.history.pushState({}, "", `/login?next=${encodeURIComponent(bad)}`);
    const { App, navigate } = buildApp();
    render(<App />);
    await waitFor(() => expect(navigate).toHaveBeenCalledTimes(1));
    expect(navigate).toHaveBeenCalledWith(`${CORE}/login?produto=demo-product`);
  });

  it("/login with no next uses the remembered deep link", async () => {
    window.sessionStorage.setItem("noctus:intended-path", "/clientes/5");
    window.history.pushState({}, "", "/login");
    const { App, navigate } = buildApp();
    render(<App />);
    await waitFor(() => expect(navigate).toHaveBeenCalledTimes(1));
    expect(navigate).toHaveBeenCalledWith(`${CORE}/login?produto=demo-product&next=%2Fclientes%2F5`);
  });

  it("/forgot-password goes to core's /esqueci-senha", async () => {
    window.history.pushState({}, "", "/forgot-password");
    const { App, navigate } = buildApp();
    render(<App />);
    await waitFor(() => expect(navigate).toHaveBeenCalledTimes(1));
    expect(navigate).toHaveBeenCalledWith(`${CORE}/esqueci-senha?produto=demo-product`);
  });

  it("the deprecated Login/ForgotPassword props are accepted, warn naming S6, and are not mounted", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    window.history.pushState({}, "", "/login");
    const { App, navigate } = buildApp({ Login: LegacyLogin, ForgotPassword: LegacyLogin });
    render(<App />);
    await waitFor(() => expect(navigate).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId("legacy-login")).toBeNull();
    expect(warn.mock.calls.filter((c) => String(c[0]).includes("S6")).length).toBe(2);
  });
});
