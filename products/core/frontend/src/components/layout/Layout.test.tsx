/**
 * The admin shell renders the seed Sidebar with core's module groups, pruned per role.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Layout } from './Layout';
import { ADMIN_NAV_GROUPS, ADMIN_STANDALONE_ITEMS } from '../../admin/navConfig';
import { WEBSITE_NAV_GROUPS } from '../../admin/websiteConfig';

afterEach(() => { cleanup(); window.localStorage.clear(); });

vi.mock('./CoreHeader', () => ({ CoreHeader: () => <div data-testid="hdr" /> }));

function renderShell(role: 'admin' | 'marketing', path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Layout role={role} navGroups={role === 'admin' ? ADMIN_NAV_GROUPS : WEBSITE_NAV_GROUPS} standaloneItems={role === 'admin' ? ADMIN_STANDALONE_ITEMS : []}><div>BODY</div></Layout>
    </MemoryRouter>,
  );
}

const groupLabels = () =>
  screen.getAllByRole('button').map((b) => b.textContent?.trim() ?? '').filter(Boolean);

describe('admin shell navigation', () => {
  it('lists the module groups in order for a platform admin, with Painel as a standalone item', () => {
    renderShell('admin', '/admin');
    const labels = groupLabels();
    const order = ['CRM', 'Redes Sociais', 'ERP', 'CMS', 'CoreStudio', 'Banib', 'Emissões', 'Integrações', 'Configurações', 'Operação', 'Modelos da plataforma'];
    const idx = order.map((l) => labels.findIndex((x) => x.includes(l)));
    expect(idx.every((i) => i >= 0)).toBe(true);
    expect([...idx].sort((a, b) => a - b)).toEqual(idx);
    expect(screen.getByRole('link', { name: /Painel/ })).toBeTruthy();
  });

  it('shows a marketing user only the website entries (CRM > Leads do site, CMS)', () => {
    renderShell('marketing', '/admin/website/leads');
    const labels = groupLabels();
    expect(labels.some((l) => l.includes('CRM'))).toBe(true);
    expect(labels.some((l) => l.includes('CMS'))).toBe(true);
    for (const l of ['ERP', 'Integrações', 'Configurações', 'Operação', 'Modelos']) {
      expect(labels.some((x) => x.includes(l))).toBe(false);
    }
    expect(screen.getByRole('link', { name: /Leads do site/ })).toBeTruthy();
    expect(screen.queryByRole('link', { name: /Painel/ })).toBeNull();
    expect(screen.queryByRole('link', { name: /Funil/ })).toBeNull();
  });
});
