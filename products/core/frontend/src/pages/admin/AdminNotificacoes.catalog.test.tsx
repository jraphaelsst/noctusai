/** Admin Notificações > switches: EVERY live product is on the page — one with no declared kinds says so, and a kind
 *  switch is a cache write (flips at once, rolls back on a refusal). */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfirmProvider } from '@noctusai/lib/components';
import { createNotificationCatalogApi, NotificationCatalogApiProvider } from '../../lib/notificationCatalog';
import { createOwnerLineApi, OwnerLineApiProvider, type OwnerLineHttp } from '../../lib/ownerLine';
import { AdminNotificacoes } from './AdminNotificacoes';

afterEach(cleanup);

const counts = { sent: 0, partial: 0, failed: 0, suppressed: 0, no_recipient: 0 };
const kind = (product: string, k: string, canais: string[] = ['whatsapp']) => ({
  product, kind: k, titulo: `Título ${k}`, descricao: 'd', gatilho: 'g', canais, enabled: true, toggled_at: null,
  registered_at: null, last_seen_at: null, counts_30d: counts, last_dispatch: null, last_sent_at: null,
});
const CATALOG = {
  window_days: 30, sends_truncated: false,
  products: [
    { product: 'core', kinds: [kind('core', 'skill_scout_novo_skill')], enabled_count: 1, total: 1, declared: true },
    { product: 'monica', kinds: [], enabled_count: 0, total: 0, declared: false },
  ],
};

function render_(routes: Record<string, (b?: unknown) => unknown>) {
  const calls: Array<{ method: string; path: string; body?: unknown }> = [];
  const h = (method: string) => async (path: string, body?: unknown) => {
    calls.push({ method, path, body });
    const r = routes[`${method} ${path.split('?')[0]}`];
    if (!r) throw new Error(`no fake route for ${method} ${path}`);
    return r(body);
  };
  const http = { get: h('GET'), post: h('POST'), put: h('PUT'), patch: h('PATCH'), delete: h('DELETE') };
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <NotificationCatalogApiProvider value={createNotificationCatalogApi(http as never)}>
        <OwnerLineApiProvider value={createOwnerLineApi(http as OwnerLineHttp)}>
          <ConfirmProvider><AdminNotificacoes /></ConfirmProvider>
        </OwnerLineApiProvider>
      </NotificationCatalogApiProvider>
    </QueryClientProvider>,
  );
  return calls;
}
const BASE = {
  'GET /api/admin/notifications': () => ({ data: CATALOG }),
  'GET /api/admin/notifications/owner-line': () => ({ data: { configurada: true, instancia: 'x' } }),
  'GET /api/admin/notifications/recipients': () => ({ data: { items: [] } }),
};

describe('catalog covers every live product', () => {
  it('lists a live product that declares nothing, saying so, with its bulk switches disabled', async () => {
    render_(BASE);
    expect(await screen.findByRole('heading', { name: /monica/ })).toBeInTheDocument();
    expect(screen.getByText(/não declara nenhum aviso para o dono/i)).toBeInTheDocument();
    const section = screen.getByRole('heading', { name: /monica/ }).closest('section') as HTMLElement;
    for (const b of section.querySelectorAll('button')) expect(b).toBeDisabled();
  });

  it('shows the WhatsApp-only channel of the skill-scout kind and no e-mail or bell badge', async () => {
    render_(BASE);
    expect(await screen.findByText('Título skill_scout_novo_skill')).toBeInTheDocument();
    expect(screen.getAllByText('WhatsApp').length).toBeGreaterThan(0);
    expect(screen.queryByText('e-mail')).toBeNull();
    expect(screen.queryByText('sino')).toBeNull();
  });

  it('flips a kind at once and rolls it back when the server refuses (never a silent failure)', async () => {
    const calls = render_({
      ...BASE,
      'PATCH /api/admin/notifications/core/skill_scout_novo_skill': () => { throw new Error('boom'); },
    });
    const sw = await screen.findByRole('switch', { name: /Desligar "Título skill_scout_novo_skill"/ });
    fireEvent.click(sw);
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true));
    expect(await screen.findByText(/Não foi possível salvar: boom/)).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: /Desligar "Título skill_scout_novo_skill"/ })).toBeChecked();
  });
});

describe('one owner number', () => {
  it('tells the admin this list is the single owner number every product reads', async () => {
    render_(BASE);
    expect(await screen.findByText(/único cadastro de números do dono/i)).toBeInTheDocument();
  });
});
