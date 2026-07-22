/**
 * Test-only helper (NOT exported from `index.ts`, NOT shipped code) that
 * makes recharts' `ResponsiveContainer` measure a non-zero size under jsdom.
 *
 * jsdom does no real layout: `getBoundingClientRect()` / `offsetWidth` /
 * `offsetHeight` default to 0, and `ResizeObserver` doesn't exist at all.
 * recharts v2's `ResponsiveContainer` measures its container on mount and
 * REFUSES to render its children (silently, via a `console.error` warning
 * only) when the measured size is 0×0 — a SEPARATE gap from the
 * dual-React-instance issue already fixed for `seed/lib/frontend`'s vitest
 * harness (see `reference_lib_frontend_vitest_render_harness_gap`). This
 * file is the local, scoped fix for the recharts-specific half of that gap,
 * applied only to this slice's own colocated tests — not the shared
 * `tests/setup.ts` (kept file-disjoint from other slices touching this repo).
 *
 * Usage: call once in a `beforeAll()` in any test file that renders a
 * recharts-based chart wrapper (LineChart/AreaChart/BarChart/DonutChart).
 */
export function mockRechartsLayout(width = 500, height = 280): void {
  class StubResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  globalThis.ResizeObserver = StubResizeObserver as unknown as typeof ResizeObserver;

  Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
    configurable: true,
    value: () => ({
      width,
      height,
      top: 0,
      left: 0,
      bottom: height,
      right: width,
      x: 0,
      y: 0,
      toJSON() {},
    }),
  });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, value: width });
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", { configurable: true, value: height });
}
