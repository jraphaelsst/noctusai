/**
 * Tests for `<WhatsAppConnectionsPage/>` (+ its composed
 * `CreateConnectionDialog` / `ConnectionDetailDialog`).
 *
 * Coverage:
 *   1. Loading — Skeleton
 *   2. Empty — default copy, and the `emptyState` slot override
 *   3. Error — role="alert"
 *   4. Success — row rendered with label + live status badge
 *   5. Create flow — dialog open → fill → submit → POST
 *   6. Detail dialog — opens on row click; QR panel renders when not paired
 *   7. Delete — confirm() gate, then DELETE
 */
/// <reference types="@testing-library/jest-dom" />
import * as React from 'react';
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { createWhatsAppConnectionsHooks } from '../../whatsapp';
import { WhatsAppConnectionsPage } from './WhatsAppConnectionsPage';
import type { ApiClient } from '../../api';
import type { WhatsAppConnectionLine, WhatsAppConnectionStatus, WhatsAppConnectionQr } from '../../whatsapp';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

afterEach(cleanup);

const LINE: WhatsAppConnectionLine = {
  id: 'conn-1',
  label: 'Atendimento',
  base_url: 'https://waha.example.com',
  session_name: 'default',
  webhook_url: 'https://sw.example.com/api/whatsapp/webhook/tok',
  created_at: '2026-09-17T00:00:00Z',
  updated_at: '2026-09-17T00:00:00Z',
};

const STATUS_UNPAIRED: WhatsAppConnectionStatus = {
  connection_id: 'conn-1',
  status: 'SCAN_QR_CODE',
  paired: false,
  me_id: null,
  me_name: null,
  session: 'default',
  error: null,
};

const QR_SCANNABLE: WhatsAppConnectionQr = {
  connection_id: 'conn-1',
  scannable: true,
  status: 'SCAN_QR_CODE',
  png_base64: 'ZmFrZS1wbmc=',
};

function makeApi(overrides: Record<string, any> = {}): ApiClient {
  return {
    get: vi.fn(async (path: string) => {
      if (path.endsWith('/status')) return STATUS_UNPAIRED;
      if (path.endsWith('/qr')) return QR_SCANNABLE;
      return [LINE];
    }),
    post: vi.fn(async () => LINE),
    patch: vi.fn(async () => LINE),
    delete: vi.fn(async () => undefined),
    put: vi.fn(),
    ...overrides,
  } as unknown as ApiClient;
}

function renderPage(api: ApiClient, props: Partial<React.ComponentProps<typeof WhatsAppConnectionsPage>> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const hooks = createWhatsAppConnectionsHooks(api);
  const utils = render(
    <QueryClientProvider client={client}>
      <WhatsAppConnectionsPage hooks={hooks} {...props} />
    </QueryClientProvider>,
  );
  return { ...utils, api };
}

// ── 1. Loading ──────────────────────────────────────────────────────────────

describe('WhatsAppConnectionsPage: loading', () => {
  it('renders a Skeleton block while the list query is in flight', () => {
    const api = makeApi({ get: vi.fn((): Promise<any> => new Promise(() => {})) });
    renderPage(api);
    expect(screen.getByRole('status', { name: 'Carregando conexões' })).toBeInTheDocument();
  });
});

// ── 2. Empty ──────────────────────────────────────────────────────────────────

describe('WhatsAppConnectionsPage: empty', () => {
  it('renders the default empty copy when there are zero connections', async () => {
    const api = makeApi({ get: vi.fn(async () => []) });
    renderPage(api);
    expect(await screen.findByTestId('wa-empty-state')).toHaveTextContent(/Nenhuma conexão/i);
  });

  it('renders the emptyState slot when supplied', async () => {
    const api = makeApi({ get: vi.fn(async () => []) });
    renderPage(api, { emptyState: <p>Integração futura — nenhuma conexão pareada.</p> });
    expect(await screen.findByTestId('wa-empty-state')).toHaveTextContent(
      'Integração futura — nenhuma conexão pareada.',
    );
  });
});

// ── 3. Error ──────────────────────────────────────────────────────────────────

describe('WhatsAppConnectionsPage: error', () => {
  it('renders an alert with the error message', async () => {
    const api = makeApi({
      get: vi.fn(async () => {
        throw new Error('Boom 500');
      }),
    });
    renderPage(api);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Boom 500');
  });
});

// ── 4. Success ────────────────────────────────────────────────────────────────

describe('WhatsAppConnectionsPage: success', () => {
  it('renders the connection row with its label and live status badge', async () => {
    renderPage(makeApi());
    expect(await screen.findByText('Atendimento')).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId('wa-status-conn-1')).toHaveTextContent('SCAN_QR_CODE'),
    );
  });
});

// ── 5. Create flow ────────────────────────────────────────────────────────────

describe('WhatsAppConnectionsPage: create flow', () => {
  it('opens the dialog, fills the form, and POSTs on submit', async () => {
    const api = makeApi({ get: vi.fn(async () => []) });
    renderPage(api);
    fireEvent.click(await screen.findByRole('button', { name: /Nova conexão/i }));

    const labelInput = await screen.findByLabelText('Nome');
    const keyInput = screen.getByLabelText('Chave de API WAHA');
    fireEvent.change(labelInput, { target: { value: 'Atendimento' } });
    fireEvent.change(keyInput, { target: { value: 'wa-secret' } });
    fireEvent.click(screen.getByRole('button', { name: 'Criar conexão' }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/whatsapp/connections', {
        label: 'Atendimento',
        api_key: 'wa-secret',
      }),
    );
  });
});

// ── 6. Detail dialog + QR ─────────────────────────────────────────────────────

describe('WhatsAppConnectionsPage: detail dialog', () => {
  it('opens on row click and renders the QR panel when not paired', async () => {
    renderPage(makeApi());
    const row = await screen.findByText('Atendimento');
    fireEvent.click(row);

    expect(await screen.findByTestId('wa-qr-panel')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('wa-qr-image')).toBeInTheDocument());
  });

  it('does not render the QR panel once paired', async () => {
    const api = makeApi({
      get: vi.fn(async (path: string) => {
        if (path.endsWith('/status')) return { ...STATUS_UNPAIRED, paired: true, status: 'WORKING' };
        if (path.endsWith('/qr')) return QR_SCANNABLE;
        return [LINE];
      }),
    });
    renderPage(api);
    fireEvent.click(await screen.findByText('Atendimento'));
    const dialog = await screen.findByRole('dialog');
    await waitFor(() => expect(within(dialog).getByText('WORKING')).toBeInTheDocument());
    expect(within(dialog).queryByTestId('wa-qr-panel')).not.toBeInTheDocument();
  });
});

// ── 7. Delete ──────────────────────────────────────────────────────────────────

describe('WhatsAppConnectionsPage: delete', () => {
  beforeEach(() => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('DELETEs after the user confirms', async () => {
    const { api } = renderPage(makeApi());
    const deleteButton = await screen.findByLabelText('Remover Atendimento');
    fireEvent.click(deleteButton);

    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith('/api/whatsapp/connections/conn-1'),
    );
  });

  it('does NOT delete when the user cancels the confirm', async () => {
    (window.confirm as any).mockReturnValue(false);
    const { api } = renderPage(makeApi());
    const deleteButton = await screen.findByLabelText('Remover Atendimento');
    fireEvent.click(deleteButton);

    expect(api.delete).not.toHaveBeenCalled();
  });
});
