/**
 * The product status/deploy-scope toggles are ONE mechanism
 * (`useProductStateActions`), consumed by BOTH surfaces that render them.
 * This is a source-level wiring check (not a render test): it catches the
 * shape of regression that started this — a page re-growing its own direct
 * `/activation` or `/deploy-scope` POST instead of going through the shared
 * hook, which is exactly how the two surfaces drifted before (dashboard
 * toast vs. admin blocking `alert()`).
 */
/// <reference types="vite/client" />
// Sources come in through Vite's `?raw` import, not `node:fs`: core's tsconfig
// carries no Node types, so `node:*` imports fail `tsc --noEmit` in CI.
import { describe, it, expect } from 'vitest';
import dashboardSrc from '../pages/Dashboard.tsx?raw';
import adminProductsSrc from '../pages/admin/AdminProducts.tsx?raw';
import hookSrc from './useProductStateActions.ts?raw';

const PAGES: Array<[string, string]> = [
  ['pages/Dashboard.tsx', dashboardSrc],
  ['pages/admin/AdminProducts.tsx', adminProductsSrc],
];

const DIRECT_MUTATION_CALL = /api\.post\(\s*[`'"][^`'"]*\/(activation|deploy-scope)/;

describe('product status/deploy-scope toggles wire through the shared hook', () => {
  for (const [label, src] of PAGES) {

    it(`${label} imports useProductStateActions`, () => {
      expect(src).toMatch(/import\s*\{\s*useProductStateActions\s*\}\s*from\s*['"].*useProductStateActions['"]/);
    });

    it(`${label} has no direct /activation or /deploy-scope call outside the hook`, () => {
      expect(src).not.toMatch(DIRECT_MUTATION_CALL);
    });
  }

  it('the mutation calls actually live in the shared hook itself', () => {
    expect(hookSrc).toMatch(/\/activation/);
    expect(hookSrc).toMatch(/\/deploy-scope/);
  });
});
