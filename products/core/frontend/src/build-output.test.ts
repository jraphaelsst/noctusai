/**
 * Build-output proof: the MAIN entry chunk (and what it statically preloads) carries no admin route
 * string, admin page component or admin nav label. Runs a real `vite build` into a temp dir.
 */
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

const FRONTEND = resolve(__dirname, '..');
let out = '';
let mainChunks: string[] = [];
let allChunks: Record<string, string> = {};

beforeAll(() => {
  out = mkdtempSync(join(tmpdir(), 'core-build-'));
  execFileSync('npx', ['vite', 'build', '--outDir', out, '--emptyOutDir'], { cwd: FRONTEND, stdio: 'pipe', timeout: 280_000 });
  const html = readFileSync(join(out, 'index.html'), 'utf8');
  const refs = [...html.matchAll(/(?:src|href)="\/?(assets\/[^"]+\.js)"/g)].map((m) => m[1]);
  mainChunks = [...new Set(refs)];
  for (const f of readdirSync(join(out, 'assets')).filter((n) => n.endsWith('.js'))) {
    allChunks[`assets/${f}`] = readFileSync(join(out, 'assets', f), 'utf8');
  }
}, 290_000);

afterAll(() => { if (out) rmSync(out, { recursive: true, force: true }); });

const ADMIN_PATH = /["'`]\/admin(?:["'`/])/;
const ADMIN_LABELS = ['Fleet Control', 'Digest de auditoria', 'Modelos da plataforma', 'AdminDashboard', 'Rotinas e saúde'];

describe('admin code-splitting (built output)', () => {
  it('finds the main entry chunk', () => {
    expect(mainChunks.length).toBeGreaterThan(0);
  });

  it('keeps every admin path string and nav label out of the main entry + its static preloads', () => {
    for (const f of mainChunks) {
      const src = allChunks[f];
      expect(src, f).toBeDefined();
      expect(ADMIN_PATH.test(src), `${f} carries an /admin path string`).toBe(false);
      for (const label of ADMIN_LABELS) expect(src.includes(label), `${f} carries "${label}"`).toBe(false);
    }
  });

  it('is not vacuous: the admin paths and labels DO ship, in a lazy chunk', () => {
    const adminChunks = Object.entries(allChunks).filter(([f]) => !mainChunks.includes(f));
    expect(adminChunks.some(([, s]) => s.includes('/admin/funil'))).toBe(true);
    expect(adminChunks.some(([, s]) => s.includes('Fleet Control'))).toBe(true);
  });
});
