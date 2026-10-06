import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AdminOrganizacoes } from './AdminOrganizacoes';
import { ActAsApiProvider, createActAsApi, normalizeHistory, type HttpClient } from '../../lib/actAs';

afterEach(() => cleanup());

const ORGS = [
  {
    id: 'o1', nome: 'Imobiliária Acme', slug: 'acme', owner_email: 'dono@acme.com',
    licensed_products: [{ slug: 'igig', nome: 'IGIG', url_base: 'https://igig.example' }],
  },
  { id: 'o2', nome: 'Sem Produtos', slug: 'sp', owner_email: null, licensed_products: [] },
];

function fakeHttp(routes: Record<string, (body?: unknown) => unknown>) {
  const calls: Array<{ method: string; path: string; body?: unknown }> = [];
  const h = (method: string) => async (path: string, body?: unknown) => {
    calls.push({ method, path, body });
    const r = routes[`${method} ${path}`];
    if (!r) throw new Error(`no fake route ${method} ${path}`);
    return r(body);
  };
  return { calls, http: { get: h('GET'), post: h('POST') } as unknown as HttpClient };
}

function mount(http: HttpClient) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ActAsApiProvider value={createActAsApi(http)}>
        <AdminOrganizacoes />
      </ActAsApiProvider>
    </QueryClientProvider>,
  );
}

describe('AdminOrganizacoes', () => {
  it('shows a skeleton while loading, never the empty state', async () => {
    let release!: (v: unknown) => void;
    const pending = new Promise((r) => { release = r; });
    const { http } = fakeHttp({ 'GET /api/admin/orgs': () => pending });
    mount(http);
    expect(screen.queryByText('Nenhuma organização encontrada')).toBeNull();
    release(ORGS);
    expect(await screen.findByText('Imobiliária Acme')).toBeTruthy();
  });

  it('renders the empty state', async () => {
    const { http } = fakeHttp({ 'GET /api/admin/orgs': () => [] });
    mount(http);
    expect(await screen.findByText('Nenhuma organização encontrada')).toBeTruthy();
  });

  it('renders the error state', async () => {
    const { http } = fakeHttp({ 'GET /api/admin/orgs': () => { throw new Error('boom'); } });
    mount(http);
    expect((await screen.findByRole('alert')).textContent).toContain('boom');
  });

  it('lists orgs, owner and an Entrar button per licensed product', async () => {
    const { http } = fakeHttp({ 'GET /api/admin/orgs': () => ORGS });
    mount(http);
    expect(await screen.findByText('dono@acme.com')).toBeTruthy();
    expect(screen.getByText('IGIG')).toBeTruthy();
    expect(screen.getAllByRole('button', { name: /Entrar em/ })).toHaveLength(1);
    expect(screen.getByText('Nenhum produto licenciado')).toBeTruthy();
  });

  it('Entrar → optional Motivo → POST act-as → redirects to redirect_url', async () => {
    const { http, calls } = fakeHttp({
      'GET /api/admin/orgs': () => ORGS,
      'POST /api/admin/act-as': () => ({ session_id: 's1', redirect_url: 'https://igig.example/sso?token=t' }),
    });
    const assign = vi.fn();
    const orig = window.location;
    Object.defineProperty(window, 'location', { configurable: true, value: { ...orig, assign } });
    mount(http);
    fireEvent.click(await screen.findByRole('button', { name: 'Entrar em IGIG como Imobiliária Acme' }));
    const dialog = screen.getByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Motivo'), { target: { value: ' suporte #1 ' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirmar e entrar' }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith('https://igig.example/sso?token=t'));
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ org_id: 'o1', product_slug: 'igig', reason: 'suporte #1' });
    Object.defineProperty(window, 'location', { configurable: true, value: orig });
  });

  it('omits reason when left blank and surfaces a 403 error in the dialog', async () => {
    const { http, calls } = fakeHttp({
      'GET /api/admin/orgs': () => ORGS,
      'POST /api/admin/act-as': () => { throw new Error('Sua organização não tem acesso a este produto.'); },
    });
    mount(http);
    fireEvent.click(await screen.findByRole('button', { name: /Entrar em IGIG/ }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Confirmar e entrar' }));
    await waitFor(() => expect(within(screen.getByRole('dialog')).getByRole('alert').textContent).toContain('não tem acesso'));
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ org_id: 'o1', product_slug: 'igig' });
  });

  it('Histórico tab lists sessions (and has its own empty state)', async () => {
    const { http } = fakeHttp({
      'GET /api/admin/orgs': () => ORGS,
      'GET /api/admin/act-as/history': () => [
        { id: 'h1', action: 'act_as.start', created_at: '2026-10-06T12:00:00Z', org_nome: 'Imobiliária Acme', product_slug: 'igig', reason: 'suporte' },
      ],
    });
    mount(http);
    fireEvent.click(screen.getByRole('tab', { name: 'Histórico' }));
    expect(await screen.findByText('suporte')).toBeTruthy();
    expect(screen.getByText('Entrada')).toBeTruthy();
  });
});

describe('normalizeHistory', () => {
  it('accepts envelopes and nested details', () => {
    const rows = normalizeHistory({ items: [{ id: 'x', action: 'act_as.end', details: { org_nome: 'A', reason: 'r' } }] });
    expect(rows[0]).toMatchObject({ id: 'x', action: 'act_as.end', org: 'A', reason: 'r' });
    expect(normalizeHistory(null)).toEqual([]);
  });
});
