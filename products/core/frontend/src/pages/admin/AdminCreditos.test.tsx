/** Admin "Créditos": wallets list, grant dialog (cache write), mode switch, margin and pricing tabs. */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import { fakeHttp, renderWithCredits, WALLET } from '../../test/credits-harness';
import { AdminCreditos } from './AdminCreditos';

afterEach(cleanup);

const ORG = '11111111-1111-1111-1111-111111111111';
const ROW = { ...WALLET, org_id: ORG, org_nome: 'Imobiliária A', org_slug: 'a' };
const PRICING = [{ version: 1, credit_unit_brl: 0.01, margin: 1, fx_buffer_brl: 0.1, iof_rate: 0.035, import_tax_rate: 0,
  simples_rate: 0.06, gateway_fee_rate: 0.0399, effective_from: '2026-01-01T00:00:00Z', notes: 'semente', gross_margin: 0.48 }];

describe('AdminCreditos', () => {
  it('lists wallets with balance and mode', async () => {
    const http = fakeHttp({ 'GET /api/admin/credits/wallets': () => ({ data: [ROW] }) });
    render(renderWithCredits(http, <AdminCreditos />));
    const row = (await screen.findByText('Imobiliária A')).closest('tr')!;
    expect(within(row).getByText('12.500')).toBeInTheDocument();
    expect(within(row).getByText('R$ 125,00')).toBeInTheDocument();
    expect(within(row).getByRole('combobox')).toHaveValue('prepaid');
  });

  it('shows an empty state with no wallets', async () => {
    const http = fakeHttp({ 'GET /api/admin/credits/wallets': () => ({ data: [] }) });
    render(renderWithCredits(http, <AdminCreditos />));
    expect(await screen.findByText(/Nenhuma organização tem carteira/)).toBeInTheDocument();
  });

  it('a grant in US$ posts the reason and writes the new balance into the list', async () => {
    const http = fakeHttp({
      'GET /api/admin/credits/wallets': () => ({ data: [ROW] }),
      [`POST /api/admin/credits/${ORG}/grant`]: () => ({ data: { status: 'applied', credits: 50000, balance_credits: 62500 } }),
    });
    render(renderWithCredits(http, <AdminCreditos />));
    const row = (await screen.findByText('Imobiliária A')).closest('tr')!;
    http.routes['GET /api/admin/credits/wallets'] = () => new Promise(() => {});
    fireEvent.click(within(row).getByRole('button', { name: 'Conceder' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Quantidade'), { target: { value: '100' } });
    fireEvent.change(within(dialog).getByLabelText('Motivo'), { target: { value: 'US$100 de teste' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Conceder' }));
    expect(await screen.findByText('62.500')).toBeInTheDocument();
    const post = http.calls.find((c) => c.method === 'POST')!;
    expect(post.body).toEqual({ reason: 'US$100 de teste', usd: '100' });
  });

  it('switching the mode draws it immediately and sends it', async () => {
    const http = fakeHttp({
      'GET /api/admin/credits/wallets': () => ({ data: [ROW] }),
      [`PUT /api/admin/credits/${ORG}/wallet`]: () => ({ data: { ...WALLET, mode: 'byok' } }),
    });
    render(renderWithCredits(http, <AdminCreditos />));
    const row = (await screen.findByText('Imobiliária A')).closest('tr')!;
    http.routes['GET /api/admin/credits/wallets'] = () => new Promise(() => {});
    fireEvent.change(within(row).getByRole('combobox'), { target: { value: 'byok' } });
    await waitFor(() => expect(within(row).getByRole('combobox')).toHaveValue('byok'));
    expect(http.calls.find((c) => c.method === 'PUT')!.body).toEqual({ mode: 'byok' });
  });

  it('pricing tab shows versions and a new version is drafted then published', async () => {
    const http = fakeHttp({
      'GET /api/admin/credits/wallets': () => ({ data: [] }),
      'GET /api/admin/credits/pricing': () => ({ data: PRICING }),
      'POST /api/admin/credits/pricing': () => ({ data: [{ ...PRICING[0], version: 2, margin: 1.5, gross_margin: 0.58 }, PRICING[0]] }),
    });
    render(renderWithCredits(http, <AdminCreditos />));
    fireEvent.click(screen.getByRole('tab', { name: 'Preços' }));
    expect(await screen.findByText('semente')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Nova versão de preço' }));
    expect(screen.getByText(/não salva/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Markup (1.0 = 100%)'), { target: { value: '1.5' } });
    http.routes['GET /api/admin/credits/pricing'] = () => new Promise(() => {}); // settle refetch never answers
    fireEvent.click(screen.getByRole('button', { name: 'Publicar versão' }));
    expect(await screen.findByText(/v2/)).toBeInTheDocument();
    expect((http.calls.find((c) => c.method === 'POST')!.body as { margin: string }).margin).toBe('1.5');
  });

  it('margin tab shows revenue vs provider cost', async () => {
    const http = fakeHttp({
      'GET /api/admin/credits/wallets': () => ({ data: [] }),
      'GET /api/admin/credits/margin': () => ({ data: {
        window: { from: 'a', to: 'b' },
        totals: { revenue_brl: 100, provider_cost_brl: 40, purchased_brl: 200, granted_brl: 50, gross_margin_brl: 60, gross_margin_pct: 0.6 },
        per_org: [{ org_id: ORG, revenue_brl: 100, provider_cost_brl: 40, gross_margin_brl: 60, gross_margin_pct: 0.6,
          debited_credits: 10000, byok_calls: 0, purchased_brl: 200, granted_brl: 50, refunded_brl: 0,
          per_product: [{ product: 'erp-imobiliario', revenue_brl: 100, provider_cost_brl: 40, gross_margin_brl: 60,
            gross_margin_pct: 0.6, debited_credits: 10000, byok_calls: 0 }] }],
      } }),
    });
    render(renderWithCredits(http, <AdminCreditos />));
    fireEvent.click(screen.getByRole('tab', { name: 'Margem' }));
    expect(await screen.findByText('erp-imobiliario')).toBeInTheDocument();
    expect(screen.getAllByText('60%').length).toBeGreaterThan(0);
  });
});
