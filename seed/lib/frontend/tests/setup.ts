/**
 * Vitest setup — registers @testing-library/jest-dom matchers
 * (e.g. `toBeInTheDocument()`) on vitest's `expect` so component
 * tests can use them idiomatically.
 *
 * Mirrors `seed/framework/frontend/tests/setup.ts`.
 */
import "@testing-library/jest-dom/vitest";
