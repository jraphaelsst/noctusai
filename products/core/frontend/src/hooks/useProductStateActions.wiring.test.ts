/**
 * The product status/deploy-scope toggles are ONE mechanism
 * (`useProductStateActions`), consumed by BOTH surfaces that render them.
 * This is a source-level wiring check (not a render test): it catches the
 * shape of regression that started this — a page re-growing its own direct
 * `/activation` or `/deploy-scope` POST instead of going through the shared
 * hook, which is exactly how the two surfaces drifted before (dashboard
 * toast vs. admin blocking `alert()`).
 */
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it, expect } from 'vitest';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(HERE, '..');

const PAGES = [
  resolve(SRC, 'pages/Dashboard.tsx'),
  resolve(SRC, 'pages/admin/AdminProducts.tsx'),
];

const DIRECT_MUTATION_CALL = /api\.post\(\s*[`'"][^`'"]*\/(activation|deploy-scope)/;

describe('product status/deploy-scope toggles wire through the shared hook', () => {
  for (const path of PAGES) {
    const src = readFileSync(path, 'utf-8');
    const label = path.split('/src/')[1];

    it(`${label} imports useProductStateActions`, () => {
      expect(src).toMatch(/import\s*\{\s*useProductStateActions\s*\}\s*from\s*['"].*useProductStateActions['"]/);
    });

    it(`${label} has no direct /activation or /deploy-scope call outside the hook`, () => {
      expect(src).not.toMatch(DIRECT_MUTATION_CALL);
    });
  }

  it('the mutation calls actually live in the shared hook itself', () => {
    const hookSrc = readFileSync(resolve(SRC, 'hooks/useProductStateActions.ts'), 'utf-8');
    expect(hookSrc).toMatch(/\/activation/);
    expect(hookSrc).toMatch(/\/deploy-scope/);
  });
});
