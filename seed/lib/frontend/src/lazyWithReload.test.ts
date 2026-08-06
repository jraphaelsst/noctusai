/**
 * Tests for `lazyWithReload` — stale-chunk recovery after a mid-session deploy.
 *
 * The incident (2026-08-05): "Base de Leads" showed "Algo deu errado" on a
 * phone while every sibling tab worked and desktop was fine. 23 production
 * deploys landed that day; each re-hashes every lazy chunk filename, so a
 * browser holding the previous `index.html` asks for files the server has
 * already deleted.
 *
 * These assert BEHAVIOUR, not implementation: recover from a stale chunk, and
 * — the part that matters more — never turn a persistent failure into a boot
 * loop the user cannot escape.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const STALE = new Error(
  "Failed to fetch dynamically imported module: /assets/BaseDeLeads-a1b2c3.js",
);

let reloadCalls = 0;

beforeEach(() => {
  reloadCalls = 0;
  sessionStorage.clear();
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { reload: () => { reloadCalls += 1; } },
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

/** Drive the factory the way React.lazy does, without rendering. */
async function runFactory(mod: any) {
  // React.lazy stores the thunk on `_payload._result` in dev builds; calling
  // it directly is the stable way to exercise the logic in a unit test.
  const payload = (mod as any)._payload;
  return payload._result();
}

describe("lazyWithReload", () => {
  it("returns the module when the import succeeds", async () => {
    const { lazyWithReload } = await import("./lazyWithReload");
    const Comp = () => null;
    const mod = lazyWithReload(async () => ({ default: Comp }));
    await expect(runFactory(mod)).resolves.toEqual({ default: Comp });
    expect(reloadCalls).toBe(0);
  });

  it("retries once before giving up — a dropped request is not a stale deploy", async () => {
    const { lazyWithReload } = await import("./lazyWithReload");
    const Comp = () => null;
    let calls = 0;
    const mod = lazyWithReload(async () => {
      calls += 1;
      if (calls === 1) throw STALE;
      return { default: Comp };
    });
    await expect(runFactory(mod)).resolves.toEqual({ default: Comp });
    expect(calls).toBe(2);
    expect(reloadCalls).toBe(0);   // the retry succeeded; no reload needed
  });

  it("reloads once when the chunk is genuinely gone", async () => {
    const { lazyWithReload } = await import("./lazyWithReload");
    const mod = lazyWithReload(async () => { throw STALE; });
    // Never resolves — the page is being torn down by the reload.
    const pending = runFactory(mod);
    await Promise.race([pending, new Promise((r) => setTimeout(r, 20))]);
    expect(reloadCalls).toBe(1);
    expect(sessionStorage.getItem("noc:chunk-reload")).toBe("1");
  });

  it("🔴 NEVER reloads twice — a boot loop is worse than the error screen", async () => {
    const { lazyWithReload } = await import("./lazyWithReload");
    sessionStorage.setItem("noc:chunk-reload", "1");   // a reload already happened
    const mod = lazyWithReload(async () => { throw STALE; });
    await expect(runFactory(mod)).rejects.toThrow(/dynamically imported/);
    expect(reloadCalls).toBe(0);   // surfaces to the ErrorBoundary instead
  });

  it("clears the guard on success so a LATER deploy can recover too", async () => {
    const { lazyWithReload } = await import("./lazyWithReload");
    sessionStorage.setItem("noc:chunk-reload", "1");
    const mod = lazyWithReload(async () => ({ default: () => null }));
    await runFactory(mod);
    expect(sessionStorage.getItem("noc:chunk-reload")).toBeNull();
  });

  it("🔴 re-throws a REAL component error untouched — never masks a bug with a reload", async () => {
    const { lazyWithReload } = await import("./lazyWithReload");
    const bug = new TypeError("Cannot read properties of undefined (reading 'map')");
    const mod = lazyWithReload(async () => { throw bug; });
    await expect(runFactory(mod)).rejects.toThrow(bug);
    expect(reloadCalls).toBe(0);
  });

  it("recognises the wording each engine uses", async () => {
    const { lazyWithReload } = await import("./lazyWithReload");
    // Safari and Chrome phrase this differently; matching only one engine's
    // string would leave the other's users stuck on the error screen.
    for (const message of [
      "Importing a module script failed.",                       // Safari
      "error loading dynamically imported module",               // Firefox
      "ChunkLoadError: Loading chunk 42 failed",                 // webpack-era
    ]) {
      sessionStorage.clear();
      reloadCalls = 0;
      const mod = lazyWithReload(async () => { throw new Error(message); });
      await Promise.race([runFactory(mod), new Promise((r) => setTimeout(r, 20))]);
      expect(reloadCalls, `not recognised: ${message}`).toBe(1);
    }
  });
});
