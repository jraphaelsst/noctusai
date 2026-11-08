/**
 * Build-output proof (a real `vite build` into a temp dir): the PUBLIC output — everything outside the
 * privileged `_p/` directory — carries no admin route string, admin page/component name, admin nav
 * label, admin API path or internal website-doc chunk name. The privileged output is the positive control.
 */
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, readdirSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, relative, resolve } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

const FRONTEND = resolve(__dirname, '..');
let out = '';
const publicFiles: Record<string, string> = {};
const privilegedFiles: Record<string, string> = {};

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

beforeAll(() => {
  out = mkdtempSync(join(tmpdir(), 'core-build-'));
  execFileSync('npx', ['vite', 'build', '--outDir', out, '--emptyOutDir'], { cwd: FRONTEND, stdio: 'pipe', timeout: 280_000 });
  for (const f of walk(out).filter((p) => /\.(js|css|html|json|map)$/.test(p))) {
    const rel = relative(out, f);
    (rel.startsWith('_p/') ? privilegedFiles : publicFiles)[rel] = readFileSync(f, 'utf8');
  }
}, 290_000);

afterAll(() => { if (out) rmSync(out, { recursive: true, force: true }); });

const FORBIDDEN: Array<[string, RegExp]> = [
  // A string LITERAL that starts with the path (vendor code such as `${this.url}/admin/users` is not ours).
  ['an /admin path literal', /["'`]\/admin(?:[/"'`?#]|$)/],
  ['an Admin* component', /Admin[A-Z]/],
  ['FleetControl', /FleetControl/],
  ['TemplatesAdmin', /TemplatesAdmin/],
  ['the "Administração" label', /Administração/],
  ['an /api/admin/ path literal', /["'`]\/api\/admin\//],
  ['an internal website-doc chunk', /\d\d-(?:api-contract|build-plan|technical-architecture|admin-website-section)/],
  ['an admin nav label', /Fleet Control|Digest de auditoria|Modelos da plataforma|Rotinas e saúde/],
];

describe('privileged output separation (built)', () => {
  it('emits public files and a privileged _p/ directory', () => {
    expect(Object.keys(publicFiles).some((f) => /^assets\/index-.*\.js$/.test(f))).toBe(true);
    expect(Object.keys(privilegedFiles).length).toBeGreaterThan(0);
  });

  it.each(FORBIDDEN)('public output has ZERO matches for %s', (_label, re) => {
    const hits = Object.entries(publicFiles).filter(([, src]) => re.test(src)).map(([f]) => f);
    expect(hits).toEqual([]);
  });

  it('positive control: the privileged output DOES carry them', () => {
    const all = Object.values(privilegedFiles).join('\n');
    expect(all).toContain('/admin/users');
    expect(all).toContain('/admin/website/leads');
    expect(all).toContain('Fleet Control');
  });

  it('the marketing bundle is separate: some privileged file has website routes but no platform ones', () => {
    const websiteOnly = Object.values(privilegedFiles).filter(
      (s) => s.includes('/admin/website/leads') && !s.includes('/admin/users') && !s.includes('Fleet Control'),
    );
    expect(websiteOnly.length).toBeGreaterThan(0);
  });
});
