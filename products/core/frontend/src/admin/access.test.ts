import { describe, expect, it } from 'vitest';
import { matchPath } from 'react-router-dom';
import { canReach, pruneNavGroups } from './access';
import { ADMIN_NAV_GROUPS, ADMIN_STANDALONE_ITEMS } from './navConfig';
import { ADMIN_ROUTES } from './routes';

const names = (groups: ReturnType<typeof pruneNavGroups>): string[] =>
  groups.flatMap((g) => [...g.items.map((i) => i.name), ...names(g.groups ?? [])]);

describe('canReach', () => {
  it('a platform admin reaches every admin path', () => {
    for (const r of ADMIN_ROUTES) expect(canReach('admin', r.path)).toBe(true);
  });

  it('marketing reaches /admin/website/* only', () => {
    expect(canReach('marketing', '/admin/website/leads')).toBe(true);
    expect(canReach('marketing', '/admin/website/docs/*')).toBe(true);
    expect(canReach('marketing', '/admin')).toBe(false);
    expect(canReach('marketing', '/admin/users')).toBe(false);
    expect(canReach('marketing', '/admin/websitex')).toBe(false);
    expect(canReach('marketing', '/security')).toBe(false);
  });

  it('no role (or an unknown one) reaches nothing', () => {
    expect(canReach(undefined, '/admin')).toBe(false);
    expect(canReach(undefined, '/admin/website/leads')).toBe(false);
  });

  it('registers exactly the website routes for marketing', () => {
    const paths = ADMIN_ROUTES.filter((r) => canReach('marketing', r.path)).map((r) => r.path);
    expect(paths.length).toBeGreaterThan(0);
    expect(paths.every((p) => p.startsWith('/admin/website'))).toBe(true);
  });
});

describe('pruneNavGroups (same predicate as the route gate)', () => {
  it('leaves a platform admin the whole tree', () => {
    expect(pruneNavGroups(ADMIN_NAV_GROUPS, 'admin').map((g) => g.key)).toEqual(ADMIN_NAV_GROUPS.map((g) => g.key));
  });

  it('shows marketing only Leads do site, Site and Documentação, with empty groups pruned', () => {
    const pruned = pruneNavGroups(ADMIN_NAV_GROUPS, 'marketing');
    expect(pruned.map((g) => g.key)).toEqual(['crm', 'cms']);
    expect(names(pruned)).toEqual(['Leads do site', 'Site', 'Documentação']);
  });

  it('shows nobody else anything', () => {
    expect(pruneNavGroups(ADMIN_NAV_GROUPS, undefined)).toEqual([]);
  });
});

describe('nav config', () => {
  it('lists the module groups in the canonical order, then core groups', () => {
    expect(ADMIN_NAV_GROUPS.map((g) => g.key)).toEqual([
      'crm', 'erp', 'cms', 'integracoes', 'configuracoes', 'operacao', 'modelos',
    ]);
    expect(ADMIN_STANDALONE_ITEMS.map((i) => i.name)).toEqual(['Painel']);
  });

  it('every admin link resolves to a registered route (no page loses its link)', () => {
    const hrefs: string[] = [];
    const walk = (gs: typeof ADMIN_NAV_GROUPS) => gs.forEach((g) => { g.items.forEach((i) => hrefs.push(i.href)); walk(g.groups ?? []); });
    walk(ADMIN_NAV_GROUPS);
    ADMIN_STANDALONE_ITEMS.forEach((i) => hrefs.push(i.href));
    for (const href of hrefs.filter((h) => h.startsWith('/admin'))) {
      expect(ADMIN_ROUTES.some((r) => matchPath({ path: r.path, end: true }, href)), href).toBe(true);
    }
  });

  it('every admin route is linked from the nav, except the lead detail page', () => {
    const hrefs: string[] = [];
    const walk = (gs: typeof ADMIN_NAV_GROUPS) => gs.forEach((g) => { g.items.forEach((i) => hrefs.push(i.href)); walk(g.groups ?? []); });
    walk(ADMIN_NAV_GROUPS);
    ADMIN_STANDALONE_ITEMS.forEach((i) => hrefs.push(i.href));
    for (const r of ADMIN_ROUTES.filter((x) => x.path !== '/admin/website/leads/:id')) {
      const base = r.path.replace(/\/\*$/, '');
      expect(hrefs.some((h) => h === base || h.startsWith(`${base}/`)), r.path).toBe(true);
    }
  });
});
