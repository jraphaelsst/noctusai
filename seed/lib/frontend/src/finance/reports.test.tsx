import { describe, it, expect, afterEach, beforeAll } from 'vitest';
import { render, screen, cleanup, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FinanceOverview } from './FinanceOverview';
import { CashflowReport } from './CashflowReport';
import { AgingReport } from './AgingReport';
import { ApiError } from '../api';
import { mockRechartsLayout } from '../design-system/charts/_recharts-test-utils';
import { baseRoutes, entry, hooksFor, makeRoutedApi, ok, page, wrapperFor } from './testUtils';
import type { AgingReportData, CashflowReportData } from './types';

beforeAll(() => mockRechartsLayout());
afterEach(cleanup);

const NOW = new Date(2026, 9, 14);
const nbsp = (s: string) => s.replace(/ /g, ' ');

const CASHFLOW: CashflowReportData = {
  from: '2026-10-01', to: '2027-03-31', account_id: null, opening_balance_cents: 100_000,
  buckets: [
    { month: '2026-10', realized_in_cents: 50_000, realized_out_cents: 20_000, projected_in_cents: 30_000, projected_out_cents: 10_000 },
    { month: '2026-11', realized_in_cents: 0, realized_out_cents: 0, projected_in_cents: 40_000, projected_out_cents: 5_000 },
  ],
  totals: { realized_in_cents: 50_000, realized_out_cents: 20_000, projected_in_cents: 70_000, projected_out_cents: 15_000 },
  closing_realized_balance_cents: 130_000, closing_projected_balance_cents: 185_000,
};
const AGING: AgingReportData = {
  as_of: '2026-10-14',
  counterparties: [
    { counterparty_name: 'Maria', counterparty_doc: '***.456.789-**', buckets: { d1_30: 10_000, d31_60: 5_000, d61_90: 0, d90_plus: 0 }, total_cents: 15_000, entries: 2, oldest_due_date: '2026-08-20' },
  ],
  totals: { buckets: { d1_30: 10_000, d31_60: 5_000, d61_90: 0, d90_plus: 0 }, total_cents: 15_000 },
};

function overviewApi(over: Record<string, unknown> = {}) {
  return makeRoutedApi({
    ...baseRoutes(),
    'GET /api/finance/accounts/acc-bank/balance': ok({ account_id: 'acc-bank', on: 'x', opening_balance_cents: 0, movement_cents: 0, balance_cents: 250_000 }),
    'GET /api/finance/accounts/acc-gw/balance': ok({ account_id: 'acc-gw', on: 'x', opening_balance_cents: 0, movement_cents: 0, balance_cents: 50_000 }),
    'GET /api/finance/reports/cashflow': ok(CASHFLOW),
    'GET /api/finance/reports/aging': ok(AGING),
    'GET /api/finance/entries': page([entry({ direction: 'payable', overdue: true, amount_cents: 8_000, settled_cents: 3_000 })], { total: 1 }),
    ...over,
  });
}

describe('FinanceOverview', () => {
  it('skeletons first, then totals from each source', async () => {
    const api = overviewApi();
    render(<FinanceOverview hooks={hooksFor(api)} now={NOW} />, { wrapper: wrapperFor() });
    expect(screen.getAllByRole('status', { name: /Carregando/ }).length).toBeGreaterThan(0);
    await screen.findByText(nbsp('R$ 3.000,00')); // 250k + 50k cents
    const tiles = document.body.textContent!.replace(/ /g, ' ');
    expect(tiles).toContain('R$ 700,00'); // to receive (projected_in total)
    expect(tiles).toContain('R$ 150,00'); // to pay
    expect(tiles).toContain('R$ 300,00'); // month result: 50k − 20k
    expect(tiles).toContain('R$ 150,00'); // overdue AR (aging total)
    expect(tiles).toContain('R$ 50,00'); // overdue AP remaining 8k − 3k
    expect(api.get).toHaveBeenCalledWith('/api/finance/reports/cashflow', { from: '2026-10-01', to: '2027-03-31' });
  });

  it('one failing report does not blank the page: it names the failure and offers retry', async () => {
    const user = userEvent.setup();
    let fail = true;
    const api = overviewApi({ 'GET /api/finance/reports/aging': () => (fail ? Promise.reject(new ApiError(500, 'x')) : ok(AGING)) });
    render(<FinanceOverview hooks={hooksFor(api)} now={NOW} />, { wrapper: wrapperFor() });
    const alert = await screen.findByText(/atrasados a receber/);
    expect(screen.getByText(/Saldo total das contas/)).toBeInTheDocument();
    expect(await screen.findByText(nbsp('R$ 3.000,00'))).toBeInTheDocument();
    fail = false;
    await user.click(within(alert.closest('[role="alert"]') as HTMLElement).getByRole('button', { name: 'Tentar novamente' }));
    await screen.findAllByText(nbsp('R$ 150,00'));
    expect(screen.queryByText(/atrasados a receber/)).not.toBeInTheDocument();
  });

  it('empty store: no accounts', async () => {
    const api = overviewApi({ 'GET /api/finance/accounts': ok([]) });
    render(<FinanceOverview hooks={hooksFor(api)} now={NOW} />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Nenhuma conta cadastrada/)).toBeInTheDocument();
  });

  it('partial overdue-payable list is labelled as partial', async () => {
    const api = overviewApi({ 'GET /api/finance/entries': page([entry({ direction: 'payable' })], { total: 250 }) });
    render(<FinanceOverview hooks={hooksFor(api)} now={NOW} />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/mostrando 1 de 250 contas/)).toBeInTheDocument();
  });
});

describe('CashflowReport', () => {
  it('renders opening/closing, per-month table with totals, defaults to the current month + 5', async () => {
    const api = makeRoutedApi({ ...baseRoutes(), 'GET /api/finance/reports/cashflow': ok(CASHFLOW) });
    render(<CashflowReport hooks={hooksFor(api)} now={NOW} />, { wrapper: wrapperFor() });
    const table = await screen.findByRole('table');
    expect(within(table).getByText('out/2026')).toBeInTheDocument();
    expect(within(table).getByText('nov/2026')).toBeInTheDocument();
    expect(within(table).getByText('Total')).toBeInTheDocument();
    expect(document.body.textContent!.replace(/ /g, ' ')).toContain('R$ 1.850,00');
    expect(api.get).toHaveBeenCalledWith('/api/finance/reports/cashflow', { from: '2026-10-01', to: '2027-03-31', account_id: '' });
  });

  it('changing the account refetches and keeps the table on screen meanwhile', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ ...baseRoutes(), 'GET /api/finance/reports/cashflow': ok(CASHFLOW) });
    render(<CashflowReport hooks={hooksFor(api)} now={NOW} />, { wrapper: wrapperFor() });
    await screen.findByRole('table');
    api.route('GET /api/finance/reports/cashflow', () => new Promise(() => {}));
    await user.selectOptions(screen.getByLabelText('Conta'), 'acc-gw');
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.queryByRole('status', { name: 'Carregando' })).not.toBeInTheDocument();
    expect(api.get).toHaveBeenLastCalledWith('/api/finance/reports/cashflow', expect.objectContaining({ account_id: 'acc-gw' }));
  });

  it('empty period and error states', async () => {
    const api = makeRoutedApi({
      ...baseRoutes(),
      'GET /api/finance/reports/cashflow': ok({ ...CASHFLOW, buckets: [], totals: { realized_in_cents: 0, realized_out_cents: 0, projected_in_cents: 0, projected_out_cents: 0 } }),
    });
    render(<CashflowReport hooks={hooksFor(api)} now={NOW} />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Sem movimentação no período/)).toBeInTheDocument();
    cleanup();
    const bad = makeRoutedApi({ ...baseRoutes(), 'GET /api/finance/reports/cashflow': () => Promise.reject(new ApiError(500, 'caiu')) });
    render(<CashflowReport hooks={hooksFor(bad)} now={NOW} />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
  });
});

describe('AgingReport', () => {
  it('shows buckets per customer and totals', async () => {
    const api = makeRoutedApi({ 'GET /api/finance/reports/aging': ok(AGING) });
    render(<AgingReport hooks={hooksFor(api)} />, { wrapper: wrapperFor() });
    expect(await screen.findByText('Maria')).toBeInTheDocument();
    expect(screen.getByText('***.456.789-**')).toBeInTheDocument();
    expect(screen.getByText('31 a 60 dias')).toBeInTheDocument();
    expect(screen.getAllByText(nbsp('R$ 150,00')).length).toBeGreaterThanOrEqual(2);
  });
  it('nothing overdue', async () => {
    const api = makeRoutedApi({ 'GET /api/finance/reports/aging': ok({ ...AGING, counterparties: [], totals: { buckets: AGING.totals.buckets, total_cents: 0 } }) });
    render(<AgingReport hooks={hooksFor(api)} />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Tudo em dia/)).toBeInTheDocument();
  });
  it('passes the as-of date and surfaces errors with retry', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ 'GET /api/finance/reports/aging': () => Promise.reject(new ApiError(500, 'x')) });
    render(<AgingReport hooks={hooksFor(api)} />, { wrapper: wrapperFor() });
    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument();
    api.route('GET /api/finance/reports/aging', ok(AGING));
    await user.click(screen.getByRole('button', { name: 'Tentar novamente' }));
    await screen.findByText('Maria');
    await user.type(screen.getByLabelText(/Posição em/), '2026-09-30');
    expect(api.get).toHaveBeenLastCalledWith('/api/finance/reports/aging', { as_of: '2026-09-30' });
  });
});
