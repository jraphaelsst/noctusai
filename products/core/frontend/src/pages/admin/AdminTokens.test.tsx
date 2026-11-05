/** Admin "Tokens de API": the MFA-to-mint switch (default off, confirm, named refusal) and the shared token card. */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiError } from '@noctusai/lib/api';
import { ConfirmProvider } from '@noctusai/lib/components';
import { AdminTokens } from './AdminTokens';

afterEach(cleanup);

type Handler = (body?: unknown) => unknown | Promise<unknown>;
function http(routes: Record<string, Handler>) {
  const calls: Array<{ method: string; path: string; body?: unknown }> = [];
  const call = (method: string) => async (path: string, body?: unknown) => {
    calls.push({ method, path, body });
    const handler = routes[`${method} ${path}`];
    if (!handler) throw new Error(`no fake route for ${method} ${path}`);
    return handler(body);
  };
  return { calls, routes, get: call('GET'), post: call('POST'), put: call('PUT'), patch: call('PATCH'), delete: call('DELETE') } as any;
}

function renderPage(h: ReturnType<typeof http>) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ConfirmProvider>
        <AdminTokens http={h} />
      </ConfirmProvider>
    </QueryClientProvider>,
  );
}

const TOKEN = {
  id: 't1', label: 'noc-agent', prefix: 'noc_3a4f9c01', scopes: ['reminders:read'], created_at: '2026-11-04T10:00:00Z',
  last_used_at: null, revoked_at: null, expires_at: null, service_account_id: 'sa1',
};
const base = (mfa: boolean, extra: Record<string, Handler> = {}) => ({
  'GET /api/admin/tokens/settings': () => ({ data: { mfa_required: mfa } }),
  'GET /api/admin/tokens/service-accounts': () => ({ data: [{ id: 'sa1', slug: 'noc-agent', name: 'noc-agent' }] }),
  'GET /api/settings/api-tokens': () => [TOKEN],
  'GET /api/settings/api-tokens/scopes': () => ({ scopes: ['reminders:read', 'reminders:write'], strict: true }),
  ...extra,
});

describe('AdminTokens — MFA switch', () => {
  it('defaults to OFF and says so', async () => {
    renderPage(http(base(false)));
    expect(await screen.findByTestId('mfa-tokens-state')).toHaveTextContent('Desligado');
    expect(screen.getByRole('switch', { name: /MFA para gerar tokens/ })).not.toBeChecked();
    expect(screen.getByText(/Ainda não usamos MFA/)).toBeInTheDocument();
  });

  it('reflects ON from the server', async () => {
    renderPage(http(base(true)));
    expect(await screen.findByTestId('mfa-tokens-state')).toHaveTextContent('Ligado');
    expect(screen.getByRole('switch', { name: /MFA para gerar tokens/ })).toBeChecked();
  });

  it('turning it on asks for confirmation, then writes the server answer into the cache', async () => {
    const h = http(base(false, { 'PUT /api/admin/tokens/settings': () => ({ data: { mfa_required: true } }) }));
    renderPage(h);
    const sw = await screen.findByRole('switch', { name: /MFA para gerar tokens/ });
    // the settle refetch never answers: the new state must come from the write itself
    h.routes['GET /api/admin/tokens/settings'] = () => new Promise(() => {});
    fireEvent.click(sw);
    expect(h.calls.some((c: any) => c.method === 'PUT')).toBe(false); // nothing before the confirm
    fireEvent.click(await screen.findByRole('button', { name: 'Exigir MFA' }));
    await waitFor(() => expect(screen.getByTestId('mfa-tokens-state')).toHaveTextContent('Ligado'));
    expect(h.calls.find((c: any) => c.method === 'PUT').body).toEqual({ mfa_required: true });
  });

  it('cancelling the confirmation changes nothing', async () => {
    const h = http(base(false));
    renderPage(h);
    fireEvent.click(await screen.findByRole('switch', { name: /MFA para gerar tokens/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Cancelar' }));
    expect(h.calls.some((c: any) => c.method === 'PUT')).toBe(false);
    expect(screen.getByTestId('mfa-tokens-state')).toHaveTextContent('Desligado');
  });

  it('shows a refused write and leaves the switch where it was', async () => {
    const h = http(base(false, {
      'PUT /api/admin/tokens/settings': () => { throw new ApiError(403, 'x', { detail: { code: 'platform_admin_required' } }); },
    }));
    renderPage(h);
    fireEvent.click(await screen.findByRole('switch', { name: /MFA para gerar tokens/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Exigir MFA' }));
    expect(await screen.findByText(/Apenas administradores da plataforma/)).toBeInTheDocument();
    expect(screen.getByTestId('mfa-tokens-state')).toHaveTextContent('Desligado');
  });

  it('shows the load error with a retry', async () => {
    renderPage(http(base(false, { 'GET /api/admin/tokens/settings': () => { throw new ApiError(500, 'boom'); } })));
    expect(await screen.findByText(/Não foi possível carregar a configuração|boom/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tentar de novo' })).toBeInTheDocument();
  });
});

describe('AdminTokens — token card', () => {
  it('lists tokens masked with their service account', async () => {
    renderPage(http(base(false)));
    const row = await screen.findByTestId('api-token-row-t1');
    expect(within(row).getByText('noc_••••9c01')).toBeInTheDocument();
    expect(within(row).getByText('reminders:read')).toBeInTheDocument();
    expect(within(row).getByText('Conta de serviço:')).toBeInTheDocument();
    expect(screen.queryByText(/noc_3a4f9c01/)).not.toBeInTheDocument();
  });

  it('mints with the server scopes and the noc-agent service account', async () => {
    const h = http(base(false, {
      'POST /api/settings/api-tokens': () => ({
        id: 't2', label: 'lembretes', token: 'noc_SECRET', prefix: 'noc_aaaabbbb', scopes: ['reminders:write'],
        created_at: '2026-11-04T11:00:00Z', expires_at: null, service_account_id: 'sa1',
      }),
    }));
    renderPage(h);
    fireEvent.click(await screen.findByRole('button', { name: 'Gerar token' }));
    fireEvent.change(await screen.findByLabelText('Nome do token'), { target: { value: 'lembretes' } });
    fireEvent.click(await screen.findByLabelText(/reminders:write/));
    fireEvent.change(screen.getByLabelText('Validade'), { target: { value: 'never' } });
    fireEvent.change(screen.getByLabelText('Conta de serviço'), { target: { value: 'sa1' } });
    fireEvent.click(screen.getAllByRole('button', { name: 'Gerar token' }).at(-1)!);
    expect(await screen.findByTestId('api-token-secret')).toHaveTextContent('noc_SECRET');
    expect(h.calls.find((c: any) => c.method === 'POST').body).toEqual({
      label: 'lembretes', scopes: ['reminders:write'], no_expiry: true, service_account_id: 'sa1',
    });
  });

  it('an unmet MFA is refused by name in the mint dialog', async () => {
    const h = http(base(true, {
      'POST /api/settings/api-tokens': () => { throw new ApiError(403, 'mfa_required', { detail: 'mfa_required' }); },
    }));
    renderPage(h);
    fireEvent.click(await screen.findByRole('button', { name: 'Gerar token' }));
    fireEvent.change(await screen.findByLabelText('Nome do token'), { target: { value: 'x' } });
    fireEvent.click(await screen.findByLabelText(/reminders:read/));
    fireEvent.click(screen.getAllByRole('button', { name: 'Gerar token' }).at(-1)!);
    expect(await screen.findByText(/verificação em duas etapas/)).toBeInTheDocument();
  });

  it('still renders the card when the service accounts cannot load, and says so', async () => {
    renderPage(http(base(false, { 'GET /api/admin/tokens/service-accounts': () => { throw new ApiError(500, 'x'); } })));
    expect(await screen.findByTestId('api-token-row-t1')).toBeInTheDocument();
    expect(await screen.findByText(/Não foi possível carregar as contas de serviço/)).toBeInTheDocument();
  });
});
