/** Page keys + module items: what `defineModule` mounts, and that the BE page-key contract is the same. */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { defineModule } from '../modules/define';
import { moduleManifest } from '../modules/manifest';
import { createAssignmentHooks } from './hooks';
import { ASSIGNMENT_DEFAULT_PATHS, ASSIGNMENT_PAGE_KEYS, assignmentModuleItems } from './pages';
import { ROUTES, makeApi, routeGet, wrapperFor } from './testUtils';

afterEach(cleanup);

const hooks = () => {
  const api = makeApi();
  routeGet(api, ROUTES);
  return createAssignmentHooks(api);
};

describe('assignmentModuleItems', () => {
  it('yields the two pages with their page keys, default paths and pt-BR labels', () => {
    const items = assignmentModuleItems({ hooks: hooks() });
    expect(items.map((i) => [i.pageKey, i.path, i.label])).toEqual([
      ['crm_distribuicao', '/crm/distribuicao', 'Distribuição'],
      ['crm_equipes', '/crm/equipes', 'Equipes'],
    ]);
    expect(Object.values(ASSIGNMENT_PAGE_KEYS)).toEqual(['crm_distribuicao', 'crm_equipes']);
    expect(ASSIGNMENT_DEFAULT_PATHS.rules).toBe('/crm/distribuicao');
  });

  it('a module can mount them: the nav group, the routes and the page-key manifest carry both pages', () => {
    const crm = defineModule({ key: 'crm', items: assignmentModuleItems({ hooks: hooks(), paths: { rules: '/crm/vendas/distribuicao' }, labels: { teams: 'Times' } }) });
    expect(crm.pageKeys).toEqual(['crm_distribuicao', 'crm_equipes']);
    expect(crm.routes.map((r) => r.path)).toEqual(['/crm/vendas/distribuicao', '/crm/equipes']);
    expect(crm.navGroup.items.map((i) => i.name)).toEqual(['Distribuição', 'Times']);
    const manifest = moduleManifest([crm]);
    expect(manifest.modules[0].pages.map((p) => p.key)).toEqual(['crm_distribuicao', 'crm_equipes']);
  });

  it('the mounted page is the real one, and canWrite may be a hook evaluated while rendering', async () => {
    const [rules] = assignmentModuleItems({ hooks: hooks(), canWrite: () => false });
    const Rules = rules.element!;
    const Wrapper = wrapperFor();
    render(<Wrapper><Rules /></Wrapper>);
    expect(await screen.findByTestId('strategy-select')).toBeDisabled();
    cleanup();
    const [writable] = assignmentModuleItems({ hooks: hooks(), canWrite: () => true });
    const Writable = writable.element!;
    render(<Wrapper><Writable /></Wrapper>);
    expect(await screen.findByTestId('strategy-select')).toBeEnabled();
  });

  it('roles and status ride through to the items (UX only)', () => {
    const items = assignmentModuleItems({ hooks: hooks(), roles: ['owner', 'admin'], status: 'desenvolvimento' });
    expect(items.every((i) => i.status === 'desenvolvimento' && i.roles?.join() === 'owner,admin')).toBe(true);
  });
});
