/**
 * Shared Vitest setup — runs ONCE before every product test module (wired via
 * `createProductVitestConfig`'s `setupFiles`). Because it runs before any test
 * file's imports, browser globals are in place before a module-scope store
 * (e.g. a zustand `persist` store) is constructed at import time.
 *
 * WHY this exists: vitest's `jsdom` environment does NOT provide a working
 * `localStorage` / `sessionStorage`. Any consumer of browser storage (zustand
 * `persist`, feature flags, draft caches) would otherwise throw
 * "storage.setItem is not a function" — which previously forced each test file
 * to re-polyfill `localStorage` by hand (a workaround that also raced the
 * import-time store construction). Provisioned here ONCE so no test re-does it.
 *
 * Idempotent + non-destructive: only installs the shim when the global is
 * absent or incomplete, so a real DOM env (or a test that supplies its own)
 * is left untouched.
 */
function createStorageShim(): Storage {
  let data: Record<string, string> = {};
  return {
    getItem: (key: string) => (key in data ? data[key] : null),
    setItem: (key: string, value: string) => {
      data[key] = String(value);
    },
    removeItem: (key: string) => {
      delete data[key];
    },
    clear: () => {
      data = {};
    },
    key: (index: number) => Object.keys(data)[index] ?? null,
    get length() {
      return Object.keys(data).length;
    },
  } as Storage;
}

function ensureStorage(name: "localStorage" | "sessionStorage"): void {
  const current = (globalThis as Record<string, unknown>)[name] as
    | Storage
    | undefined;
  const usable = current && typeof current.setItem === "function";
  if (!usable) {
    Object.defineProperty(globalThis, name, {
      value: createStorageShim(),
      writable: true,
      configurable: true,
    });
  }
}

ensureStorage("localStorage");
ensureStorage("sessionStorage");
