import * as React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ApiError, type ApiClient } from '../../api';
import { ConfirmProvider } from '../confirm';
import { ApiTokensPanel } from './ApiTokensPanel';
import { createApiTokensHooks, type ApiTokenItem } from './createApiTokensHooks';

let api: ApiClient;
const last = <T,>(xs: T[]): T => xs[xs.length - 1];
const tok = (id: string, over: Partial<ApiTokenItem> = {}): ApiTokenItem => ({
  id, label: `token-${id}`, prefix: 'noc_3a4f9c01', scopes: ['reminders:read', 'reminders:write'],
  created_at: '2026-11-04T10:00:00Z', last_used_at: null, revoked_at: null, expires_at: null, service_account_id: null, ...over,
});

function mount(props: Partial<React.ComponentProps<typeof ApiTokensPanel>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const hooks = createApiTokensHooks(api);
  return render(
    <QueryClientProvider client={qc}>
      <ConfirmProvider>
        <ApiTokensPanel hooks={hooks} {...props} />
      </ConfirmProvider>
    </QueryClientProvider>,
  );
}

const respond = (list: unknown, scopes = { scopes: ['reminders:read', 'reminders:write'], strict: true }) =>
  (api.get as any).mockImplementation(async (p: string) => {
    if (p.endsWith('/scopes')) return scopes;
    if (list instanceof Error) throw list;
    return list;
  });

beforeEach(() => {
  api = { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() } as unknown as ApiClient;
});

describe('ApiTokensPanel states', () => {
  it('shows a skeleton first, then the list', async () => {
    respond([tok('1')]);
    mount();
    expect(screen.getByLabelText('Carregando tokens')).toBeTruthy();
    expect(await screen.findByText('token-1')).toBeTruthy();
  });

  it('shows an empty state', async () => {
    respond([]);
    mount();
    expect(await screen.findByTestId('api-tokens-empty')).toBeTruthy();
  });

  it('shows the error with a retry', async () => {
    respond(new ApiError(500, 'boom'));
    mount();
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Tentar de novo' })).toBeTruthy();
  });

  it('masks the prefix and shows scopes, expiry and last use', async () => {
    respond([tok('1', { last_used_at: '2026-11-04T12:00:00Z', expires_at: '2099-01-01T00:00:00Z' }), tok('2')]);
    mount();
    expect((await screen.findByTestId('api-token-mask-1')).textContent).toBe('noc_••••9c01');
    const row = screen.getByTestId('api-token-row-1');
    expect(within(row).getByText('reminders:write')).toBeTruthy();
    expect(within(row).queryByText('Nunca usado')).toBeNull();
    expect(within(screen.getByTestId('api-token-row-2')).getByText('Nunca usado')).toBeTruthy();
    expect(within(screen.getByTestId('api-token-row-2')).getByText('Sem expiração')).toBeTruthy();
    expect(screen.queryByText(/noc_3a4f9c01/)).toBeNull();
  });

  it('marks revoked tokens and offers no actions on them', async () => {
    respond([tok('1', { revoked_at: '2026-11-04T12:00:00Z' })]);
    mount();
    const row = await screen.findByTestId('api-token-row-1');
    expect(within(row).getByText('Revogado')).toBeTruthy();
    expect(within(row).queryByRole('button', { name: /Revogar/ })).toBeNull();
  });
});

describe('mint', () => {
  it('offers only the server scopes, generates, and shows the secret once', async () => {
    respond([]);
    (api.post as any).mockResolvedValue({
      id: '9', label: 'noc-agent', token: 'noc_SECRET123', prefix: 'noc_aaaabbbb',
      scopes: ['reminders:read'], created_at: '2026-11-04T11:00:00Z', expires_at: null,
    });
    mount();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Gerar token' }));
    // scopes are checkboxes from the server list — there is no free-text scope field
    expect(await screen.findByLabelText(/reminders:read/)).toBeTruthy();
    expect(screen.getAllByRole('checkbox')).toHaveLength(2);
    // The settle refetch never answers: the new row must come from the write itself.
    (api.get as any).mockReturnValue(new Promise(() => undefined));
    const submit = last(screen.getAllByRole('button', { name: 'Gerar token' }));
    expect((submit as HTMLButtonElement).disabled).toBe(true);
    await user.type(screen.getByLabelText('Nome do token'), 'noc-agent');
    await user.click(screen.getByLabelText(/reminders:read/));
    await user.selectOptions(screen.getByLabelText('Validade'), 'never');
    await user.click(last(screen.getAllByRole('button', { name: 'Gerar token' })));
    expect((await screen.findByTestId('api-token-secret')).textContent).toBe('noc_SECRET123');
    expect((api.post as any).mock.calls[0][1]).toMatchObject({ label: 'noc-agent', scopes: ['reminders:read'], no_expiry: true });
    // Escape does not discard the only copy
    await user.keyboard('{Escape}');
    expect(screen.getByTestId('api-token-secret')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'Já copiei' }));
    await waitFor(() => expect(screen.queryByTestId('api-token-secret')).toBeNull());
    // and the new row is in the list without a refetch round trip
    expect(await screen.findByText('noc-agent')).toBeTruthy();
  });

  it('renders the named MFA refusal inline and keeps the form', async () => {
    respond([]);
    (api.post as any).mockRejectedValue(new ApiError(403, 'mfa_required', { detail: 'mfa_required' }));
    mount();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Gerar token' }));
    await user.type(await screen.findByLabelText('Nome do token'), 'x');
    await user.click(await screen.findByLabelText(/reminders:read/));
    await user.click(last(screen.getAllByRole('button', { name: 'Gerar token' })));
    expect((await screen.findByText(/verificação em duas etapas/)).getAttribute('role')).toBe('alert');
    expect((screen.getByLabelText('Nome do token') as HTMLInputElement).value).toBe('x');
  });

  it('says so when the scope list fails to load', async () => {
    (api.get as any).mockImplementation(async (p: string) => {
      if (p.endsWith('/scopes')) throw new ApiError(500, 'x');
      return [];
    });
    mount();
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Gerar token' }));
    expect(await screen.findByText(/Não foi possível carregar os escopos/)).toBeTruthy();
  });
});

describe('rotate and revoke', () => {
  it('confirms, then revokes', async () => {
    respond([tok('1')]);
    (api.delete as any).mockResolvedValue(undefined);
    mount();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Revogar token-1' }));
    expect(api.delete).not.toHaveBeenCalled();
    (api.get as any).mockReturnValue(new Promise(() => undefined));
    await user.click(await screen.findByRole('button', { name: 'Revogar' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/settings/api-tokens/1'));
    expect(await within(screen.getByTestId('api-token-row-1')).findByText('Revogado')).toBeTruthy();
  });

  it('cancelling the confirmation changes nothing', async () => {
    respond([tok('1')]);
    mount();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Revogar token-1' }));
    await user.click(await screen.findByRole('button', { name: 'Cancelar' }));
    expect(api.delete).not.toHaveBeenCalled();
  });

  it('rotates and shows the successor secret once', async () => {
    respond([tok('1')]);
    (api.post as any).mockResolvedValue({
      id: '2', label: 'token-1', token: 'noc_NEWSECRET', prefix: 'noc_ccccdddd', scopes: ['reminders:read'],
      created_at: '2026-11-04T11:00:00Z', expires_at: null,
    });
    mount();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Rotacionar token-1' }));
    await user.click(await screen.findByRole('button', { name: 'Rotacionar' }));
    expect((await screen.findByTestId('api-token-secret')).textContent).toBe('noc_NEWSECRET');
    expect(api.post).toHaveBeenCalledWith('/api/settings/api-tokens/1/rotate', {});
  });

  it('shows a refused rotation in the row', async () => {
    respond([tok('1')]);
    (api.post as any).mockRejectedValue(new ApiError(403, 'mfa_required', { detail: 'mfa_required' }));
    mount();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Rotacionar token-1' }));
    await user.click(await screen.findByRole('button', { name: 'Rotacionar' }));
    expect(await within(screen.getByTestId('api-token-row-1')).findByRole('alert')).toBeTruthy();
  });
});
