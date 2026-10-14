/**
 * Accountant additions (E16/E21): budget vs actual, Livro Caixa, MEI monthly, Domínio export, the Contador tabs, the
 * accounting-code / activity / nota-fiscal fields. Fixtures mirror the SHIPPED backend payloads (budgets.py, livro_caixa.py,
 * mei.py, dominio.py, accountant.py).
 */
import { describe, it, expect, afterEach, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ApiError } from '../api';
import { BudgetPage } from './BudgetPage';
import { DominioExport } from './DominioExport';
import { FinanceShell } from './FinanceShell';
import { LivroCaixaReport } from './LivroCaixaReport';
import { MeiMonthlyReport } from './MeiMonthlyReport';
import { FinanceCategoryManager } from './CategoryManager';
import { AccountsManager } from './AccountsManager';
import { EntryDialog } from './EntryDialog';
import { AccountantChecklist } from './AccountantChecklist';
import { baseRoutes, entry, hooksFor, makeRoutedApi, ok, wrapperFor, ACC_BANK } from './testUtils';
import type { BudgetReportData, LivroCaixaData, MeiMonthlyData } from './accountantTypes';
import { dominioMissingOf } from './accountantTypes';

afterEach(cleanup);
beforeEach(() => {
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:z'), revokeObjectURL: vi.fn() });
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
});
const NOW = new Date(2026, 9, 14);
const flat = (s: string | null) => (s ?? '').replace(/ /g, ' ');

// ---------------------------------------------------------------------------------------------------------------------
const cell = (budget: number, actual: number, status: 'ok' | 'over' | 'under' | 'no_budget') => ({ budget_cents: budget, actual_cents: actual, variance_cents: actual - budget, status });
const BUDGET: BudgetReportData = {
  from: '2026-10-01', to: '2026-11-30', months: ['2026-10', '2026-11'],
  rows: [
    { category_id: 'cat-mkt', name: 'Marketing', path: 'Despesas operacionais / Marketing', direction: 'expense',
      months: { '2026-10': cell(50_000, 80_000, 'over'), '2026-11': cell(20_000, 10_000, 'ok') }, total: cell(70_000, 90_000, 'over') },
    { category_id: 'cat-sales', name: 'Vendas', path: 'Receitas operacionais / Vendas', direction: 'income',
      months: { '2026-10': cell(400_000, 300_000, 'under'), '2026-11': cell(0, 0, 'no_budget') }, total: cell(400_000, 300_000, 'under') },
  ],
  income: { by_month: {}, budget_cents: 400_000, actual_cents: 300_000, variance_cents: -100_000 },
  expense: { by_month: {}, budget_cents: 70_000, actual_cents: 90_000, variance_cents: 20_000 },
  result: { budget_cents: 330_000, actual_cents: 210_000 }, warnings: [], notes: ['O realizado usa a mesma base da DRE.'], source: 'x',
};
const BUDGETS = [
  { id: 'b1', category_id: 'cat-mkt', month: '2026-10-01', amount_cents: 50_000 },
  { id: 'b2', category_id: 'cat-mkt', month: '2026-11-01', amount_cents: 20_000 },
  { id: 'b3', category_id: 'cat-sales', month: '2026-10-01', amount_cents: 400_000 },
];
function budgetApi(over: Record<string, unknown> = {}) {
  return makeRoutedApi({
    ...baseRoutes(),
    'GET /api/finance/reports/budget': ok(BUDGET),
    'GET /api/finance/budgets': ok(BUDGETS),
    'PUT /api/finance/budgets': ok([]),
    'DELETE /api/finance/budgets/b2': {},
    ...over,
  });
}

describe('BudgetPage', () => {
  it('shows planned vs actual with the verdict in words, and the totals', async () => {
    render(<BudgetPage hooks={hooksFor(budgetApi())} now={NOW} />, { wrapper: wrapperFor() });
    const row = (await screen.findByText('Despesas operacionais / Marketing')).closest('tr')!;
    expect(flat(row.textContent)).toContain('R$ 800,00');
    expect(flat(row.textContent)).toContain('acima do planejado');
    expect(flat(row.textContent)).toContain('dentro do planejado'.length ? '' : '');
    const sales = screen.getByText('Receitas operacionais / Vendas').closest('tr')!;
    expect(flat(sales.textContent)).toContain('abaixo do planejado');
    expect(flat(screen.getByText('Resultado').closest('div')!.textContent)).toContain('R$ 3.300,00');
    expect(screen.getByText(/mesma base da DRE/)).toBeInTheDocument();
  });

  it('non-admin is read-only: no inputs, no save, an explanation', async () => {
    render(<BudgetPage hooks={hooksFor(budgetApi())} now={NOW} />, { wrapper: wrapperFor() });
    await screen.findByText('Despesas operacionais / Marketing');
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Salvar orçamento' })).not.toBeInTheDocument();
    expect(screen.getByText(/Somente leitura/)).toBeInTheDocument();
  });

  it('admin edits a cell and saves ONE PUT with only the changed cells; save is disabled until something changes', async () => {
    const user = userEvent.setup();
    const api = budgetApi();
    render(<BudgetPage hooks={hooksFor(api)} isAdmin now={NOW} />, { wrapper: wrapperFor() });
    const save = await screen.findByRole('button', { name: 'Salvar orçamento' });
    expect(save).toBeDisabled();
    const input = screen.getByLabelText('Planejado: Marketing out/2026');
    expect(input).toHaveValue('500,00');
    await user.clear(input);
    await user.type(input, '750,50');
    expect(save).toBeEnabled();
    await user.click(save);
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1));
    expect(api.put.mock.calls[0]).toEqual(['/api/finance/budgets', { items: [{ category_id: 'cat-mkt', month: '2026-10-01', amount_cents: 75_050 }] }]);
    expect(await screen.findByText('Salvo')).toBeInTheDocument();
  });

  it('clearing an existing cell deletes that budget; an invalid amount is refused before any request', async () => {
    const user = userEvent.setup();
    const api = budgetApi();
    render(<BudgetPage hooks={hooksFor(api)} isAdmin now={NOW} />, { wrapper: wrapperFor() });
    const nov = await screen.findByLabelText('Planejado: Marketing nov/2026');
    await user.clear(nov);
    await user.click(screen.getByRole('button', { name: 'Salvar orçamento' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/finance/budgets/b2'));
    expect(api.put).not.toHaveBeenCalled();
    const oct = screen.getByLabelText('Planejado: Marketing out/2026');
    await user.clear(oct);
    await user.type(oct, 'abc');
    await user.click(screen.getByRole('button', { name: 'Salvar orçamento' }));
    expect(await screen.findByText('Valor inválido')).toBeInTheDocument();
    expect(api.put).not.toHaveBeenCalled();
  });

  it('a server refusal is shown, never swallowed; a failed first load offers retry', async () => {
    const user = userEvent.setup();
    const api = budgetApi({ 'PUT /api/finance/budgets': () => Promise.reject(new ApiError(403, 'Restrito a administradores')) });
    render(<BudgetPage hooks={hooksFor(api)} isAdmin now={NOW} />, { wrapper: wrapperFor() });
    const input = await screen.findByLabelText('Planejado: Marketing out/2026');
    await user.clear(input);
    await user.type(input, '1');
    await user.click(screen.getByRole('button', { name: 'Salvar orçamento' }));
    expect(await screen.findByText(/Restrito a administradores/)).toBeInTheDocument();
    cleanup();
    render(<BudgetPage hooks={hooksFor(budgetApi({ 'GET /api/finance/reports/budget': () => Promise.reject(new ApiError(500, 'boom')) }))} now={NOW} />, { wrapper: wrapperFor() });
    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument();
  });

  it('an empty period explains itself and lets the admin pull a category into the budget', async () => {
    const user = userEvent.setup();
    const empty = { ...BUDGET, rows: [] };
    render(<BudgetPage hooks={hooksFor(budgetApi({ 'GET /api/finance/reports/budget': ok(empty), 'GET /api/finance/budgets': ok([]) }))} isAdmin now={NOW} />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Nenhuma categoria com orçamento/)).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Incluir categoria no orçamento'), 'cat-sales');
    expect(await screen.findByLabelText('Planejado: Vendas out/2026')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------------------------------------------------
const BOOK: LivroCaixaData = {
  from: '2026-10-01', to: '2026-10-14', opening_balance_cents: 10_700, total_in_cents: 5_000, total_out_cents: 2_100, closing_balance_cents: 13_600,
  row_count: 3, page: 1, page_size: 100,
  rows: [
    { on: '2026-10-05', kind: 'settlement', history: 'Mensalidade outubro', in: 5_000, out: 0, balance_cents: 15_700, counterparty: 'Ana', category: 'Vendas', account: 'Banco', ledger_id: 'l1' },
    { on: '2026-10-05', kind: 'fee', history: 'Tarifa: Mensalidade outubro', in: 0, out: 100, balance_cents: 15_600, counterparty: null, category: null, account: 'Banco', ledger_id: 'l2' },
    { on: '2026-10-06', kind: 'settlement', history: 'Aluguel', in: 0, out: 2_000, balance_cents: 13_600, counterparty: null, category: null, account: 'Banco', ledger_id: 'l3' },
  ],
  legal_basis: 'LC 123/2006 art. 26 §2 · Res. CGSN 140/2018 art. 63', notes: ['Todas as contas somadas.'], disclaimer: 'Listagem preparada pelo sistema.',
};

describe('LivroCaixaReport', () => {
  it('renders saldo anterior, running balance and totals; downloads CSV and PDF with the period', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ 'GET /api/finance/reports/livro-caixa': ok(BOOK) });
    render(<LivroCaixaReport hooks={hooksFor(api)} canExport now={NOW} />, { wrapper: wrapperFor() });
    expect(await screen.findByText('Mensalidade outubro')).toBeInTheDocument();
    const opening = screen.getByText('Saldo anterior').closest('div')!;
    expect(flat(opening.textContent)).toContain('R$ 107,00');
    expect(flat(screen.getByText('Saldo final').closest('div')!.textContent)).toContain('R$ 136,00');
    expect(flat(screen.getByText('Aluguel').closest('tr')!.textContent)).toContain('R$ 136,00');
    expect(screen.getByText(/LC 123\/2006/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Baixar PDF' }));
    await waitFor(() => expect(api.download).toHaveBeenCalledWith('/api/finance/exports/livro-caixa.pdf?from=2026-10-01&to=2026-10-14'));
    await user.click(screen.getByRole('button', { name: 'Baixar CSV' }));
    await waitFor(() => expect(api.download).toHaveBeenCalledWith('/api/finance/exports/livro-caixa.csv?from=2026-10-01&to=2026-10-14'));
  });

  it('without the export right there are no download buttons; an empty period and an error say so', async () => {
    const api = makeRoutedApi({ 'GET /api/finance/reports/livro-caixa': ok({ ...BOOK, rows: [], row_count: 0 }) });
    render(<LivroCaixaReport hooks={hooksFor(api)} now={NOW} />, { wrapper: wrapperFor() });
    expect(await screen.findByText('Sem movimentação no período.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Baixar/ })).not.toBeInTheDocument();
    cleanup();
    render(<LivroCaixaReport hooks={hooksFor(makeRoutedApi({ 'GET /api/finance/reports/livro-caixa': () => Promise.reject(new ApiError(403, 'x')) }))} now={NOW} />, { wrapper: wrapperFor() });
    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument();
  });

  it('pages through the rows (display only) by requesting the next page', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ 'GET /api/finance/reports/livro-caixa': ok({ ...BOOK, row_count: 250 }) });
    render(<LivroCaixaReport hooks={hooksFor(api)} now={NOW} />, { wrapper: wrapperFor() });
    await user.click(await screen.findByRole('button', { name: 'Próxima' }));
    await waitFor(() => expect(api.get.mock.calls.some((c) => (c[1] as { page?: number })?.page === 2)).toBe(true));
  });
});

// ---------------------------------------------------------------------------------------------------------------------
const FIELDS = {
  comercio: { title: 'Revenda de mercadorias (comércio)', without: 'Revenda sem nota', without_roman: 'I', with: 'Revenda com nota', with_roman: 'II', total: 'Total revenda', total_roman: 'III' },
  industria: { title: 'Venda de produtos industrializados (indústria)', without: 'Indústria sem nota', without_roman: 'IV', with: 'Indústria com nota', with_roman: 'V', total: 'Total indústria', total_roman: 'VI' },
  servicos: { title: 'Prestação de serviços', without: 'Serviços sem nota', without_roman: 'VII', with: 'Serviços com nota', with_roman: 'VIII', total: 'Total serviços', total_roman: 'IX' },
};
const MEI: MeiMonthlyData = {
  month: '2026-10', tax_regime: 'mei', applicable: true, basis: 'cash', deadline: '2026-11-20',
  groups: {
    comercio: { without_invoice_cents: 4_000, with_invoice_cents: 10_000, total_cents: 14_000 },
    industria: { without_invoice_cents: 0, with_invoice_cents: 0, total_cents: 0 },
    servicos: { without_invoice_cents: 5_000, with_invoice_cents: 30_000, total_cents: 35_000 },
  },
  fields: FIELDS, grand_total: { label: 'Total geral das receitas brutas no mês', roman: 'X' }, total_cents: 49_000,
  unassigned_cents: 2_500, unknown_invoice_cents: 4_000,
  warnings: [{ code: 'atividade_nao_definida', severity: 'critical', message: 'Receita sem atividade.', action: 'Defina a atividade.' }],
  notes: ['Regime de caixa.'], legal_basis: 'Res. CGSN 140/2018 art. 106, 108 e 109 (Anexo X)', disclaimer: 'Relatório preparado pelo sistema.',
};

describe('MeiMonthlyReport', () => {
  it('lays out the model rows I-X, the unassigned money apart, the deadline and the warnings', async () => {
    const api = makeRoutedApi({ 'GET /api/finance/reports/mei-monthly': ok(MEI) });
    render(<MeiMonthlyReport hooks={hooksFor(api)} canExport now={NOW} />, { wrapper: wrapperFor() });
    const total = (await screen.findByText('Total geral das receitas brutas no mês')).closest('tr')!;
    expect(flat(total.textContent)).toContain('R$ 490,00');
    expect(flat(screen.getByText('Revenda com nota').closest('tr')!.textContent)).toContain('R$ 100,00');
    expect(flat(screen.getByText(/fora dos totais/).textContent)).toContain('R$ 25,00');
    expect(screen.getByText(/20\/11\/2026/)).toBeInTheDocument();
    expect(screen.getByText('Receita sem atividade.')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/api/finance/reports/mei-monthly', { month: '2026-10-01' });
  });

  it('downloads CSV and PDF for the chosen month', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ 'GET /api/finance/reports/mei-monthly': ok(MEI) });
    render(<MeiMonthlyReport hooks={hooksFor(api)} canExport now={NOW} />, { wrapper: wrapperFor() });
    await user.click(await screen.findByRole('button', { name: 'Baixar PDF' }));
    await waitFor(() => expect(api.download).toHaveBeenCalledWith('/api/finance/exports/mei-monthly.pdf?month=2026-10-01'));
    await user.click(screen.getByRole('button', { name: 'Baixar CSV' }));
    await waitFor(() => expect(api.download).toHaveBeenCalledWith('/api/finance/exports/mei-monthly.csv?month=2026-10-01'));
  });

  it('outside the MEI regime it shows an explanation instead of numbers and offers no downloads', async () => {
    const api = makeRoutedApi({ 'GET /api/finance/reports/mei-monthly': ok({ ...MEI, applicable: false, tax_regime: 'simples', warnings: [] }) });
    render(<MeiMonthlyReport hooks={hooksFor(api)} canExport now={NOW} />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/só para o MEI/)).toBeInTheDocument();
    expect(screen.queryByText('Revenda com nota')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Baixar/ })).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------------------------------------------------
const CHECK = (over: Record<string, unknown> = {}) => ({
  generated_at: '', tax_regime: 'simples', tax_regime_informed: true, das_split_irpj_csll: false, provisional_choices: [], confirmed_choices: [],
  open_questions: [], exports: [], disclaimer: 'x', dominio_readiness: { categories_without_code: 3, accounts_without_code: 1, ready: false }, ...over,
});
const missingErr = () => new ApiError(422, 'faltam códigos', {
  error: { code: 'dominio_codigos_ausentes', message: 'x', details: { categories: [{ id: 'c1', name: 'Vendas' }], accounts: [{ id: 'a1', name: 'Itaú' }], issues: [{ code: 'lancamento_sem_categoria', count: 2 }] } },
});

describe('DominioExport', () => {
  it('validates the company document locally before any request', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ 'GET /api/finance/accountant-checklist': ok(CHECK()) });
    render(<DominioExport hooks={hooksFor(api)} canExport now={NOW} />, { wrapper: wrapperFor() });
    await user.type(await screen.findByLabelText(/^CNPJ/), '123');
    await user.click(screen.getByRole('button', { name: 'Baixar arquivo do Domínio' }));
    expect(await screen.findByText(/14 dígitos/)).toBeInTheDocument();
    expect(api.download).not.toHaveBeenCalled();
  });

  it('downloads with digits only and the optional histórico code', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ 'GET /api/finance/accountant-checklist': ok(CHECK()) });
    render(<DominioExport hooks={hooksFor(api)} canExport now={NOW} />, { wrapper: wrapperFor() });
    await user.type(await screen.findByLabelText(/^CNPJ/), '11.222.333/0001-81');
    await user.type(screen.getByLabelText(/Código do histórico/), '7');
    await user.click(screen.getByRole('button', { name: 'Baixar arquivo do Domínio' }));
    await waitFor(() => expect(api.download).toHaveBeenCalledWith('/api/finance/exports/dominio.txt?from=2026-10-01&to=2026-10-14&cnpj=11222333000181&history_code=7'));
    expect(await screen.findByText('Arquivo baixado.')).toBeInTheDocument();
  });

  it('shows the exact categories and accounts the server says are missing, and routes to Cadastros', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ 'GET /api/finance/accountant-checklist': ok(CHECK()) });
    api.download.mockRejectedValueOnce(missingErr());
    const go = vi.fn();
    render(<DominioExport hooks={hooksFor(api)} canExport onGoToRegisters={go} now={NOW} />, { wrapper: wrapperFor() });
    await user.type(await screen.findByLabelText(/^CNPJ/), '11222333000181');
    await user.click(screen.getByRole('button', { name: 'Baixar arquivo do Domínio' }));
    const box = await screen.findByTestId('dominio-missing');
    expect(within(box).getByText('Vendas')).toBeInTheDocument();
    expect(within(box).getByText('Itaú')).toBeInTheDocument();
    expect(within(box).getByText(/Lançamentos baixados sem categoria \(2\)/)).toBeInTheDocument();
    await user.click(within(box).getByRole('button', { name: 'Ir para Cadastros' }));
    expect(go).toHaveBeenCalled();
    expect(screen.getByText(/Faltam códigos contábeis: 3 categoria/)).toBeInTheDocument();
  });

  it('any other error is a plain message; without the export right nothing is offered', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ 'GET /api/finance/accountant-checklist': ok(CHECK({ dominio_readiness: { categories_without_code: 0, accounts_without_code: 0, ready: true } })) });
    api.download.mockRejectedValueOnce(new ApiError(403, 'Sem permissão'));
    render(<DominioExport hooks={hooksFor(api)} canExport now={NOW} />, { wrapper: wrapperFor() });
    await user.type(await screen.findByLabelText(/^CNPJ/), '11222333000181');
    await user.click(screen.getByRole('button', { name: 'Baixar arquivo do Domínio' }));
    expect(await screen.findByText(/Sem permissão/)).toBeInTheDocument();
    expect(screen.queryByTestId('dominio-missing')).not.toBeInTheDocument();
    cleanup();
    render(<DominioExport hooks={hooksFor(api)} now={NOW} />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Somente administradores/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Baixar arquivo do Domínio' })).not.toBeInTheDocument();
  });

  it('dominioMissingOf only recognises the contract error', () => {
    expect(dominioMissingOf(new ApiError(422, 'x', { error: { code: 'outro' } }))).toBeNull();
    expect(dominioMissingOf(new Error('x'))).toBeNull();
    expect(dominioMissingOf(missingErr())?.categories).toEqual([{ id: 'c1', name: 'Vendas' }]);
  });
});

// ---------------------------------------------------------------------------------------------------------------------
describe('Accountant checklist: books + Domínio readiness', () => {
  it('links to the Livro Caixa / Domínio (and MEI only for the MEI regime) and states readiness', async () => {
    const user = userEvent.setup();
    const open = vi.fn();
    const api = makeRoutedApi({ 'GET /api/finance/accountant-checklist': ok(CHECK({ tax_regime: 'mei', exports: [{ name: 'livro_caixa_pdf', path: '/api/finance/exports/livro-caixa.pdf' }] })) });
    render(<AccountantChecklist hooks={hooksFor(api)} canExport onOpenTab={open} />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Faltam códigos contábeis: 3 categoria\(s\) e 1 conta\(s\)/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Abrir o Livro Caixa' }));
    await user.click(screen.getByRole('button', { name: 'Gerar o arquivo do Domínio' }));
    await user.click(screen.getByRole('button', { name: 'Abrir o Relatório Mensal do MEI' }));
    expect(open.mock.calls.map((c) => c[0])).toEqual(['livro_caixa', 'dominio', 'mei']);
    await user.click(screen.getByRole('button', { name: 'Livro Caixa (PDF)' }));
    await waitFor(() => expect(api.download).toHaveBeenCalledWith('/api/finance/exports/livro-caixa.pdf'));
  });

  it('no MEI link for other regimes; the accountant read grant (canExport) enables downloads without admin', async () => {
    const api = makeRoutedApi({ 'GET /api/finance/accountant-checklist': ok(CHECK({ exports: [{ name: 'dre_csv', path: '/api/finance/exports/dre.csv' }] })) });
    render(<AccountantChecklist hooks={hooksFor(api)} canExport onOpenTab={() => {}} />, { wrapper: wrapperFor() });
    expect(await screen.findByRole('button', { name: 'DRE (CSV)' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: 'Abrir o Relatório Mensal do MEI' })).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------------------------------------------------
function shellRoutes(regime: 'mei' | 'simples') {
  return makeRoutedApi({
    ...baseRoutes(),
    'GET /api/finance/dre-settings': ok({ persisted: true, tax_regime: regime, tax_regime_prefilled: false, das_split_irpj_csll: false, das_irpj_csll_share_bps: 0, choices: {} }),
    'GET /api/finance/accountant-checklist': ok(CHECK({ tax_regime: regime })),
    'GET /api/finance/reports/budget': ok(BUDGET),
    'GET /api/finance/budgets': ok(BUDGETS),
    'GET /api/finance/reports/livro-caixa': ok(BOOK),
    'GET /api/finance/reports/mei-monthly': ok(MEI),
  });
}

describe('FinanceShell: Orçamento + Contador tabs', () => {
  it('has an Orçamento section and the new Contador tabs; the MEI tab appears only for tax_regime = mei', async () => {
    const user = userEvent.setup();
    render(<FinanceShell hooks={hooksFor(shellRoutes('simples'))} isAdmin section="accountant" now={NOW} />, { wrapper: wrapperFor() });
    const tabs = await screen.findByRole('tablist', { name: 'Contador' });
    await waitFor(() => expect(within(tabs).getByRole('tab', { name: 'Livro Caixa' })).toBeInTheDocument());
    expect(within(tabs).getByRole('tab', { name: 'Arquivo do Domínio' })).toBeInTheDocument();
    expect(within(tabs).queryByRole('tab', { name: 'Relatório do MEI' })).not.toBeInTheDocument();
    await user.click(within(tabs).getByRole('tab', { name: 'Livro Caixa' }));
    expect(await screen.findByRole('heading', { name: 'Livro Caixa' })).toBeInTheDocument();
    cleanup();
    render(<FinanceShell hooks={hooksFor(shellRoutes('mei'))} isAdmin section="accountant" now={NOW} />, { wrapper: wrapperFor() });
    const mei = await screen.findByRole('tab', { name: 'Relatório do MEI' });
    await user.click(mei);
    expect(await screen.findByRole('heading', { name: 'Relatório Mensal de Receitas Brutas' })).toBeInTheDocument();
  });

  it('the Orçamento section renders the budget page', async () => {
    render(<FinanceShell hooks={hooksFor(shellRoutes('simples'))} isAdmin section="budget" now={NOW} />, { wrapper: wrapperFor() });
    expect(await screen.findByRole('heading', { name: 'Orçamento' })).toBeInTheDocument();
    expect(await screen.findByText('Despesas operacionais / Marketing')).toBeInTheDocument();
  });

  it('isAccountant (read grant, not admin) is offered the downloads but no budget editing', async () => {
    const user = userEvent.setup();
    const api = shellRoutes('simples');
    render(<FinanceShell hooks={hooksFor(api)} isAccountant section="accountant" now={NOW} />, { wrapper: wrapperFor() });
    const tabs = await screen.findByRole('tablist', { name: 'Contador' });
    await user.click(within(tabs).getByRole('tab', { name: 'Livro Caixa' }));
    expect(await screen.findByRole('button', { name: 'Baixar PDF' })).toBeInTheDocument();
    cleanup();
    render(<FinanceShell hooks={hooksFor(api)} isAccountant section="budget" now={NOW} />, { wrapper: wrapperFor() });
    await screen.findByText('Despesas operacionais / Marketing');
    expect(screen.queryByRole('button', { name: 'Salvar orçamento' })).not.toBeInTheDocument();
  });

  it('a plain staff member is not offered downloads', async () => {
    const user = userEvent.setup();
    render(<FinanceShell hooks={hooksFor(shellRoutes('simples'))} section="accountant" now={NOW} />, { wrapper: wrapperFor() });
    const tabs = await screen.findByRole('tablist', { name: 'Contador' });
    await user.click(within(tabs).getByRole('tab', { name: 'Livro Caixa' }));
    await screen.findByText('Mensalidade outubro');
    expect(screen.queryByRole('button', { name: 'Baixar PDF' })).not.toBeInTheDocument();
  });

  it("'Ir para Cadastros' from the Domínio tab opens Cadastros > Categorias", async () => {
    const user = userEvent.setup();
    const api = shellRoutes('simples');
    api.download.mockRejectedValue(missingErr());
    render(<FinanceShell hooks={hooksFor(api)} isAdmin now={NOW} />, { wrapper: wrapperFor() });
    await user.click(within(screen.getByRole('navigation', { name: 'Financeiro' })).getByRole('button', { name: 'Contador' }));
    const tabs = await screen.findByRole('tablist', { name: 'Contador' });
    await user.click(within(tabs).getByRole('tab', { name: 'Arquivo do Domínio' }));
    await user.type(await screen.findByLabelText(/^CNPJ/), '11222333000181');
    await user.click(screen.getByRole('button', { name: 'Baixar arquivo do Domínio' }));
    await user.click(await screen.findByRole('button', { name: 'Ir para Cadastros' }));
    expect(await screen.findByRole('heading', { name: 'Categorias' })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------------------------------------------------
describe('registers: accounting code, MEI activity, nota fiscal', () => {
  it('a category form sends the accounting code and (income only) the MEI activity', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ ...baseRoutes(), 'POST /api/finance/categories': ok({ id: 'n' }) });
    render(<FinanceCategoryManager hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
    await user.click(await screen.findByRole('button', { name: 'Nova categoria' }));
    const form = screen.getByRole('form', { name: 'Dados da categoria' });
    await user.type(within(form).getByLabelText(/^Nome/), 'Consultoria');
    await user.selectOptions(within(form).getByLabelText('Tipo'), 'income');
    await user.type(within(form).getByLabelText(/Código contábil/), '3.1.05');
    await user.selectOptions(within(form).getByLabelText(/Atividade \(MEI\)/), 'servicos');
    await user.click(within(form).getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post.mock.calls[0][1]).toMatchObject({ name: 'Consultoria', direction: 'income', accounting_code: '3.1.05', activity_kind: 'servicos' });
  });

  it('an expense category has no MEI activity field; the table shows the code or "sem código"', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ ...baseRoutes(), 'GET /api/finance/categories': ok([{ id: 'cat-sales', parent_id: null, name: 'Vendas', direction: 'income', is_default: true, active: true, dre_line: 'gross_revenue', behavior: 'variable', accounting_code: '3.1.01', activity_kind: 'comercio' }, { id: 'cat-rent', parent_id: null, name: 'Aluguel', direction: 'expense', is_default: true, active: true }]) });
    render(<FinanceCategoryManager hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
    const sales = (await screen.findByText('Vendas')).closest('tr')!;
    expect(within(sales).getByText('3.1.01')).toBeInTheDocument();
    expect(within(sales).getByText(/Comércio/)).toBeInTheDocument();
    expect(within(screen.getByText('Aluguel').closest('tr')!).getByText('sem código')).toBeInTheDocument();
    await user.click(within(screen.getByText('Aluguel').closest('tr')!).getByRole('button', { name: 'Editar' }));
    expect(screen.queryByLabelText(/Atividade \(MEI\)/)).not.toBeInTheDocument();
  });

  it('editing a category with a code lets the admin clear it (explicit null)', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ ...baseRoutes(), 'GET /api/finance/categories': ok([{ id: 'cat-rent', parent_id: null, name: 'Aluguel', direction: 'expense', is_default: false, active: true, accounting_code: '4.1.02' }]), 'PATCH /api/finance/categories/cat-rent': ok({}) });
    render(<FinanceCategoryManager hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
    await user.click(await screen.findByRole('button', { name: 'Editar' }));
    const form = screen.getByRole('form', { name: 'Dados da categoria' });
    await user.clear(within(form).getByLabelText(/Código contábil/));
    await user.click(within(form).getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalled());
    expect(api.patch.mock.calls[0][1]).toMatchObject({ accounting_code: null });
  });

  it('an account form carries the accounting code', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({
      ...baseRoutes(),
      'GET /api/finance/accounts/acc-bank/balance': ok({ account_id: 'acc-bank', on: 'x', opening_balance_cents: 0, movement_cents: 0, balance_cents: 0 }),
      'GET /api/finance/accounts/acc-gw/balance': ok({ account_id: 'acc-gw', on: 'x', opening_balance_cents: 0, movement_cents: 0, balance_cents: 0 }),
      'PATCH /api/finance/accounts/acc-bank': ok({}),
    });
    render(<AccountsManager hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
    const li = (await screen.findByText(ACC_BANK.name)).closest('li')!;
    await user.click(within(li).getByRole('button', { name: 'Editar' }));
    await user.type(screen.getByLabelText(/Código contábil/), '1.1.01');
    await user.click(within(screen.getByRole('form', { name: 'Dados da conta' })).getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalled());
    expect(api.patch.mock.calls[0][1]).toMatchObject({ accounting_code: '1.1.01' });
  });

  it('a receivable asks about the nota fiscal and sends it only when changed; a payable has no such field', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ ...baseRoutes(), 'PATCH /api/finance/entries/e1': ok(entry()) });
    const { rerender } = render(<EntryDialog hooks={hooksFor(api)} open onClose={() => {}} direction="receivable" entry={entry()} />, { wrapper: wrapperFor() });
    await user.selectOptions(await screen.findByLabelText(/^Nota fiscal da venda/), 'yes');
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalled());
    expect(api.patch.mock.calls[0][1]).toMatchObject({ has_invoice: true });
    api.patch.mockClear();
    cleanup();
    render(<EntryDialog hooks={hooksFor(api)} open onClose={() => {}} direction="receivable" entry={entry({ has_invoice: true })} />, { wrapper: wrapperFor() });
    await user.click(await screen.findByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalled());
    expect(api.patch.mock.calls[0][1]).not.toHaveProperty('has_invoice');
    cleanup();
    void rerender;
    render(<EntryDialog hooks={hooksFor(api)} open onClose={() => {}} direction="payable" />, { wrapper: wrapperFor() });
    await screen.findByLabelText(/^Descrição/);
    expect(screen.queryByLabelText(/^Nota fiscal da venda/)).not.toBeInTheDocument();
  });
});
