import { render, screen, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const apiGet = vi.fn();
const coreGet = vi.fn();
vi.mock('@noctusai/seed/infra', () => ({
  api: { get: (...a: unknown[]) => apiGet(...a) },
  coreApi: { get: (...a: unknown[]) => coreGet(...a) },
}));

import { BrandProvider, useBrand } from './BrandProvider';
import { buildBrandCss, googleFontsHref, safeAssetUrl, sanitizeTokens } from './brand-tokens';

// The token key list is DERIVED from tokens.css (never hand-maintained).
const css = readFileSync(resolve(__dirname, 'tokens.css'), 'utf8');
const rootBlock = css.slice(css.indexOf(':root'), css.indexOf('.dark'));
const KEYS = [...rootBlock.matchAll(/^\s*--([a-z0-9-]+):\s*(\d{1,3}(?:\.\d+)? \d{1,3}(?:\.\d+)?% \d{1,3}(?:\.\d+)?%);/gm)]
  .map((m) => m[1]);

const accessOf = (id: string) => ({ has_access: true, product_slug: 'p', org: { id, nome: id } });
const brandOf = (primary: string, source: 'org' | 'platform' = 'org') => ({
  source, identity_id: 'i1', version: 1, updated_at: null,
  tokens: {
    light: { primary }, dark: { primary: '10 50% 40%' }, radius: '1rem',
    fonts: { heading: { family: 'Cormorant Garamond', weights: [500, 600], source: 'google' } },
  },
  assets: { logo_light: 'https://s.example/logo.png', favicon: 'https://s.example/f.png', logo_dark: null, logo_mark: null },
});

function Probe() {
  const b = useBrand();
  return <div data-testid="p" data-source={b.source} data-loading={String(b.isLoading)}>{b.logo.light ?? 'none'}</div>;
}
function mount(qc = new QueryClient({ defaultOptions: { queries: { retry: false } } }), authenticated = true) {
  return render(
    <QueryClientProvider client={qc}><BrandProvider authenticated={authenticated}><Probe /></BrandProvider></QueryClientProvider>,
  );
}
const styleText = () => document.getElementById('noc-brand-tokens')?.textContent ?? '';

beforeEach(() => { apiGet.mockReset(); coreGet.mockReset(); window.localStorage.clear(); });
afterEach(() => { cleanup(); document.head.innerHTML = ''; });

describe('brand-tokens validation (CSS injection guard)', () => {
  it('derives a non-trivial key list from tokens.css and accepts every one', () => {
    expect(KEYS.length).toBeGreaterThan(40);
    expect(KEYS).toContain('primary');
    const light = Object.fromEntries(KEYS.map((k) => [k, '210 40% 50%']));
    expect(Object.keys(sanitizeTokens({ light }).light).sort()).toEqual([...KEYS].sort());
  });
  it('drops anything off-regex instead of repairing it', () => {
    const t = sanitizeTokens({
      light: { primary: '0 0% 0%; } body{display:none', 'bad key;': '1 1% 1%', ok: '1 1% 1%', url: 'url(x)' },
      radius: '1rem; x', fonts: { heading: { family: 'Evil";}x', weights: [400] }, body: { family: 'Lora', weights: [400, 'a', 99999], source: 'google' } },
    });
    expect(t.light).toEqual({ ok: '1 1% 1%' });
    expect(t.radius).toBeNull();
    expect(t.fonts.heading).toBeUndefined();
    expect(t.fonts.body).toEqual({ family: 'Lora', weights: [400], source: 'google' });
    expect(buildBrandCss(t)).not.toMatch(/display|url\(|\}x/);
  });
  it('builds :root then .dark and a google href from validated fonts', () => {
    const t = sanitizeTokens(brandOf('1 2% 3%').tokens);
    expect(buildBrandCss(t)).toBe(':root{--primary:1 2% 3%;--radius:1rem;--font-heading:"Cormorant Garamond",system-ui,sans-serif;}.dark{--primary:10 50% 40%;}');
    expect(googleFontsHref(t)).toBe('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600&display=swap');
  });
  it('only lets https or same-origin relative asset urls through', () => {
    expect(safeAssetUrl('https://x/y.png')).toBe('https://x/y.png');
    expect(safeAssetUrl('/a.png')).toBe('/a.png');
    for (const bad of ['javascript:alert(1)', '//evil.com/x', 'http://x', 'data:text/html,x', 'https://x/"onload=']) expect(safeAssetUrl(bad)).toBeNull();
  });
});

describe('BrandProvider', () => {
  it('fetches via coreApi once access answers, applies tokens, favicon and exposes the logo', async () => {
    apiGet.mockResolvedValue(accessOf('org-a'));
    coreGet.mockResolvedValue(brandOf('11 22% 33%'));
    mount();
    await waitFor(() => expect(styleText()).toContain('--primary:11 22% 33%;'));
    expect(coreGet).toHaveBeenCalledWith('/api/brand/current');
    expect(screen.getByTestId('p').textContent).toBe('https://s.example/logo.png');
    expect(screen.getByTestId('p').dataset.source).toBe('org');
    expect((document.getElementById('noc-brand-favicon') as HTMLLinkElement).href).toBe('https://s.example/f.png');
    expect(document.getElementById('noc-brand-google-fonts')).not.toBeNull();
    expect(JSON.parse(window.localStorage.getItem('noc:brand:org-a')!).light.primary).toBe('11 22% 33%');
  });

  it('never fetches while unauthenticated', async () => {
    mount(undefined, false);
    await new Promise((r) => setTimeout(r, 20));
    expect(apiGet).not.toHaveBeenCalled();
    expect(coreGet).not.toHaveBeenCalled();
  });

  it('applies the last org cache synchronously at boot (no flash) before any fetch answers', () => {
    window.localStorage.setItem('noc:brand:last-org', 'org-a');
    window.localStorage.setItem('noc:brand:org-a', JSON.stringify(sanitizeTokens(brandOf('7 8% 9%').tokens)));
    apiGet.mockReturnValue(new Promise(() => {}));
    mount();
    expect(styleText()).toContain('--primary:7 8% 9%;');
    expect(screen.getByTestId('p').dataset.loading).toBe('false');
  });

  it('on error keeps the NOC standard, logs, and reports platform', async () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {});
    apiGet.mockResolvedValue(accessOf('org-a'));
    coreGet.mockRejectedValue(new Error('boom'));
    mount();
    await waitFor(() => expect(err).toHaveBeenCalled());
    expect(styleText()).toBe('');
    expect(screen.getByTestId('p').dataset.source).toBe('platform');
    expect(screen.getByTestId('p').dataset.loading).toBe('false');
    err.mockRestore();
  });

  it('a corrupt cache is ignored (sanitized), not applied', () => {
    window.localStorage.setItem('noc:brand:last-org', 'org-a');
    window.localStorage.setItem('noc:brand:org-a', '{not json');
    apiGet.mockReturnValue(new Promise(() => {}));
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    mount();
    expect(styleText()).toBe('');
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it('keys the query by org: a swap refetches and reapplies, org A never stands in for org B', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    apiGet.mockResolvedValue(accessOf('org-a'));
    coreGet.mockResolvedValue(brandOf('1 1% 1%'));
    mount(qc);
    await waitFor(() => expect(styleText()).toContain('--primary:1 1% 1%;'));
    expect(qc.getQueryData(['brand', 'current', 'org-a'])).toBeDefined();

    coreGet.mockResolvedValue(brandOf('2 2% 2%'));
    qc.setQueryData(['me', 'access'], accessOf('org-b'));
    await waitFor(() => expect(styleText()).toContain('--primary:2 2% 2%;'));
    expect(qc.getQueryData(['brand', 'current', 'org-b'])).toBeDefined();
  });

  it('a platform answer drops the org cache and clears nothing but the override', async () => {
    window.localStorage.setItem('noc:brand:org-a', '{}');
    apiGet.mockResolvedValue(accessOf('org-a'));
    coreGet.mockResolvedValue(brandOf('3 3% 3%', 'platform'));
    mount();
    await waitFor(() => expect(window.localStorage.getItem('noc:brand:org-a')).toBeNull());
  });
});
