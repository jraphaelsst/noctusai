/**
 * DRE pages — fixtures mirror the SHIPPED backend payloads (`dre.py` build_dre, `dre_settings.py` present,
 * `accountant.py` build_checklist, `simples_base.py`), CONTRACT §10/§10.5/§11.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DreReport } from './DreReport';
import { DreSettingsForm } from './DreSettingsForm';
import { AccountantChecklist } from './AccountantChecklist';
import { SimplesBaseReport } from './SimplesBaseReport';
import { ApiError } from '../api';
import { hooksFor, makeRoutedApi, ok, wrapperFor } from './testUtils';
import type { AccountantChecklistData, DreReportData, DreSettings, DreStatementItem, SimplesBaseData } from './dreTypes';

afterEach(cleanup);
const NOW = new Date(2026, 9, 14);
const flat = (s: string | null) => (s ?? '').replace(/\u00a0/g, ' ');

const months = ['2026-09', '2026-10'];
const I = (key: string, label: string, cents: number, over: Partial<DreStatementItem> = {}): DreStatementItem => ({
  key, kind: ['net_revenue', 'gross_result', 'net_result'].includes(key) ? 'subtotal' : 'line', label,
  sign: ['gross_revenue', 'financial_revenue', 'other_operating'].includes(key) ? 1 : -1 as 1 | -1, cents,
  by_month: { '2026-09': Math.floor(cents / 2), '2026-10': cents - Math.floor(cents / 2) }, detail: [], empty: cents === 0, ...over,
});
const D = (name: string, cents: number, behavior: 'variable' | 'fixed' | null = 'variable') => ({
  category_id: `c-${name}`, name, cents, by_month: { '2026-09': Math.floor(cents / 2), '2026-10': cents - Math.floor(cents / 2) }, behavior, source: null,
});
const STATEMENT: DreStatementItem[] = [
  I('gross_revenue', 'Receita bruta', 1_000_000, { detail: [D('Vendas', 900_000), D('Juros de parcelamento', 100_000)] }),
  I('deductions', '(-) Deduções da receita', 80_000),
  I('net_revenue', '= Receita líquida', 920_000),
  I('cost_of_sales', '(-) Custo das vendas', 0),
  I('gross_result', '= Lucro bruto', 920_000),
  I('selling_expenses', '(-) Despesas com vendas', 35_000, { detail: [D('Taxas do gateway/cartão (MDR)', 35_000)] }),
  I('net_result', '= Resultado líquido', 885_000),
];
const REPORT: DreReportData = {
  from: '2026-01-01', to: '2026-10-14', months, view: 'statement', title: 'Demonstração do Resultado do Exercício (DRE)',
  standard: 'nbc_tg_1002', tax_regime: 'simples', trailing_12m_gross_revenue_cents: 1_000_000, net_result_cents: 885_000,
  unclassified: { net_cents: 0, by_month: {}, detail: [], included_in_net_result: false },
  help: { selling_expenses: { label: '(-) Despesas com vendas', what: 'Ajuda do servidor para vendas', example: 'Taxa do gateway', source: 'Fonte do servidor' } },
  warnings: [], accountant_alerts: [], statement: STATEMENT,
};
const MANAGERIAL = {
  title: 'Visão gerencial — margem de contribuição',
  revenue: { cents: 1_000_000, by_month: {}, detail: [{ line: 'gross_revenue' as const, category_id: 'c1', name: 'Vendas', by_month: {}, cents: 1_000_000 }] },
  variable_costs: { cents: 300_000, by_month: {}, detail: [{ line: 'deductions' as const, category_id: 'c2', name: 'Impostos sobre vendas', by_month: {}, cents: 300_000 }] },
  contribution_margin: { cents: 700_000, by_month: {}, percent_of_revenue_bps: 7000 },
  fixed_costs: { cents: 0, by_month: {}, detail: [] },
  other_income: { cents: 0, by_month: {}, detail: [] },
  net_result: { cents: 700_000, by_month: {} },
};

function mount(report: Partial<DreReportData> | (() => Promise<unknown>) = {}) {
  const api = makeRoutedApi({
    'GET /api/finance/reports/dre': typeof report === 'function' ? report : ok({ ...REPORT, ...report }),
  });
  render(<DreReport hooks={hooksFor(api)} now={NOW} />, { wrapper: wrapperFor() });
  return api;
}

describe('DreReport', () => {
  it('lists the statement rows in order with the API labels and money', async () => {
    mount();
    const table = await screen.findByRole('table', { name: 'Demonstração do resultado' });
    const order = [...table.querySelectorAll('tbody > tr[data-line]')].map((r) => r.getAttribute('data-line'));
    expect(order).toEqual(['gross_revenue', 'deductions', 'net_revenue', 'cost_of_sales', 'gross_result', 'selling_expenses', 'net_result']);
    const row = within(table).getByText('(-) Deduções da receita').closest('tr')!;
    expect(flat(row.textContent)).toContain('R$ 800,00');
    expect(within(table).getByText('= Receita líquida').closest('tr')).toHaveClass('font-semibold');
    expect(flat(within(table).getByText('= Resultado líquido').closest('tr')!.textContent)).toContain('R$ 8.850,00');
  });

  it('requests the period (year start → today) with view=statement', async () => {
    const api = mount();
    await screen.findByRole('table');
    expect(api.get).toHaveBeenCalledWith('/api/finance/reports/dre', { from: '2026-01-01', to: '2026-10-14', view: 'statement' });
  });

  it('zero lines stay visible, greyed, labelled, and keep their help', async () => {
    const user = userEvent.setup();
    mount();
    const row = (await screen.findByText('(-) Custo das vendas')).closest('tr')!;
    expect(row).toHaveAttribute('data-zero', 'true');
    expect(row).toHaveClass('text-muted-foreground');
    expect(within(row).getByText('sem valores no período')).toBeInTheDocument();
    await user.click(within(row).getByRole('button', { name: 'O que é "(-) Custo das vendas"?' }));
    expect(within(row).getByRole('note')).toHaveTextContent(/custo do que foi vendido/i);
    expect(within(row).getByRole('note')).toHaveTextContent(/NBC TG 1002/);
  });

  it('uses the API help[key] when present, else the built-in plain-language copy', async () => {
    const user = userEvent.setup();
    mount();
    const sell = (await screen.findByText('(-) Despesas com vendas')).closest('tr')!;
    await user.click(within(sell).getByRole('button', { name: /O que é/ }));
    expect(within(sell).getByRole('note')).toHaveTextContent('Ajuda do servidor para vendas');
    expect(within(sell).getByRole('note')).toHaveTextContent('Fonte do servidor');
    const gross = screen.getByText('Receita bruta').closest('tr')!;
    await user.click(within(gross).getByRole('button', { name: /O que é/ }));
    expect(within(gross).getByRole('note')).toHaveTextContent(/Tudo o que a loja vendeu/);
  });

  it('expands category detail rows under a line', async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByText('Receita bruta');
    expect(screen.queryByText('Juros de parcelamento')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Ver detalhes de Receita bruta' }));
    expect(screen.getByText('Juros de parcelamento')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Ver detalhes de Receita bruta' })).toHaveAttribute('aria-expanded', 'true');
    await user.click(screen.getByRole('button', { name: 'Ver detalhes de Receita bruta' }));
    expect(screen.queryByText('Juros de parcelamento')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Ver detalhes de = Lucro bruto' })).not.toBeInTheDocument();
  });

  it('by-month columns', async () => {
    const user = userEvent.setup();
    mount();
    const table = await screen.findByRole('table');
    expect(within(table).queryByRole('columnheader', { name: 'set/2026' })).not.toBeInTheDocument();
    await user.click(screen.getByLabelText('Mostrar mês a mês'));
    expect(within(table).getByRole('columnheader', { name: 'set/2026' })).toBeInTheDocument();
    expect(within(table).getByRole('columnheader', { name: 'out/2026' })).toBeInTheDocument();
  });

  it('unclassified money is shown in its own block and is NOT part of the net result', async () => {
    mount({ unclassified: { net_cents: -12_000, by_month: {}, detail: [D('Papelaria', 12_000, null)], included_in_net_result: false } });
    const block = await screen.findByLabelText('Não classificado');
    expect(flat(block.textContent)).toMatch(/Não classificado: -R\$ 120,00/);
    expect(within(block).getByText('Papelaria')).toBeInTheDocument();
    expect(within(block).getByText(/NÃO entram no resultado líquido/)).toBeInTheDocument();
    expect(flat(screen.getByText('= Resultado líquido').closest('tr')!.textContent)).toContain('R$ 8.850,00');
  });

  it('no unclassified block when nothing is unclassified', async () => {
    mount();
    await screen.findByRole('table');
    expect(screen.queryByLabelText('Não classificado')).not.toBeInTheDocument();
  });

  it('warnings banner and accountant alerts (code, severity, message, action; why + source)', async () => {
    mount({
      warnings: [
        { code: 'categoria_sem_linha_dre', severity: 'warning', message: '2 categorias sem linha do DRE.', action: 'Classifique em Cadastros > Categorias.' },
        { code: 'limite_microentidade_excedido', severity: 'critical', message: 'Receita acima de R$ 4,8 milhões.', action: '' },
        { code: 'cmv_por_compras', severity: 'info', message: 'Custo calculado pelas compras do mês.', action: 'Confirme com o contador.' },
      ],
      accountant_alerts: [{ code: 'a1', message: 'Fale com um contador sobre a mudança de norma.', why: 'NBC TG 1001 passa a valer.', source: 'NBC TG 1001' }],
    });
    const banner = await screen.findByLabelText('Avisos sobre o relatório');
    expect(within(banner).getByText('2 categorias sem linha do DRE.')).toBeInTheDocument();
    expect(within(banner).getByText(/Classifique em Cadastros/)).toBeInTheDocument();
    expect(within(banner).getByText('Receita acima de R$ 4,8 milhões.')).toBeInTheDocument();
    expect(within(banner).getByText('Custo calculado pelas compras do mês.')).toBeInTheDocument();
    expect(within(banner).getByText(/Fale com um contador/)).toBeInTheDocument();
    expect(within(banner).getByText(/NBC TG 1001 passa a valer/)).toBeInTheDocument();
    expect(within(banner).getByText('Fonte: NBC TG 1001')).toBeInTheDocument();
  });

  it('MEI stores keep the server title "DRE gerencial (MEI não é obrigado a ter DRE)"; others the server title', async () => {
    mount({ tax_regime: 'mei', title: 'DRE gerencial (MEI não é obrigado a ter DRE)' });
    expect(await screen.findByRole('heading', { name: 'DRE gerencial (MEI não é obrigado a ter DRE)' })).toBeInTheDocument();
    cleanup();
    mount();
    expect(await screen.findByRole('heading', { name: 'Demonstração do Resultado do Exercício (DRE)' })).toBeInTheDocument();
  });

  it('managerial view: asks view=managerial, renders the managerial block (margin, variable/fixed), no statement', async () => {
    const user = userEvent.setup();
    const api = mount();
    await screen.findByRole('table');
    api.route('GET /api/finance/reports/dre', ok({ ...REPORT, view: 'managerial', statement: undefined, managerial: MANAGERIAL }));
    await user.click(screen.getByRole('button', { name: /Gerencial/ }));
    const table = await screen.findByRole('table', { name: 'Demonstração gerencial' });
    expect(api.get).toHaveBeenLastCalledWith('/api/finance/reports/dre', expect.objectContaining({ view: 'managerial' }));
    expect(within(table).getByText(/Custos e despesas variáveis/)).toBeInTheDocument();
    expect(flat(screen.getByText(/Margem de contribuição:/).closest('p')!.textContent)).toContain('R$ 7.000,00 (70,0%)');
    expect(screen.getByRole('heading', { name: 'Visão gerencial — margem de contribuição' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Gerencial/ })).toHaveAttribute('aria-pressed', 'true');
    await user.click(within(table).getByRole('button', { name: 'Ver detalhes de Custos e despesas variáveis' }));
    expect(within(table).getByText('Impostos sobre vendas')).toBeInTheDocument();
    expect(within(table).getByText(/Custos e despesas fixos/).closest('tr')).toHaveAttribute('data-zero', 'true');
  });

  it('a managerial request that came back without the block says so (no fake numbers)', async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByRole('table');
    await user.click(screen.getByRole('button', { name: /Gerencial/ }));
    expect(await screen.findByText(/visão gerencial ainda não está disponível/)).toBeInTheDocument();
  });

  it('skeleton → keeps lines while the period changes → error with retry', async () => {
    const user = userEvent.setup();
    mount(() => new Promise(() => {}));
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    cleanup();
    const api2 = mount();
    await screen.findByRole('table');
    api2.route('GET /api/finance/reports/dre', () => new Promise(() => {}));
    await user.clear(screen.getByLabelText('Até'));
    await user.type(screen.getByLabelText('Até'), '2026-09-30');
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.queryByTestId('list-loading')).not.toBeInTheDocument();
    cleanup();
    mount(() => Promise.reject(new ApiError(500, 'caiu')));
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
  });
});

const choice = (value: string, over: Record<string, unknown> = {}) => ({ value, default: value, provisional: true, confirmed_by: null, confirmed_at: null, note: null, ...over });
const SETTINGS = {
  persisted: true, tax_regime: 'simples', tax_regime_prefilled: false, das_split_irpj_csll: false, das_irpj_csll_share_bps: 0,
  choices: {
    gateway_fee_line: choice('selling_expenses', { provisional: false, confirmed_at: '2026-10-10T12:00:00Z', confirmed_by: 'u1' }),
    anticipation_fee_line: choice('financial_expenses'),
    chargeback_line: choice('deductions'),
    chargeback_fee_line: choice('selling_expenses'),
    installment_interest_line: choice('gross_revenue'),
  },
} as DreSettings;

function mountSettings(settings: Partial<DreSettings> | (() => Promise<unknown>) = {}, extra: Record<string, unknown> = {}, isAdmin = true) {
  const api = makeRoutedApi({
    'GET /api/finance/dre-settings': typeof settings === 'function' ? settings : ok({ ...SETTINGS, ...settings }),
    ...extra,
  });
  render(<DreSettingsForm hooks={hooksFor(api)} isAdmin={isAdmin} />, { wrapper: wrapperFor() });
  return api;
}

describe('DreSettingsForm', () => {
  it('marks every unconfirmed choice provisional and the confirmed one confirmed', async () => {
    mountSettings();
    const gateway = (await screen.findByText('Taxa do gateway / cartão')).closest('[data-setting]') as HTMLElement;
    expect(within(gateway).getByText(/^confirmado/)).toBeInTheDocument();
    for (const key of ['anticipation_fee_line', 'chargeback_line', 'chargeback_fee_line', 'installment_interest_line']) {
      const block = document.querySelector(`[data-setting="${key}"]`) as HTMLElement;
      expect(within(block).getByText('provisório — confirme com seu contador')).toBeInTheDocument();
    }
    expect(screen.getByText(/Tudo o que está marcado como "provisório"/)).toBeInTheDocument();
  });

  it('confirming = PUT with confirmations[name] {confirmed, note} (there is no /confirm route); never automatic', async () => {
    const user = userEvent.setup();
    const api = mountSettings({}, { 'PUT /api/finance/dre-settings': ok(SETTINGS) });
    await screen.findByText('Taxa de antecipação de recebíveis');
    expect(api.put).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText(/Anotação da confirmação/), 'Confirmado pela contadora Ana');
    const block = document.querySelector('[data-setting="chargeback_line"]') as HTMLElement;
    await user.click(within(block).getByRole('button', { name: 'Confirmar com o contador' }));
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/api/finance/dre-settings', { confirmations: { chargeback_line: { confirmed: true, note: 'Confirmado pela contadora Ana' } } }),
    );
    expect(api.post).not.toHaveBeenCalled();
  });

  it('confirming one choice keeps the unsaved edits of the others', async () => {
    const user = userEvent.setup();
    const api = mountSettings({}, { 'PUT /api/finance/dre-settings': ok(SETTINGS) });
    await user.selectOptions(await screen.findByLabelText('Tarifa de chargeback'), 'financial_expenses');
    const block = document.querySelector('[data-setting="chargeback_line"]') as HTMLElement;
    await user.click(within(block).getByRole('button', { name: 'Confirmar com o contador' }));
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    await waitFor(() => expect(api.get.mock.calls.length).toBeGreaterThan(1)); // refetched after the confirmation
    expect(screen.getByLabelText('Tarifa de chargeback')).toHaveValue('financial_expenses');
  });

  it('saves only what changed (PUT), and Save is disabled until something changes', async () => {
    const user = userEvent.setup();
    const api = mountSettings({}, { 'PUT /api/finance/dre-settings': ok(SETTINGS) });
    const save = await screen.findByRole('button', { name: 'Salvar' });
    expect(save).toBeDisabled();
    await user.selectOptions(screen.getByLabelText('Tarifa de chargeback'), 'financial_expenses');
    expect(save).toBeEnabled();
    await user.click(save);
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/api/finance/dre-settings', { chargeback_fee_line: 'financial_expenses' }));
    expect(await screen.findByText('Salvo')).toBeInTheDocument();
  });

  it('regime drives the form: unknown warns; simples offers the DAS split (share in bps, required); mei hides it', async () => {
    const user = userEvent.setup();
    const api = mountSettings({ tax_regime: 'unknown' }, { 'PUT /api/finance/dre-settings': ok(SETTINGS) });
    expect(await screen.findByText(/Regime não informado/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Separar a parte de IRPJ/)).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Regime tributário'), 'simples');
    await user.click(screen.getByLabelText(/Separar a parte de IRPJ/));
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    expect(await screen.findByText(/percentual de repartição do seu anexo/)).toBeInTheDocument();
    expect(api.put).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText(/Parte de IRPJ \+ CSLL/), '12.5');
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/api/finance/dre-settings', { tax_regime: 'simples', das_split_irpj_csll: true, das_irpj_csll_share_bps: 1250 }));
    await user.selectOptions(screen.getByLabelText('Regime tributário'), 'mei');
    expect(screen.queryByLabelText(/Separar a parte de IRPJ/)).not.toBeInTheDocument();
    expect(screen.getByText(/MEI: o DAS é um valor fixo/)).toBeInTheDocument();
  });

  it('shows a stored split share as a percentage, and a regime pre-filled from the store profile', async () => {
    mountSettings({ das_split_irpj_csll: true, das_irpj_csll_share_bps: 2740, tax_regime_prefilled: true });
    expect(await screen.findByLabelText(/Parte de IRPJ \+ CSLL/)).toHaveValue(27.4);
    expect(screen.getByText(/Preenchido pelo cadastro da loja/)).toBeInTheDocument();
  });

  it('staff: read-only (controls disabled), no confirm/save buttons', async () => {
    mountSettings({}, {}, false);
    expect(await screen.findByLabelText('Taxa do gateway / cartão')).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Confirmar com o contador' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Salvar' })).not.toBeInTheDocument();
    expect(screen.getByText(/Somente administradores/)).toBeInTheDocument();
  });

  it('skeleton, load error with retry, and server refusal on save', async () => {
    const user = userEvent.setup();
    mountSettings(() => new Promise(() => {}));
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    cleanup();
    mountSettings(() => Promise.reject(new ApiError(500, 'x')));
    expect(await screen.findByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument();
    cleanup();
    mountSettings({}, { 'PUT /api/finance/dre-settings': () => Promise.reject(new ApiError(422, 'Linha inválida para esta escolha')) });
    await user.selectOptions(await screen.findByLabelText('Tarifa de chargeback'), 'deductions');
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Linha inválida para esta escolha');
  });
});

const item = (choice: string, over: Record<string, unknown> = {}) => ({
  choice, question_id: 'Q1', question: 'A taxa do gateway/cartão (MDR) é despesa com vendas ou despesa financeira?',
  why_open: 'Não há norma; a prática se divide.', options: { selling_expenses: 'Despesas com vendas (padrão)', financial_expenses: 'Despesas financeiras' },
  current_value: 'selling_expenses', default_value: 'selling_expenses', provisional: true, confirmed_by: null, confirmed_at: null, note: null,
  sources: ['KB § PATTERNS/finance/dre-structure.md §4(a)', 'Solução de Consulta Cosit 143/2021'], ...over,
});
const CHECKLIST = {
  generated_at: '2026-10-14T10:00:00Z', tax_regime: 'simples', tax_regime_informed: true, das_split_irpj_csll: false,
  provisional_choices: [item('gateway_fee_line'), item('chargeback_line', { question_id: 'Q3', question: 'O chargeback perdido é dedução?' })],
  confirmed_choices: [item('installment_interest_line', { question_id: 'Q2', question: 'Juros de parcelamento: receita bruta ou financeira?', provisional: false, confirmed_at: '2026-10-10T12:00:00Z', note: 'Ok pela Ana' })],
  open_questions: [{ id: 'Q4', question: 'Divisão do DAS: tudo em Deduções ou separar IRPJ/CSLL?', context: 'NBC TG 1002 §29.3 admite ambos.', sources: ['NBC TG 1002 §29.3'] }],
  exports: [
    { name: 'dre_csv', path: '/api/finance/exports/dre.csv' },
    { name: 'entries_csv', path: '/api/finance/exports/entries.csv' },
    { name: 'ledger_ofx', path: '/api/finance/exports/ledger.ofx' },
  ],
  disclaimer: 'Este sistema prepara, classifica e exporta; não assina, não entrega obrigações e não escolhe regime tributário.',
} as AccountantChecklistData;

describe('AccountantChecklist', () => {
  it('shows the server disclaimer, provisional choices with why/options/sources, open questions and confirmed ones', async () => {
    const api = makeRoutedApi({ 'GET /api/finance/accountant-checklist': ok(CHECKLIST) });
    render(<AccountantChecklist hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
    expect(await screen.findByText('3 ponto(s) ainda precisam da confirmação do contador.')).toBeInTheDocument(); // 2 choices + 1 question
    expect(screen.getByText(/não assina, não entrega obrigações/)).toBeInTheDocument();
    const card = document.querySelector('[data-item="gateway_fee_line"]') as HTMLElement;
    expect(within(card).getByText('Provisório')).toBeInTheDocument();
    expect(card.textContent).toContain('Escolha atual do sistema: Despesas com vendas (padrão)');
    expect(card.textContent).toContain('Por que está em aberto: Não há norma');
    expect(card.textContent).toContain('Despesas financeiras');
    expect(card.textContent).toContain('Solução de Consulta Cosit 143/2021');
    const q = document.querySelector('[data-question="Q4"]') as HTMLElement;
    expect(q.textContent).toContain('Divisão do DAS');
    expect(q.textContent).toContain('NBC TG 1002 §29.3');
    const done = document.querySelector('[data-item="installment_interest_line"]') as HTMLElement;
    expect(within(done).getByText('Confirmado')).toBeInTheDocument();
    expect(done.textContent).toContain('Ok pela Ana');
  });

  it('warns when the regime was not informed', async () => {
    const api = makeRoutedApi({ 'GET /api/finance/accountant-checklist': ok({ ...CHECKLIST, tax_regime: 'unknown', tax_regime_informed: false }) });
    render(<AccountantChecklist hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Regime não informado/)).toBeInTheDocument();
  });

  it('downloads DRE / entries CSV from the API export links; the OFX (needs an account) is not offered here; staff cannot', async () => {
    const user = userEvent.setup();
    Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:z'), revokeObjectURL: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const api = makeRoutedApi({ 'GET /api/finance/accountant-checklist': ok(CHECKLIST) });
    render(<AccountantChecklist hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
    expect(screen.queryByRole('button', { name: /OFX|razão/i })).not.toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: 'DRE (CSV)' }));
    await waitFor(() => expect(api.download).toHaveBeenCalledWith('/api/finance/exports/dre.csv'));
    cleanup();
    render(<AccountantChecklist hooks={hooksFor(api)} />, { wrapper: wrapperFor() });
    expect(await screen.findByRole('button', { name: 'Lançamentos (CSV)' })).toBeDisabled();
    expect(click).toHaveBeenCalledTimes(1);
    click.mockRestore();
  });

  it('all confirmed, empty, skeleton and error', async () => {
    const done = { ...CHECKLIST, provisional_choices: [], open_questions: [], exports: [] };
    render(<AccountantChecklist hooks={hooksFor(makeRoutedApi({ 'GET /api/finance/accountant-checklist': ok(done) }))} />, { wrapper: wrapperFor() });
    expect(await screen.findByText('Tudo confirmado pelo contador.')).toBeInTheDocument();
    cleanup();
    const empty = { ...done, confirmed_choices: [] };
    render(<AccountantChecklist hooks={hooksFor(makeRoutedApi({ 'GET /api/finance/accountant-checklist': ok(empty) }))} />, { wrapper: wrapperFor() });
    expect(await screen.findByText('Nada para confirmar no momento.')).toBeInTheDocument();
    cleanup();
    render(<AccountantChecklist hooks={hooksFor(makeRoutedApi({ 'GET /api/finance/accountant-checklist': () => new Promise(() => {}) }))} />, { wrapper: wrapperFor() });
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    cleanup();
    render(<AccountantChecklist hooks={hooksFor(makeRoutedApi({ 'GET /api/finance/accountant-checklist': () => Promise.reject(new ApiError(500, 'x')) }))} />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
  });
});

const T = (over: Record<string, number> = {}) => ({ sales_cents: 500_000, interest_cents: 20_000, refunds_cents: 10_000, chargebacks_cents: 0, base_cents: 510_000, ...over });
const SIMPLES: SimplesBaseData = {
  from: '2026-01-01', to: '2026-10-14', tax_regime: 'simples', invoice_basis_from: '2027-01-01', crosses_basis_boundary: false,
  months: [{ month: '2026-10', basis: 'cash', ...T() }],
  totals: { ...T(), cash_basis: T(), invoice_basis: T({ sales_cents: 0, interest_cents: 0, refunds_cents: 0, base_cents: 0 }) },
  basis_note: 'Base de faturamento aproximada pelo mês de competência do recebível.',
  notes: ['Comissão de marketplace não é descontada.'],
  warnings: [{ code: 'chargeback_fora_da_base', severity: 'info', message: 'Chargebacks perdidos NÃO foram abatidos da base.', action: 'Pergunte ao contador.' }],
};

describe('SimplesBaseReport', () => {
  it('totals, per-month basis, the 2027 rule, notes, warnings, disclaimer; defaults to year start → today', async () => {
    const api = makeRoutedApi({ 'GET /api/finance/reports/simples-base': ok(SIMPLES) });
    render(<SimplesBaseReport hooks={hooksFor(api)} now={NOW} />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/a partir de 01\/01\/2027 vale o faturamento/)).toBeInTheDocument();
    expect(flat(screen.getByText('Base de cálculo', { selector: 'dt' }).parentElement!.textContent)).toContain('R$ 5.100,00');
    const table = screen.getByRole('table');
    expect(within(table).getByText('out/2026')).toBeInTheDocument();
    expect(within(table).getByText('Caixa')).toBeInTheDocument();
    expect(screen.getByText('Comissão de marketplace não é descontada.')).toBeInTheDocument();
    expect(screen.getByText('Chargebacks perdidos NÃO foram abatidos da base.')).toBeInTheDocument();
    expect(screen.getByText(/aproximada pelo mês de competência/)).toBeInTheDocument();
    expect(screen.getByText(/não envia nada à Receita/)).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/api/finance/reports/simples-base', { from: '2026-01-01', to: '2026-10-14' });
  });

  it('a period crossing the basis boundary is explained, and lost chargebacks are shown but not deducted', async () => {
    const data = {
      ...SIMPLES, crosses_basis_boundary: true,
      months: [{ month: '2026-12', basis: 'cash' as const, ...T() }, { month: '2027-01', basis: 'invoice' as const, ...T({ chargebacks_cents: 7_000 }) }],
      totals: { ...SIMPLES.totals, chargebacks_cents: 7_000 },
    };
    render(<SimplesBaseReport hooks={hooksFor(makeRoutedApi({ 'GET /api/finance/reports/simples-base': ok(data) }))} now={NOW} />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/O período passa por essa mudança/)).toBeInTheDocument();
    expect(screen.getByText('Faturamento')).toBeInTheDocument();
    expect(flat(screen.getByText(/Chargebacks perdidos no período/).textContent)).toContain('R$ 70,00');
  });

  it('empty and error states', async () => {
    render(<SimplesBaseReport hooks={hooksFor(makeRoutedApi({ 'GET /api/finance/reports/simples-base': ok({ ...SIMPLES, months: [], warnings: [] }) }))} now={NOW} />, { wrapper: wrapperFor() });
    expect(await screen.findByText('Sem movimento no período.')).toBeInTheDocument();
    cleanup();
    render(<SimplesBaseReport hooks={hooksFor(makeRoutedApi({ 'GET /api/finance/reports/simples-base': () => Promise.reject(new ApiError(500, 'x')) }))} now={NOW} />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
  });
});
