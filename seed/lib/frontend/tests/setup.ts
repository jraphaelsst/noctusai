/**
 * Vitest setup — registers @testing-library/jest-dom matchers
 * (e.g. `toBeInTheDocument()`) on vitest's `expect` so component
 * tests can use them idiomatically.
 *
 * Uses the default `@testing-library/jest-dom` entry (index.mjs) rather than
 * the vitest-specific entrypoint. The reason: `@testing-library/jest-dom/vitest`
 * does `import { expect } from 'vitest'` which resolves from jest-dom's own
 * node_modules, potentially finding a different vitest copy than the running
 * test runner — causing "Invalid Chai property: toBeInTheDocument" when the two
 * vitest instances diverge (e.g. when using the framework's vitest binary to run
 * lib tests). The default `index.mjs` entry instead calls `expect.extend(extensions)`
 * on globalThis.expect, which is always the running test framework's expect
 * (vitest injects it as a global when `globals: true`).
 *
 * Mirrors `seed/framework/frontend/tests/setup.ts` pattern.
 */
import "@testing-library/jest-dom";

/**
 * jsdom Pointer Events polyfill — Radix UI's pointer-driven primitives
 * (Select, and any future Combobox/Slider/etc.) call
 * `target.hasPointerCapture` / `setPointerCapture` / `releasePointerCapture`
 * on pointerdown, and `scrollIntoView` when auto-scrolling a highlighted
 * item into view. jsdom does not implement the Pointer Events API, so these
 * are undefined and Radix throws `TypeError: target.hasPointerCapture is
 * not a function` on the first `userEvent.click` of a trigger — this is
 * jsdom's known gap (documented by Radix itself), not a defect in the
 * component under test. No-op stubs are the standard fix.
 */
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => {};
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => {};
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
