import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { AdminBilling } from './AdminBilling';
import { SETTINGS, deferred, fakeHttp, renderWithBilling } from '../../test/billing-harness';

afterEach(() => cleanup());

const SUMMARY = {
  mrr: 159, arr: 1908, counted_subscriptions: 3, non_brl_mrr: {},
  counts: { incomplete: 0, trial: 1, active: 2, past_due: 0, grace: 1, canceled: 0, expired: 0 },
  mode: 'test', automations_enabled: false,
};

const PLANS = [{
  id: 'plan-1', nome: 'Corretor', slug: 'corretor', audience: 'individual', trial_days: 7, grace_days: 5,
  ativo: true, product_id: 'prod-1',
  prices: [{ id: 'price-1', plan_id: 'plan-1', billing_cycle: 'monthly', currency: 'BRL', amount_cents: 9900,
    stripe_price_id_test: 'price_abc', stripe_price_id_live: null, ativo: true }],
}];

function openTab(name: string) {
  fireEvent.click(screen.getByRole('tab', { name }));
}

describe('AdminBilling — summary', () => {
  it('shows a skeleton while loading, never an empty state', async () => {
    const pending = deferred<unknown>();
    const http = fakeHttp({ 'GET /api/admin/billing/summary': () => pending.promise });
    render(renderWithBilling(http, <AdminBilling />));
    expect(screen.queryByText(/MRR/)).toBeNull();
    expect(screen.getAllByRole('status').length).toBeGreaterThan(0);
    pending.resolve({ data: SUMMARY });
    expect(await screen.findByText('MRR (receita mensal recorrente)')).toBeTruthy();
    expect(screen.getByText(/R\$\s*159,00/)).toBeTruthy();
    expect(screen.getByText('automações desligadas')).toBeTruthy();
  });

  it('surfaces a load error', async () => {
    const http = fakeHttp({ 'GET /api/admin/billing/summary': () => { throw new Error('[403] Restrito'); } });
    render(renderWithBilling(http, <AdminBilling />));
    expect((await screen.findByRole('alert')).textContent).toContain('403');
  });
});

describe('AdminBilling — gateways', () => {
  function setup(extra: Record<string, (b?: any) => unknown> = {}) {
    const http = fakeHttp({
      'GET /api/admin/billing/summary': () => ({ data: SUMMARY }),
      'GET /api/admin/billing/settings': () => ({ data: SETTINGS }),
      ...extra,
    });
    render(renderWithBilling(http, <AdminBilling />));
    openTab('Gateways');
    return http;
  }

  it('shows webhook URLs and key status, never a value', async () => {
    setup();
    expect(await screen.findByText('https://core.example.com/api/billing/webhook')).toBeTruthy();
    expect(screen.getByText('https://core.example.com/api/billing/webhooks/asaas')).toBeTruthy();
    expect(screen.getAllByText('configurado (variável de ambiente)').length).toBe(2);
    for (const input of screen.getAllByLabelText(/Secret key|Webhook signing secret|Chave de API|Token do webhook/)) {
      expect((input as HTMLInputElement).type).toBe('password');
      expect((input as HTMLInputElement).value).toBe('');
    }
  });

  it('saves a key and clears the field', async () => {
    const http = setup({ 'PUT /api/admin/billing/settings/secrets': () => ({ data: SETTINGS }) });
    const input = (await screen.findByLabelText(/Webhook signing secret/, { selector: '#stripe-test-webhook_secret' })) as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'whsec_new' } });
    const row = input.parentElement!;
    fireEvent.click(within(row).getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(input.value).toBe(''));
    expect(http.calls.find((c) => c.method === 'PUT')?.body).toEqual({
      gateway: 'stripe', mode: 'test', field: 'webhook_secret', value: 'whsec_new',
    });
  });

  it('shows the backend refusal for a wrong-mode key', async () => {
    setup({ 'PUT /api/admin/billing/settings/secrets': () => { throw new Error("Esta chave Stripe é do modo 'test', não 'live'."); } });
    const input = await screen.findByLabelText(/Secret key/, { selector: '#stripe-live-secret_key' });
    fireEvent.change(input, { target: { value: 'sk_test_x' } });
    fireEvent.click(within(input.parentElement!).getByRole('button', { name: 'Salvar' }));
    expect((await screen.findByRole('alert')).textContent).toContain("modo 'test'");
  });

  it('tests the connection and reports the result', async () => {
    const http = setup({
      'POST /api/admin/billing/settings/test-connection': (body: any) =>
        ({ data: body.mode === 'test' ? { ok: true, message: 'Conexão OK.' } : { ok: false, message: 'Falha (401): bad key' } }),
    });
    await screen.findByText('https://core.example.com/api/billing/webhook');
    const buttons = screen.getAllByRole('button', { name: 'Testar conexão' });
    fireEvent.click(buttons[0]);
    fireEvent.click(buttons[1]);
    expect(await screen.findByText('Conexão OK.')).toBeTruthy();
    expect(await screen.findByText('Falha (401): bad key')).toBeTruthy();
    expect(http.calls.filter((c) => c.path.endsWith('test-connection')).map((c) => c.body)).toEqual([
      { gateway: 'stripe', mode: 'test' }, { gateway: 'stripe', mode: 'live' },
    ]);
  });

  it('flips the automation switch', async () => {
    const http = setup({
      'PUT /api/admin/billing/settings': (body: any) => ({ data: { ...SETTINGS, ...body } }),
    });
    const toggle = (await screen.findByLabelText(/Automações de cobrança ativas/)) as HTMLInputElement;
    expect(toggle.checked).toBe(false);
    fireEvent.click(toggle);
    await waitFor(() => expect(http.calls.some((c) => c.method === 'PUT' && (c.body as any).automations_enabled === true)).toBe(true));
  });

  it('warns when ENCRYPTION_KEY is missing', async () => {
    const http = fakeHttp({
      'GET /api/admin/billing/summary': () => ({ data: SUMMARY }),
      'GET /api/admin/billing/settings': () => ({ data: { ...SETTINGS, encryption_configured: false } }),
    });
    render(renderWithBilling(http, <AdminBilling />));
    openTab('Gateways');
    expect((await screen.findByRole('alert')).textContent).toContain('ENCRYPTION_KEY');
  });
});

describe('AdminBilling — plans', () => {
  it('lists prices and creates a new price from a BRL amount', async () => {
    const http = fakeHttp({
      'GET /api/admin/billing/summary': () => ({ data: SUMMARY }),
      'GET /api/admin/billing/plans': () => ({ data: PLANS }),
      'POST /api/admin/billing/plans/plan-1/prices': (body) => ({ data: { id: 'price-2', ...(body as object) } }),
    });
    render(renderWithBilling(http, <AdminBilling />));
    openTab('Planos');
    expect(await screen.findByText('Corretor')).toBeTruthy();
    expect(screen.getByText(/R\$\s*99,00/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Novo valor'), { target: { value: '1.299,90' } });
    fireEvent.click(screen.getByRole('button', { name: 'Definir preço' }));
    await waitFor(() => expect(http.calls.some((c) => c.method === 'POST')).toBe(true));
    expect(http.calls.find((c) => c.method === 'POST')?.body).toEqual({ billing_cycle: 'monthly', amount_cents: 129990 });
  });

  it('refuses a malformed Stripe price id before sending', async () => {
    const http = fakeHttp({
      'GET /api/admin/billing/summary': () => ({ data: SUMMARY }),
      'GET /api/admin/billing/plans': () => ({ data: PLANS }),
    });
    render(renderWithBilling(http, <AdminBilling />));
    openTab('Planos');
    const live = await screen.findByLabelText('Stripe price (produção)');
    fireEvent.change(live, { target: { value: 'prod_123' } });
    const save = within(live.closest('tr')!).getByRole('button', { name: 'Salvar' }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
  });
});

describe('AdminBilling — subscriptions and payments', () => {
  it('lists subscriptions and marks legacy rows read-only', async () => {
    const http = fakeHttp({
      'GET /api/admin/billing/summary': () => ({ data: SUMMARY }),
      'GET /api/admin/billing/subscriptions': () => ({
        data: [
          { id: 's1', org_id: 'o1', status: 'grace', gateway: 'asaas', automation_managed: true,
            amount_cents: 9900, currency: 'BRL', billing_cycle: 'monthly', grace_ends_at: '2026-09-20T00:00:00Z',
            created_at: '2026-09-01', organizations: { id: 'o1', nome: 'Imob A', slug: 'a' }, plans: { id: 'p', nome: 'Corretor' } },
          { id: 's2', org_id: 'o2', status: 'active', gateway: null, automation_managed: false,
            created_at: '2026-01-01', organizations: { id: 'o2', nome: 'Legada', slug: 'l' }, plans: null },
        ],
        total: 2, page: 1, page_size: 50,
      }),
    });
    render(renderWithBilling(http, <AdminBilling />));
    openTab('Assinaturas');
    const managedRow = (await screen.findByText('Imob A')).closest('tr')!;
    expect(within(managedRow).getByText('Carência')).toBeTruthy();
    expect(within(managedRow).getByRole('button', { name: 'Cancelar agora' })).toBeTruthy();
    const legacyRow = screen.getByText('Legada').closest('tr')!;
    expect(within(legacyRow).getByText('legado')).toBeTruthy();
    expect(within(legacyRow).queryByRole('button')).toBeNull();
  });

  it('shows fees and nets, and a pending fee as pending', async () => {
    const http = fakeHttp({
      'GET /api/admin/billing/summary': () => ({ data: SUMMARY }),
      'GET /api/admin/billing/payments': () => ({
        data: [
          { id: 'p1', org_id: 'o1', gateway: 'asaas', gateway_mode: 'live', status: 'paid', billing_method: 'pix',
            currency: 'BRL', gross_cents: 9900, fee_cents: 199, net_cents: 9701, created_at: '2026-09-16',
            organizations: { id: 'o1', nome: 'Imob A' } },
          { id: 'p2', org_id: 'o1', gateway: 'stripe', gateway_mode: 'live', status: 'paid', billing_method: 'card',
            currency: 'BRL', gross_cents: 9900, fee_cents: 0, net_cents: 9900, fee_pending: true, created_at: '2026-09-16',
            organizations: { id: 'o1', nome: 'Imob A' } },
        ],
        page_totals_brl: { gross_cents: 19800, fee_cents: 199, net_cents: 19601 },
        total: 2, page: 1, page_size: 50,
      }),
    });
    render(renderWithBilling(http, <AdminBilling />));
    openTab('Pagamentos');
    expect((await screen.findAllByText(/R\$\s*1,99/)).length).toBe(2); // total card + row
    expect(screen.getByText(/R\$\s*196,01/)).toBeTruthy();
    const pendingRow = screen.getByText('aguardando').closest('tr')!;
    expect(within(pendingRow).getByText('Cartão')).toBeTruthy();
  });
});
