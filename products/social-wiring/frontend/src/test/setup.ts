/**
 * Social-wiring vitest setup — layered ON TOP of the shared seed setup
 * (`createProductVitestConfig`'s `setupFilesExtra`).
 *
 * jsdom Pointer Events polyfill, aligned with `seed/lib/frontend/tests/setup.ts`
 * (card-hub wave-a Slice F). Radix UI's pointer-driven primitives (Select, and
 * any future Combobox/Slider/etc.) call `target.hasPointerCapture` /
 * `setPointerCapture` / `releasePointerCapture` on pointerdown, and
 * `scrollIntoView` when auto-scrolling a highlighted item into view. jsdom does
 * not implement the Pointer Events API, so without these no-op stubs Radix
 * throws `TypeError: target.hasPointerCapture is not a function` on the first
 * `userEvent.click` of a trigger. That is a known jsdom gap, not a defect in the
 * component under test. With the stubs, SW suites can exercise the REAL seed
 * Radix `Select` (e.g. the seed `AnexosSection` tipo picker) instead of mocking
 * `@/components/ui/select`.
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
