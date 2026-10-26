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
import { ConfirmProvider } from '../confirm';
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
      <ConfirmProvider>
        <WhatsAppConnectionsPage hooks={hooks} {...props} />
      </ConfirmProvider>
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
  it('DELETEs after the user confirms', async () => {
    const { api } = renderPage(makeApi());
    const deleteButton = await screen.findByLabelText('Remover Atendimento');
    fireEvent.click(deleteButton);
    fireEvent.click(within(await screen.findByTestId('confirm-dialog')).getByRole('button', { name: 'Excluir' }));

    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith('/api/whatsapp/connections/conn-1'),
    );
  });

  it('does NOT delete when the user cancels the confirm', async () => {
    const { api } = renderPage(makeApi());
    const deleteButton = await screen.findByLabelText('Remover Atendimento');
    fireEvent.click(deleteButton);
    fireEvent.click(within(await screen.findByTestId('confirm-dialog')).getByRole('button', { name: 'Cancelar' }));

    expect(api.delete).not.toHaveBeenCalled();
  });
});

// ── 8. App switch / borrowed session / purge ───────────────────────────────────

describe('WhatsAppConnectionsPage: per-app switch', () => {
  const withLine = (extra: Partial<WhatsAppConnectionLine>, over: Record<string, any> = {}) =>
    makeApi({
      get: vi.fn(async (path: string) => {
        if (path.endsWith('/status')) return STATUS_UNPAIRED;
        if (path.endsWith('/qr')) return QR_SCANNABLE;
        return [{ ...LINE, app_enabled: true, session_role: 'owner', ...extra }];
      }),
      ...over,
    });

  it('draws no switch on a backend that predates it', async () => {
    renderPage(makeApi());
    await screen.findByText('Atendimento');
    expect(screen.queryByTestId('wa-enabled-conn-1')).not.toBeInTheDocument();
  });

  it('PUTs /enabled and flips the switch on the click, before the server answers', async () => {
    let release!: (line: WhatsAppConnectionLine) => void;
    const api = withLine({}, { put: vi.fn(() => new Promise((r) => { release = r as any; })) });
    renderPage(api);
    const sw = await screen.findByTestId('wa-enabled-conn-1');
    expect(sw).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(sw);
    await waitFor(() => expect(screen.getByTestId('wa-enabled-conn-1')).toHaveAttribute('aria-checked', 'false'));
    expect(api.put).toHaveBeenCalledWith('/api/whatsapp/connections/conn-1/enabled', { enabled: false });
    expect(screen.getByTestId('wa-off-conn-1')).toBeInTheDocument();
    release({ ...LINE, app_enabled: false, session_role: 'owner' });
  });

  it('puts the switch back when the server refuses', async () => {
    const api = withLine({}, { put: vi.fn(async () => { throw new Error('boom'); }) });
    renderPage(api);
    const sw = await screen.findByTestId('wa-enabled-conn-1');
    fireEvent.click(sw);
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByTestId('wa-enabled-conn-1')).toHaveAttribute('aria-checked', 'true'));
  });

  it('marks a borrowed line and disables every session control in its detail', async () => {
    renderPage(withLine({ session_role: 'borrower' }));
    expect(await screen.findByTestId('wa-borrower-conn-1')).toHaveTextContent('Sessão compartilhada');
    fireEvent.click(screen.getByText('Atendimento'));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByTestId('wa-borrowed-note')).toBeInTheDocument();
    expect(within(dialog).queryByTestId('wa-qr-panel')).not.toBeInTheDocument();
    for (const name of ['Iniciar', 'Reiniciar', 'Desconectar', /Recuperar conexão/, 'Reenviar configuração']) {
      expect(within(dialog).getByRole('button', { name })).toBeDisabled();
    }
  });
});

describe('WhatsAppConnectionsPage: purge', () => {
  const offLine = () =>
    makeApi({
      get: vi.fn(async (path: string) => {
        if (path.endsWith('/status')) return STATUS_UNPAIRED;
        if (path.endsWith('/qr')) return QR_SCANNABLE;
        return [{ ...LINE, app_enabled: false, session_role: 'owner' }];
      }),
      post: vi.fn(async () => ({ connection_id: 'conn-1', chats_deleted: 2, messages_deleted: 5, extra: { leads_deleted: 1 } })),
    });

  it('offers the purge only while the app is off', async () => {
    renderPage(makeApi({
      get: vi.fn(async (path: string) => (path.endsWith('/status') ? STATUS_UNPAIRED : path.endsWith('/qr') ? QR_SCANNABLE : [{ ...LINE, app_enabled: true }])),
    }));
    fireEvent.click(await screen.findByText('Atendimento'));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).queryByRole('button', { name: 'Apagar dados de teste' })).not.toBeInTheDocument();
  });

  it('arms only when the label is typed back, then POSTs it and shows the counts', async () => {
    const api = offLine();
    renderPage(api);
    fireEvent.click(await screen.findByText('Atendimento'));
    fireEvent.click(await screen.findByRole('button', { name: 'Apagar dados de teste' }));
    const confirmInput = await screen.findByLabelText(/Digite/);
    const submit = screen.getByRole('button', { name: 'Apagar dados' });
    expect(submit).toBeDisabled();
    fireEvent.change(confirmInput, { target: { value: 'Atendiment' } });
    expect(submit).toBeDisabled();
    fireEvent.change(confirmInput, { target: { value: 'Atendimento' } });
    expect(submit).toBeEnabled();
    fireEvent.click(submit);
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/whatsapp/connections/conn-1/purge', { confirm: 'Atendimento' }),
    );
    expect(await screen.findByTestId('wa-purge-done')).toHaveTextContent('2 conversas e 5 mensagens apagadas');
  });
});
