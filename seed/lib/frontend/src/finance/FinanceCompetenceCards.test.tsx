import { describe, it, expect, afterEach, beforeAll } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FinanceShell } from './FinanceShell';
import { mockRechartsLayout } from '../design-system/charts/_recharts-test-utils';
import { baseRoutes, entry, hooksFor, makeRoutedApi, ok, page, wrapperFor } from './testUtils';

beforeAll(() => mockRechartsLayout());
afterEach(cleanup);

const CASH = ok({
  from: '', to: '', account_id: null, opening_balance_cents: 0,
  buckets: [{ realized_in_cents: 0, realized_out_cents: 0 }],
  totals: { realized_in_cents: 0, realized_out_cents: 0, projected_in_cents: 0, projected_out_cents: 0 },
  closing_realized_balance_cents: 0, closing_projected_balance_cents: 0,
});
const AGING = ok({ as_of: '', counterparties: [], totals: { buckets: { d1_30: 0, d31_60: 0, d61_90: 0, d90_plus: 0 }, total_cents: 0 } });

const item = (key: string, cents: number, detail: { name: string; cents: number }[] = []) => ({
  key, kind: 'line', label: key, sign: 1, cents, by_month: {}, empty: cents === 0,
  detail: detail.map((d) => ({ category_id: d.name, name: d.name, cents: d.cents, by_month: {}, behavior: null, source: null })),
});
const dre = (over: Record<string, unknown> = {}, statement: unknown[] = []) =>
  ok({
    from: '', to: '', months: [], view: 'statement', title: 'DRE', standard: 'nbc_tg_1002', tax_regime: 'unknown',
    trailing_12m_gross_revenue_cents: 0, net_result_cents: 0,
    unclassified: { net_cents: 0, by_month: {}, detail: [], included_in_net_result: false },
    help: {}, warnings: [], accountant_alerts: [], statement, ...over,
  });

const STATEMENT = [
  item('gross_revenue', 527_400, [{ name: 'Assinaturas', cents: 79_400 }, { name: 'Projetos', cents: 448_000 }]),
  item('deductions', 0),
  item('cost_of_sales', 121_000),
  item('administrative_expenses', 88_000),
];

function routes(over: Record<string, unknown> = {}) {
  return makeRoutedApi({
    ...baseRoutes(),
    'GET /api/finance/accounts/acc-bank/balance': ok({ account_id: 'acc-bank', on: 'x', opening_balance_cents: 0, movement_cents: 0, balance_cents: 1000 }),
    'GET /api/finance/accounts/acc-gw/balance': ok({ account_id: 'acc-gw', on: 'x', opening_balance_cents: 0, movement_cents: 0, balance_cents: 0 }),
    'GET /api/finance/reports/cashflow': CASH,
    'GET /api/finance/reports/aging': AGING,
    'GET /api/finance/entries': page([entry({ source: 'recurrence' })]),
    'GET /api/finance/reports/dre': dre({}, STATEMENT),
    ...over,
  } as never);
}

const NOW = new Date(2026, 10, 7);

describe('competence cards (opt-in)', () => {
  it('are absent by default (today behaviour) and do not call the DRE', async () => {
    const api = routes();
    render(<FinanceShell hooks={hooksFor(api)} isAdmin now={NOW} />, { wrapper: wrapperFor() });
    await screen.findByRole('heading', { name: 'Visão geral do financeiro' });
    expect(screen.queryByText('De onde veio a receita do mês')).not.toBeInTheDocument();
    expect((api.get as unknown as { mock: { calls: unknown[][] } }).mock.calls.some(([p]) => String(p).includes('/reports/dre'))).toBe(false);
  });

  it('split revenue by category and NEVER estimate tax: result is "—" with "depende do contador"', async () => {
    render(<FinanceShell hooks={hooksFor(routes())} isAdmin now={NOW} competenceCards />, { wrapper: wrapperFor() });
    expect(await screen.findByText('De onde veio a receita do mês')).toBeInTheDocument();
    expect(await screen.findByRole('img', { name: /Projetos 85%, Assinaturas 15%/ })).toBeInTheDocument();
    expect(await screen.findByText('depende do contador')).toBeInTheDocument();
    const result = screen.getByText('Resultado', { selector: 'dt' }).nextElementSibling;
    expect(result).toHaveTextContent('—');
  });

  it('show the result once the regime is informed and tax is booked', async () => {
    const st = [...STATEMENT.slice(0, 1), item('deductions', 30_000), ...STATEMENT.slice(2)];
    render(<FinanceShell hooks={hooksFor(routes({ 'GET /api/finance/reports/dre': dre({ tax_regime: 'simples', net_result_cents: 288_400 }, st) }))} isAdmin now={NOW} competenceCards />, { wrapper: wrapperFor() });
    const dt = await screen.findByText('Resultado', { selector: 'dt' });
    expect(dt.nextElementSibling).toHaveTextContent(/2\.884,00/);
    expect(screen.queryByText('depende do contador')).not.toBeInTheDocument();
  });

  it('show a visible retryable error (not an empty state) when the DRE fails', async () => {
    const api = routes({ 'GET /api/finance/reports/dre': () => { throw new Error('boom'); } });
    render(<FinanceShell hooks={hooksFor(api)} isAdmin now={NOW} competenceCards />, { wrapper: wrapperFor() });
    expect((await screen.findAllByText('Não foi possível carregar o resultado do mês.')).length).toBeGreaterThan(0);
    expect(screen.queryByText('Nenhuma receita lançada neste mês.')).not.toBeInTheDocument();
  });
});

describe('overview empty state + footer seams', () => {
  const EMPTY = { title: 'Financeiro vazio', description: 'Comece cadastrando a conta.' };
  it('shows the first-use state only once loaded with no account and no movement, with working actions', async () => {
    const user = userEvent.setup();
    const api = routes({
      'GET /api/finance/accounts': ok([]),
      'GET /api/finance/reports/cashflow': ok({ from: '', to: '', account_id: null, opening_balance_cents: 0, buckets: [], totals: { realized_in_cents: 0, realized_out_cents: 0, projected_in_cents: 0, projected_out_cents: 0 }, closing_realized_balance_cents: 0, closing_projected_balance_cents: 0 }),
    });
    render(<FinanceShell hooks={hooksFor(api)} isAdmin now={NOW} overviewEmptyState={EMPTY} overviewFooter={<p>RODAPÉ</p>} />, { wrapper: wrapperFor() });
    expect(await screen.findByRole('heading', { name: 'Financeiro vazio' })).toBeInTheDocument();
    expect(screen.getByText('RODAPÉ')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Importar um extrato (OFX)' }));
    expect(await screen.findByRole('button', { name: 'Conciliação' })).toHaveAttribute('aria-current', 'page');
  });

  it('keeps the normal overview (plus footer) when there is data', async () => {
    render(<FinanceShell hooks={hooksFor(routes())} isAdmin now={NOW} overviewEmptyState={EMPTY} overviewFooter={<p>RODAPÉ</p>} />, { wrapper: wrapperFor() });
    expect(await screen.findByText('Saldo total das contas')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Financeiro vazio' })).not.toBeInTheDocument();
    expect(screen.getByText('RODAPÉ')).toBeInTheDocument();
  });
});

describe('Origem column (opt-in)', () => {
  it('is absent by default and shows how the entry got in when asked', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<FinanceShell hooks={hooksFor(routes())} isAdmin section="receivable" now={NOW} />, { wrapper: wrapperFor() });
    await screen.findByText('Pedido #100');
    expect(screen.queryByRole('columnheader', { name: 'Origem' })).not.toBeInTheDocument();
    rerender(<FinanceShell hooks={hooksFor(routes())} isAdmin section="receivable" now={NOW} showEntryOrigin />);
    expect(await screen.findByRole('columnheader', { name: 'Origem' })).toBeInTheDocument();
    expect(await screen.findByText('Recorrência')).toBeInTheDocument();
    void user;
  });
});
