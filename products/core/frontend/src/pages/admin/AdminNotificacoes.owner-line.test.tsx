/** Admin Notificações > "Quem recebe os avisos": list, add (field errors), toggle, remove, line status — all cache writes. */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfirmProvider } from '@noctusai/lib/components';
import { createNotificationCatalogApi, NotificationCatalogApiProvider } from '../../lib/notificationCatalog';
import { createOwnerLineApi, OwnerLineApiProvider, type OwnerLineHttp } from '../../lib/ownerLine';
import { AdminNotificacoes } from './AdminNotificacoes';

afterEach(cleanup);

type Route = (body?: unknown) => unknown | Promise<unknown>;
function fake(routes: Record<string, Route>) {
  const calls: Array<{ method: string; path: string; body?: unknown }> = [];
  const h = (method: string) => async (path: string, body?: unknown) => {
    calls.push({ method, path, body });
    const r = routes[`${method} ${path.split('?')[0]}`];
    if (!r) throw new Error(`no fake route for ${method} ${path}`);
    return r(body);
  };
  const http = { get: h('GET'), post: h('POST'), put: h('PUT'), patch: h('PATCH'), delete: h('DELETE') };
  return { http, calls, routes };
}

const R = '/api/admin/notifications/recipients';
const A = { id: 'a1', numero: '+5511999998888', nome: 'Raphael', ativo: true, created_at: '2026-11-10T10:00:00Z' };
const B = { id: 'b2', numero: '+5521988887777', nome: null, ativo: false, created_at: '2026-11-10T11:00:00Z' };
const LINE_OFF = () => ({ data: { configurada: false, instancia: null } });

function wrap(f: ReturnType<typeof fake>, ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <NotificationCatalogApiProvider value={createNotificationCatalogApi(f.http as never)}>
        <OwnerLineApiProvider value={createOwnerLineApi(f.http as OwnerLineHttp)}>
          <ConfirmProvider>{ui}</ConfirmProvider>
        </OwnerLineApiProvider>
      </NotificationCatalogApiProvider>
    </QueryClientProvider>
  );
}
const base = (extra: Record<string, Route> = {}) => ({
  'GET /api/admin/notifications': () => ({ data: { window_days: 30, sends_truncated: false, products: [] } }),
  'GET /api/admin/notifications/owner-line': LINE_OFF,
  [`GET ${R}`]: () => ({ data: { items: [A, B] } }),
  ...extra,
});

describe('Quem recebe os avisos', () => {
  it('lists recipients formatted, with the not-configured line status', async () => {
    render(wrap(fake(base()), <AdminNotificacoes />));
    expect(await screen.findByText('+55 11 99999-8888')).toBeInTheDocument();
    expect(screen.getByText('Sem nome')).toBeInTheDocument();
    expect(await screen.findByText(/Linha NoctusAI: não configurada — os avisos por WhatsApp ficam registrados como falha/)).toBeInTheDocument();
  });

  it('shows the connected line with its instance', async () => {
    const f = fake(base({ 'GET /api/admin/notifications/owner-line': () => ({ data: { configurada: true, instancia: 'noc-l3' } }) }));
    render(wrap(f, <AdminNotificacoes />));
    expect(await screen.findByText('Linha NoctusAI: conectada (noc-l3)')).toBeInTheDocument();
  });

  it('empty state tells what to do', async () => {
    render(wrap(fake(base({ [`GET ${R}`]: () => ({ data: { items: [] } }) })), <AdminNotificacoes />));
    expect(await screen.findByText(/Ninguém cadastrado para receber os avisos/)).toBeInTheDocument();
  });

  it('a failed list is an error state, not an empty one', async () => {
    const f = fake(base({ [`GET ${R}`]: () => { throw new Error('boom'); } }));
    render(wrap(f, <AdminNotificacoes />));
    await waitFor(() => expect(screen.queryByText(/Ninguém cadastrado/)).not.toBeInTheDocument());
    expect(await screen.findAllByRole('button', { name: /tentar novamente/i })).not.toHaveLength(0);
  });

  it('rejects an invalid number client-side without calling the server', async () => {
    const f = fake(base());
    render(wrap(f, <AdminNotificacoes />));
    await screen.findByText('+55 11 99999-8888');
    fireEvent.change(screen.getByLabelText('Número (WhatsApp)'), { target: { value: '123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar' }));
    expect(await screen.findByText(/Número inválido/)).toBeInTheDocument();
    expect(screen.getByLabelText('Número (WhatsApp)')).toHaveAttribute('aria-invalid', 'true');
    expect(f.calls.some((c) => c.method === 'POST')).toBe(false);
  });

  it('add appends the server row while the refetch is still pending', async () => {
    const C = { id: 'c3', numero: '+5531977776666', nome: 'Ana', ativo: true, created_at: '2026-11-10T12:00:00Z' };
    const f = fake(base({ [`POST ${R}`]: () => ({ data: C }) }));
    render(wrap(f, <AdminNotificacoes />));
    await screen.findByText('+55 11 99999-8888');
    f.routes[`GET ${R}`] = () => new Promise(() => {});
    fireEvent.change(screen.getByLabelText('Número (WhatsApp)'), { target: { value: '(31) 97777-6666' } });
    fireEvent.change(screen.getByLabelText('Nome (opcional)'), { target: { value: 'Ana' } });
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar' }));
    expect(await screen.findByText('+55 31 97777-6666')).toBeInTheDocument();
    expect(f.calls.find((c) => c.method === 'POST')!.body).toEqual({ numero: '(31) 97777-6666', nome: 'Ana' });
    expect(screen.getByLabelText('Número (WhatsApp)')).toHaveValue('');
  });

  it('maps 409 and 422 to field errors in pt-BR', async () => {
    const f = fake(base({ [`POST ${R}`]: () => { throw Object.assign(new Error('x'), { status: 409, code: 'numero_duplicado' }); } }));
    render(wrap(f, <AdminNotificacoes />));
    await screen.findByText('+55 11 99999-8888');
    fireEvent.change(screen.getByLabelText('Número (WhatsApp)'), { target: { value: '11999998888' } });
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar' }));
    expect(await screen.findByText('Este número já está na lista de destinatários.')).toBeInTheDocument();
    f.routes[`POST ${R}`] = () => { throw Object.assign(new Error('x'), { status: 422, code: 'numero_invalido' }); };
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar' }));
    await waitFor(() => expect(screen.getByLabelText('Número (WhatsApp)')).toHaveAttribute('aria-invalid', 'true'));
    expect(await screen.findByText(/Número inválido\. Use DDD/)).toBeInTheDocument();
  });

  it('toggle flips at once and sends PATCH', async () => {
    const f = fake(base({ [`PATCH ${R}/b2`]: () => ({ data: { ...B, ativo: true } }) }));
    render(wrap(f, <AdminNotificacoes />));
    await screen.findByText('+55 21 98888-7777');
    f.routes[`GET ${R}`] = () => new Promise(() => {});
    const sw = screen.getByRole('switch', { name: /Ativar avisos para \+55 21 98888-7777/ });
    fireEvent.click(sw);
    await waitFor(() => expect(screen.getByRole('switch', { name: /Pausar avisos para \+55 21/ })).toBeChecked());
    expect(f.calls.find((c) => c.method === 'PATCH')!.body).toEqual({ ativo: true });
  });

  it('remove asks first, then deletes the row from the list', async () => {
    const f = fake(base({ [`DELETE ${R}/a1`]: () => ({ data: null }) }));
    render(wrap(f, <AdminNotificacoes />));
    await screen.findByText('+55 11 99999-8888');
    f.routes[`GET ${R}`] = () => new Promise(() => {});
    fireEvent.click(screen.getByRole('button', { name: 'Remover Raphael' }));
    const dialog = await screen.findByRole('dialog');
    expect(f.calls.some((c) => c.method === 'DELETE')).toBe(false);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Remover' }));
    await waitFor(() => expect(screen.queryByText('+55 11 99999-8888')).not.toBeInTheDocument());
    expect(screen.getByText('+55 21 98888-7777')).toBeInTheDocument();
  });
});
