import { describe, it, expect, afterEach, vi, beforeAll } from 'vitest';
import { render, screen, cleanup, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FinanceShell, FINANCE_SECTIONS, financeSectionFromPath, financeSectionPath } from './FinanceShell';
import { mockRechartsLayout } from '../design-system/charts/_recharts-test-utils';
import { baseRoutes, hooksFor, makeRoutedApi, ok, page, wrapperFor } from './testUtils';

beforeAll(() => mockRechartsLayout());
afterEach(cleanup);

function routes() {
  return makeRoutedApi({
    ...baseRoutes(),
    'GET /api/finance/accounts/acc-bank/balance': ok({ account_id: 'acc-bank', on: 'x', opening_balance_cents: 0, movement_cents: 0, balance_cents: 1000 }),
    'GET /api/finance/accounts/acc-gw/balance': ok({ account_id: 'acc-gw', on: 'x', opening_balance_cents: 0, movement_cents: 0, balance_cents: 0 }),
    'GET /api/finance/reports/cashflow': ok({ from: '', to: '', account_id: null, opening_balance_cents: 0, buckets: [], totals: { realized_in_cents: 0, realized_out_cents: 0, projected_in_cents: 0, projected_out_cents: 0 }, closing_realized_balance_cents: 0, closing_projected_balance_cents: 0 }),
    'GET /api/finance/reports/aging': ok({ as_of: '', counterparties: [], totals: { buckets: { d1_30: 0, d31_60: 0, d61_90: 0, d90_plus: 0 }, total_cents: 0 } }),
    'GET /api/finance/reports/dre': ok({ from: '', to: '', months: [], view: 'statement', title: 'Demonstração do Resultado do Exercício (DRE)', standard: 'nbc_tg_1002', tax_regime: 'simples', trailing_12m_gross_revenue_cents: 0, net_result_cents: 0, unclassified: { net_cents: 0, by_month: {}, detail: [], included_in_net_result: false }, help: {}, warnings: [], accountant_alerts: [], statement: [] }),
    'GET /api/finance/reports/simples-base': ok({ from: '', to: '', tax_regime: 'simples', invoice_basis_from: '2027-01-01', crosses_basis_boundary: false, months: [], totals: { sales_cents: 0, interest_cents: 0, refunds_cents: 0, chargebacks_cents: 0, base_cents: 0 }, basis_note: '', notes: [], warnings: [] }),
    'GET /api/finance/entries': page([]),
    'GET /api/finance/statements': page([]),
    'GET /api/finance/recurrences': ok([]),
    'GET /api/finance/accountant-checklist': ok({ generated_at: '', tax_regime: 'simples', tax_regime_informed: true, das_split_irpj_csll: false, provisional_choices: [], confirmed_choices: [], open_questions: [], exports: [], disclaimer: '' }),
    'GET /api/finance/dre-settings': ok({ persisted: false, tax_regime: 'simples', tax_regime_prefilled: false, das_split_irpj_csll: false, das_irpj_csll_share_bps: 0, choices: Object.fromEntries([['gateway_fee_line', 'selling_expenses'], ['anticipation_fee_line', 'financial_expenses'], ['chargeback_line', 'deductions'], ['chargeback_fee_line', 'selling_expenses'], ['installment_interest_line', 'gross_revenue']].map(([k, v]) => [k, { value: v, default: v, provisional: true, confirmed_by: null, confirmed_at: null, note: null }])) }),
  });
}

describe('FinanceShell', () => {
  it('exposes the eight sections in order and maps URL segments both ways', () => {
    expect(FINANCE_SECTIONS.map((s) => s.key)).toEqual(['overview', 'receivable', 'payable', 'cashflow', 'dre', 'reconciliation', 'registers', 'accountant']);
    expect(financeSectionFromPath('receber')).toBe('receivable');
    expect(financeSectionFromPath('/contador/')).toBe('accountant');
    expect(financeSectionFromPath('')).toBe('overview');
    expect(financeSectionFromPath('qualquer-coisa')).toBe('overview');
    for (const s of FINANCE_SECTIONS) expect(financeSectionFromPath(financeSectionPath(s.key))).toBe(s.key);
  });

  it('navigates between pages (uncontrolled) and marks the current one', async () => {
    const user = userEvent.setup();
    render(<FinanceShell hooks={hooksFor(routes())} isAdmin now={new Date(2026, 9, 14)} />, { wrapper: wrapperFor() });
    const nav = screen.getByRole('navigation', { name: 'Financeiro' });
    expect(within(nav).getByRole('button', { name: 'Visão geral' })).toHaveAttribute('aria-current', 'page');
    expect(await screen.findByRole('heading', { name: 'Visão geral do financeiro' })).toBeInTheDocument();

    await user.click(within(nav).getByRole('button', { name: 'Contas a pagar' }));
    expect(await screen.findByRole('heading', { name: 'Contas a pagar', level: 2 })).toBeInTheDocument();
    expect(within(nav).getByRole('button', { name: 'Contas a pagar' })).toHaveAttribute('aria-current', 'page');

    await user.click(within(nav).getByRole('button', { name: 'DRE' }));
    expect(await screen.findByRole('heading', { name: 'Demonstração do Resultado do Exercício (DRE)' })).toBeInTheDocument();

    await user.click(within(nav).getByRole('button', { name: 'Conciliação' }));
    expect(await screen.findByRole('heading', { name: 'Conciliação bancária' })).toBeInTheDocument();
  });

  it('controlled mode reports changes and renders the given section', async () => {
    const user = userEvent.setup();
    const onSectionChange = vi.fn();
    render(<FinanceShell hooks={hooksFor(routes())} section="cashflow" onSectionChange={onSectionChange} now={new Date(2026, 9, 14)} />, { wrapper: wrapperFor() });
    expect(await screen.findByRole('heading', { name: 'Fluxo de caixa' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Inadimplência' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Contas a receber' }));
    expect(onSectionChange).toHaveBeenCalledWith('receivable');
    // controlled: the section did not change by itself
    expect(screen.getByRole('button', { name: 'Fluxo de caixa' })).toHaveAttribute('aria-current', 'page');
  });

  it('Cadastros has accounts, categories, cost centers and recurrences tabs', async () => {
    const user = userEvent.setup();
    render(<FinanceShell hooks={hooksFor(routes())} section="registers" isAdmin />, { wrapper: wrapperFor() });
    const tabs = screen.getByRole('tablist', { name: 'Cadastros' });
    expect(within(tabs).getAllByRole('tab').map((t) => t.textContent)).toEqual(['Contas', 'Categorias', 'Centros de custo', 'Recorrências']);
    expect(await screen.findByRole('heading', { name: 'Contas', level: 2 })).toBeInTheDocument();
    await user.click(within(tabs).getByRole('tab', { name: 'Categorias' }));
    expect(await screen.findByRole('columnheader', { name: 'Linha do DRE' })).toBeInTheDocument();
    await user.click(within(tabs).getByRole('tab', { name: 'Centros de custo' }));
    expect(await screen.findByRole('heading', { name: 'Centros de custo', level: 2 })).toBeInTheDocument();
    await user.click(within(tabs).getByRole('tab', { name: 'Recorrências' }));
    expect(await screen.findByText(/Nenhuma recorrência/)).toBeInTheDocument();
  });

  it('Contador has checklist, DRE setup, Simples base and exports', async () => {
    const user = userEvent.setup();
    render(<FinanceShell hooks={hooksFor(routes())} section="accountant" isAdmin now={new Date(2026, 9, 14)} />, { wrapper: wrapperFor() });
    const tabs = screen.getByRole('tablist', { name: 'Contador' });
    expect(await screen.findByRole('heading', { name: 'Para o seu contador' })).toBeInTheDocument();
    await user.click(within(tabs).getByRole('tab', { name: 'Como o DRE é montado' }));
    expect(await screen.findByRole('heading', { name: 'Como o seu DRE é montado' })).toBeInTheDocument();
    await user.click(within(tabs).getByRole('tab', { name: 'Base do Simples' }));
    expect(await screen.findByRole('heading', { name: 'Base do Simples Nacional' })).toBeInTheDocument();
    await user.click(within(tabs).getByRole('tab', { name: 'Exportações' }));
    expect(await screen.findByRole('heading', { name: 'Exportações' })).toBeInTheDocument();
  });

  it('overview deep links jump to the right section', async () => {
    const user = userEvent.setup();
    render(<FinanceShell hooks={hooksFor(routes())} now={new Date(2026, 9, 14)} />, { wrapper: wrapperFor() });
    await user.click(await screen.findByRole('button', { name: 'Ver fluxo de caixa' }));
    expect(await screen.findByRole('heading', { name: 'Fluxo de caixa' })).toBeInTheDocument();
  });
});
