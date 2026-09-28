/**
 * Vitest setup — registers @testing-library/jest-dom's matchers
 * (e.g. `toBeInTheDocument()`) on vitest's `expect` so component
 * tests can use them idiomatically.
 */
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";

// jsdom's `window` (and therefore `sessionStorage`) persists across every
// test WITHIN one test file (vitest isolates per file, not per test) — a
// test that writes to `sessionStorage` (e.g. `createProductApp`'s deep-link
// memory) would otherwise leak into the next test in the same file/describe
// block. Clearing after every test matches real-browser reality (a fresh
// tab never carries a prior test's storage) with zero risk to product code.
afterEach(() => {
  window.sessionStorage.clear();
});
