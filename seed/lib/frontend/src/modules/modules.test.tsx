/// <reference types="@testing-library/jest-dom" />
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Home } from 'lucide-react';

import { Sidebar } from '../design-system/components/Sidebar';
import { MODULE_GROUP_ORDER } from '../design-system/components/nav-groups';
import { filterNavByPageStatus, type StatusPagina } from '../page-status';
import { assertManifestMatches, composeModules, defineModule, extendModule, moduleManifest, useEnabledModules } from './index';

afterEach(cleanup);

const Leads = () => <div>leads page</div>;
const Funil = () => <div>funil page</div>;
const Fin = () => <div>fin page</div>;

const crm = defineModule({
  key: 'crm',
  items: [
    { label: 'Leads', path: '/crm/leads', pageKey: 'crm/leads', icon: Home, element: Leads },
    { label: 'Funil', path: '/crm/funil', pageKey: 'crm/funil', icon: Home, element: Funil },
    { label: 'Relatórios', path: '/crm/relatorios', pageKey: 'crm/relatorios', icon: Home, status: 'desenvolvimento', roles: ['owner', 'admin'] },
  ],
});
const erp = defineModule({
  key: 'erp',
  enablementKey: 'erp-financeiro',
  items: [{ label: 'Financeiro', path: '/erp/financeiro', pageKey: 'erp/financeiro', icon: Home, element: Fin }],
});
const settings = { key: 'configuracoes', label: 'Configurações', icon: Home, items: [{ name: 'Geral', href: '/cfg', icon: Home, route: 'cfg' }] };
const all = new Set(['crm', 'erp-financeiro']);

describe('defineModule', () => {
  it('yields nav group, routes and page keys', () => {
    expect(crm.navGroup.key).toBe('crm');
    expect(crm.navGroup.label).toBe('CRM');
    expect(crm.navGroup.items.map((i) => i.route)).toEqual(['crm/leads', 'crm/funil', 'crm/relatorios']);
    expect(crm.routes.map((r) => r.path)).toEqual(['/crm/leads', '/crm/funil']); // nav-only item has no route
    expect(crm.pageKeys).toEqual(['crm/leads', 'crm/funil', 'crm/relatorios']);
  });
  it('refuses non-canonical keys, duplicate page keys and paths', () => {
    expect(() => defineModule({ key: 'nope' as never, items: [] })).toThrow(/canonical/);
    expect(() => defineModule({ key: 'crm', items: [{ label: 'a', path: '/a', pageKey: 'a' }, { label: 'b', path: '/b', pageKey: 'a' }] })).toThrow(/duplicate pageKey/);
    expect(() => defineModule({ key: 'crm', items: [{ label: 'a', path: '/a', pageKey: 'a' }, { label: 'b', path: '/a', pageKey: 'b' }] })).toThrow(/duplicate path/);
  });
  it('children become a nested group and still count as pages', () => {
    const m = defineModule({ key: 'cms', items: [{ label: 'Blog', path: '/cms/blog', pageKey: 'cms/blog', children: [{ label: 'Posts', path: '/cms/blog/posts', pageKey: 'cms/posts' }] }] });
    expect(m.navGroup.groups?.[0].items.map((i) => i.route)).toEqual(['cms/posts']);
    expect(m.pageKeys).toEqual(['cms/blog', 'cms/posts']);
  });
});

describe('extendModule', () => {
  it('adds, overrides and removes without touching the base', () => {
    const ext = extendModule(crm, {
      items: [{ label: 'Visitas', path: '/crm/visitas', pageKey: 'crm/visitas' }],
      insertAfter: 'crm/leads',
      override: { 'crm/funil': { label: 'Pipeline' } },
      remove: ['crm/relatorios'],
    });
    expect(ext.pageKeys).toEqual(['crm/leads', 'crm/visitas', 'crm/funil']);
    expect(ext.navGroup.items.find((i) => i.route === 'crm/funil')?.name).toBe('Pipeline');
    expect(crm.pageKeys).toHaveLength(3);
    expect(ext.enablementKey).toBe('crm');
  });
  it('refuses unknown page keys and a pageKey change', () => {
    expect(() => extendModule(crm, { remove: ['x'] })).toThrow(/unknown pageKey/);
    expect(() => extendModule(crm, { override: { nope: { label: 'x' } } })).toThrow(/unknown pageKey/);
  });
});

describe('composeModules', () => {
  it('orders groups canonically and puts unknown local groups after', () => {
    const out = composeModules({ modules: [erp, crm], localGroups: [settings, { ...settings, key: 'mine', label: 'Mine' }], enabledKeys: all });
    expect(out.navGroups.map((g) => g.key)).toEqual(['crm', 'erp', 'configuracoes', 'mine']);
    expect(out.navGroups.map((g) => g.key).filter((k) => MODULE_GROUP_ORDER.includes(k as never))).toEqual(['crm', 'erp', 'configuracoes']);
    expect(out.routes.map((r) => r.pageKey)).toEqual(['erp/financeiro', 'crm/leads', 'crm/funil']);
  });
  it('a module disabled for the org is absent: no nav group, no routes, no page keys', () => {
    const out = composeModules({ modules: [crm, erp], enabledKeys: new Set(['crm']) });
    expect(out.navGroups.map((g) => g.key)).toEqual(['crm']);
    expect(out.routes.some((r) => r.moduleKey === 'erp')).toBe(false);
    expect(out.pageKeys).not.toContain('erp/financeiro');
    expect(out.hiddenModules).toEqual(['erp']);
  });
  it('unknown enablement renders no module and reports pending', () => {
    const out = composeModules({ modules: [crm], localGroups: [settings], enabledKeys: null });
    expect(out.pending).toBe(true);
    expect(out.navGroups.map((g) => g.key)).toEqual(['configuracoes']);
    expect(out.routes).toEqual([]);
  });
  it('role filter drops items and routes', () => {
    const out = composeModules({ modules: [crm], enabledKeys: all, orgRole: 'member' });
    expect(out.navGroups[0].items.map((i) => i.route)).toEqual(['crm/leads', 'crm/funil']);
  });
  it('refuses a page in two modules and a local group colliding with a module', () => {
    const dup = defineModule({ key: 'cms', items: [{ label: 'L', path: '/cms/l', pageKey: 'crm/leads' }] });
    expect(() => composeModules({ modules: [crm, dup], enabledKeys: all })).toThrow(/one module/);
    expect(() => composeModules({ modules: [crm], localGroups: [{ ...settings, key: 'crm' }], enabledKeys: all })).toThrow(/collides/);
  });
  it('status_pagina still gates the composed nav (page keys tie to rows)', () => {
    const rows: StatusPagina[] = [
      { id: '1', nome_pagina: 'crm/leads', status: 'producao' },
      { id: '2', nome_pagina: 'crm/relatorios', status: 'desenvolvimento' },
    ];
    const { navGroups } = composeModules({ modules: [crm], enabledKeys: all });
    const asMember = filterNavByPageStatus(navGroups as never, rows, 'member') as any[];
    expect(asMember[0].items.map((i: any) => i.name)).toEqual(['Leads']); // funil has no row -> hidden
    const asOwner = filterNavByPageStatus(navGroups as never, rows, 'owner') as any[];
    expect(asOwner[0].items.map((i: any) => [i.name, i.badge])).toEqual([['Leads', undefined], ['Relatórios', 'DEV']]);
  });
  it('a disabled module does not render in the sidebar or as a route', () => {
    const out = composeModules({ modules: [crm, erp], enabledKeys: new Set(['crm']) });
    const groups = (out.navGroups as any[]).map(({ items, ...g }) => ({ ...g, items: items.map(({ route: _r, ...i }: any) => ({ ...i, icon: Home })), icon: Home }));
    render(
      <MemoryRouter initialEntries={['/erp/financeiro']}>
        <Sidebar brandIcon={Home} brandTitle="T" brandSubtitle="S" navGroups={groups} storageKey="mod-test" />
        <Routes>
          {out.routes.map((r) => <Route key={r.pageKey} path={r.path} element={<r.Component />} />)}
          <Route path="*" element={<div>not found</div>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText('not found')).toBeInTheDocument();
    expect(screen.queryByText('fin page')).toBeNull();
    expect(screen.queryByText('ERP')).toBeNull();
    expect(screen.getByText('CRM')).toBeInTheDocument();
  });
});

describe('useEnabledModules', () => {
  function Probe({ get }: { get: () => Promise<unknown> }) {
    const { enabledKeys, showSkeleton, error } = useEnabledModules({ get } as never);
    return <div>{showSkeleton ? 'loading' : error ? 'error' : [...(enabledKeys ?? [])].join(',')}</div>;
  }
  const wrap = (get: () => Promise<unknown>) => (
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Probe get={get} /></QueryClientProvider>
  );
  it('null while loading, then the enabled enablement keys', async () => {
    render(wrap(async () => ({ modules: [{ key: 'crm', enablement_key: 'crm', enabled: true, permissions: {} }, { key: 'erp', enablement_key: 'erp-financeiro', enabled: false, permissions: {} }] })));
    expect(screen.getByText('loading')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('crm')).toBeInTheDocument());
  });
  it('a failed read is an error, never an assumed set', async () => {
    render(wrap(async () => { throw new Error('boom'); }));
    await waitFor(() => expect(screen.getByText('error')).toBeInTheDocument());
  });
});

describe('page-key contract', () => {
  const fixture = JSON.parse(readFileSync(resolve(__dirname, '../../../backend/tests/fixtures/module_manifest.json'), 'utf8'));
  const crmFull = defineModule({
    key: 'crm',
    items: [
      { label: 'Leads', path: '/crm/leads', pageKey: 'crm/leads' },
      { label: 'Funil', path: '/crm/funil', pageKey: 'crm/funil' },
      { label: 'Relatórios', path: '/crm/relatorios', pageKey: 'crm/relatorios', status: 'desenvolvimento' },
    ],
  });
  const erpFull = defineModule({ key: 'erp', enablementKey: 'erp-financeiro', items: [{ label: 'Financeiro', path: '/erp/financeiro', pageKey: 'erp/financeiro' }] });
  it('matches the manifest the BE ModuleSpec fixture pins', () => {
    expect(moduleManifest([erpFull, crmFull])).toEqual(fixture);
    expect(() => assertManifestMatches([erpFull, crmFull], fixture)).not.toThrow();
  });
  it('fails when a page key diverges', () => {
    const drift = defineModule({ key: 'crm', items: [{ label: 'Leads', path: '/crm/leads', pageKey: 'crm/leadz' }] });
    expect(() => assertManifestMatches([drift, erpFull], fixture)).toThrow(/diverged/);
  });
});
