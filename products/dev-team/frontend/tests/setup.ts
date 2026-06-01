import "@testing-library/jest-dom/vitest";

// jsdom doesn't ship ResizeObserver, but recharts's `ResponsiveContainer`
// pokes at it during effect-mount. Tests that render charts only care
// about wiring (component renders without throwing) — a no-op
// ResizeObserver lets jsdom mount the chart subtree.
class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = globalThis.ResizeObserver || NoopResizeObserver;
