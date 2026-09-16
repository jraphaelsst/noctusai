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
 * Also `ResizeObserver`, which jsdom does not implement at all: every Radix
 * primitive that measures itself (Switch thumb, Checkbox indicator, Popover)
 * calls it on mount, so a product test that renders a real one crashed with
 * `ResizeObserver is not defined` — and each file re-declared its own no-op
 * class (N=3 by 2026-09-16: Settings, Referencias, GuiasEstilo). A no-op is
 * the correct stand-in: jsdom has no layout, so there is nothing to observe.
 * A test that needs real size callbacks (recharts) installs its own stub,
 * which this leaves in place.
 *
 * Idempotent + non-destructive: only installs a shim when the global is
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


function ensureResizeObserver(): void {
  if (typeof (globalThis as Record<string, unknown>).ResizeObserver === "function") return;
  class NoopResizeObserver {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  Object.defineProperty(globalThis, "ResizeObserver", {
    value: NoopResizeObserver,
    writable: true,
    configurable: true,
  });
}

ensureResizeObserver();
