/**
 * Tests for `<ConnectionPairingPanel/>`: QR render, poll stops on WORKING, logout confirm,
 * canManage=false hides actions, empty / loading / error states.
 */
/// <reference types="@testing-library/jest-dom" />
import * as React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { createWhatsAppConnectionsHooks } from '../../whatsapp';
import type { WhatsAppConnectionQr, WhatsAppConnectionStatus } from '../../whatsapp';
import { ConfirmProvider } from '../confirm';
import type { ApiClient } from '../../api';
import { ConnectionPairingPanel } from './ConnectionPairingPanel';

afterEach(cleanup);

const STATUS: WhatsAppConnectionStatus = {
  connection_id: 'c1', status: 'SCAN_QR_CODE', paired: false, me_id: null, me_name: null, session: 'default', error: null,
};
const QR: WhatsAppConnectionQr = { connection_id: 'c1', scannable: true, status: 'SCAN_QR_CODE', png_base64: 'ZmFrZQ==' };

function makeApi(over: Record<string, unknown> = {}): ApiClient {
  return {
    get: vi.fn(async (path: string) => (path.endsWith('/qr') ? QR : STATUS)),
    post: vi.fn(async () => STATUS),
    patch: vi.fn(), delete: vi.fn(), put: vi.fn(),
    ...over,
  } as unknown as ApiClient;
}

function setup(api: ApiClient, props: Partial<React.ComponentProps<typeof ConnectionPairingPanel>> = {}, pollMs = 5) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const base = createWhatsAppConnectionsHooks(api);
  // Fast polling for the test; same hook, shorter interval.
  const hooks = {
    ...base,
    useConnectionQr: (id: string | null, enabled: boolean) => base.useConnectionQr(id, enabled, { pollMs }),
    useConnectionStatus: (id: string | null, enabled?: boolean) => base.useConnectionStatus(id, enabled, { pollMs }),
  };
  return render(
    <QueryClientProvider client={client}>
      <ConfirmProvider>
        <ConnectionPairingPanel connectionId="c1" hooks={hooks} {...props} />
      </ConfirmProvider>
    </QueryClientProvider>,
  );
}

const qrCalls = (api: ApiClient) =>
  (api.get as unknown as ReturnType<typeof vi.fn>).mock.calls.filter(([p]) => String(p).endsWith('/qr')).length;

describe('ConnectionPairingPanel', () => {
  it('renders the QR image when scannable', async () => {
    setup(makeApi());
    const img = await screen.findByTestId('wa-qr-image');
    expect(img).toHaveAttribute('src', 'data:image/png;base64,ZmFrZQ==');
  });

  it('polls the QR until WORKING, then stops', async () => {
    let working = false;
    const api = makeApi({
      get: vi.fn(async (path: string) =>
        path.endsWith('/qr')
          ? { ...QR, scannable: !working, status: working ? 'WORKING' : 'SCAN_QR_CODE' }
          : { ...STATUS, status: working ? 'WORKING' : 'SCAN_QR_CODE', paired: working }),
    });
    setup(api);
    await screen.findByTestId('wa-qr-image');
    await waitFor(() => expect(qrCalls(api)).toBeGreaterThan(1)); // polling
    working = true;
    await waitFor(() => expect(screen.queryByTestId('wa-qr-panel')).not.toBeInTheDocument());
    const after = qrCalls(api);
    await new Promise((r) => setTimeout(r, 60));
    expect(qrCalls(api)).toBeLessThanOrEqual(after + 1);
  });

  it('asks before logout with the product text, and only then POSTs', async () => {
    const api = makeApi();
    setup(api, { onLogoutConfirmText: 'Isso para a Julia e os avisos da equipe.' });
    fireEvent.click(await screen.findByRole('button', { name: 'Desconectar' }));
    const dlg = await screen.findByTestId('confirm-dialog');
    expect(dlg).toHaveTextContent('Isso para a Julia e os avisos da equipe.');
    expect(api.post).not.toHaveBeenCalled();
    fireEvent.click(within(dlg).getByRole('button', { name: 'Cancelar' }));
    await waitFor(() => expect(screen.queryByTestId('confirm-dialog')).not.toBeInTheDocument());
    expect(api.post).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Desconectar' }));
    fireEvent.click(within(await screen.findByTestId('confirm-dialog')).getByRole('button', { name: 'Desconectar' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/whatsapp/connections/c1/logout'));
  });

  it('canManage=false hides the actions and the QR but keeps the status', async () => {
    const api = makeApi();
    setup(api, { canManage: false });
    expect(await screen.findByText('SCAN_QR_CODE')).toBeInTheDocument();
    expect(screen.queryByTestId('wa-pairing-actions')).not.toBeInTheDocument();
    expect(screen.queryByTestId('wa-qr-panel')).not.toBeInTheDocument();
    expect(qrCalls(api)).toBe(0);
  });

  it('shows a skeleton while there is no data, never a fake loaded panel', () => {
    setup(makeApi({ get: vi.fn((): Promise<never> => new Promise(() => {})) }));
    expect(screen.getByRole('status', { name: 'Carregando' })).toBeInTheDocument();
    expect(screen.queryByTestId('wa-pairing-actions')).not.toBeInTheDocument();
  });

  it('shows an alert with retry when the status read is refused', async () => {
    setup(makeApi({ get: vi.fn(async () => { throw new Error('boom'); }) }));
    expect(await screen.findByTestId('wa-pairing-error')).toHaveAttribute('role', 'alert');
    expect(screen.getByRole('button', { name: 'Tentar de novo' })).toBeInTheDocument();
  });

  it('shows a refused action, not silence', async () => {
    const api = makeApi({ post: vi.fn(async () => { throw new Error('WAHA fora do ar'); }) });
    setup(api);
    fireEvent.click(await screen.findByRole('button', { name: 'Iniciar' }));
    expect(await screen.findByTestId('wa-action-error')).toHaveTextContent('WAHA fora do ar');
  });

  it('draws the empty state (with its action slot) when there is no line', () => {
    const api = makeApi();
    setup(api, { connectionId: null, emptyAction: <button type="button">Criar linha</button> });
    expect(screen.getByTestId('wa-pairing-empty')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Criar linha' })).toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalled();
  });
});
