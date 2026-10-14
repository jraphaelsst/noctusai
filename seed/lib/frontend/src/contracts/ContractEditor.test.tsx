import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ContractEditor, buildContractInput } from './ContractEditor';
import { ApiError } from '../api';
import { contract, ok, setup, version } from './testUtils';

afterEach(cleanup);

const DETAIL = (c = contract()) => ({
  [`GET /api/contracts/${c.id}`]: ok(c),
  [`GET /api/contracts/${c.id}/versions`]: ok([version()]),
  [`GET /api/contracts/${c.id}/billing-preview`]: ok({ items: [], billed: 0 }),
});

function mount(routes: Record<string, unknown>, props: Partial<React.ComponentProps<typeof ContractEditor>> = {}) {
  const s = setup(routes);
  render(<s.Wrapper><ContractEditor hooks={s.hooks} open contractId={null} onClose={() => undefined} canWrite {...props} /></s.Wrapper>);
  return s;
}

describe('ContractEditor — billing-model fields follow the seam', () => {
  it.each([
    ['one_time', ['Valor do pagamento', 'Primeiro vencimento'], ['Número de parcelas', 'Periodicidade', 'Horas incluídas por mês', 'Dia do vencimento']],
    ['installments', ['Valor total', 'Número de parcelas', 'Dia do vencimento'], ['Periodicidade', 'Horas incluídas por mês']],
    ['recurring', ['Valor por período', 'Periodicidade', 'Dia do vencimento', 'Índice de reajuste'], ['Número de parcelas', 'Horas incluídas por mês']],
    ['retainer', ['Honorário mensal', 'Horas incluídas por mês', 'Valor da hora excedente', 'Índice de reajuste'], ['Número de parcelas', 'Periodicidade']],
  ])('%s shows its own fields only', async (model, shown, hidden) => {
    const user = userEvent.setup();
    mount({});
    await user.selectOptions(screen.getByLabelText('Modelo de cobrança'), model);
    for (const l of shown) expect(screen.getByLabelText(l)).toBeInTheDocument();
    for (const l of hidden) expect(screen.queryByLabelText(l)).not.toBeInTheDocument();
  });

  it('a fixed index asks for the percentage', async () => {
    const user = userEvent.setup();
    mount({});
    expect(screen.queryByLabelText('Percentual fixo (%)')).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Índice de reajuste'), 'fixed');
    expect(screen.getByLabelText('Percentual fixo (%)')).toBeInTheDocument();
  });
});

describe('ContractEditor — create', () => {
  it('posts integer cents / minutes / basis points for a retainer and closes', async () => {
    const user = userEvent.setup();
    let closed = false;
    const s = mount({ 'POST /api/contracts': ok(contract({ id: 'new', billing_model: 'retainer' })) }, { onClose: () => { closed = true; } });
    await user.type(screen.getByLabelText('Título'), 'Suporte mensal');
    await user.selectOptions(screen.getByLabelText('Modelo de cobrança'), 'retainer');
    await user.type(screen.getByLabelText('Honorário mensal'), '1.500,00');
    await user.type(screen.getByLabelText('Horas incluídas por mês'), '10');
    await user.type(screen.getByLabelText('Valor da hora excedente'), '120');
    await user.type(screen.getByLabelText('Dia do vencimento'), '10');
    await user.type(screen.getByLabelText('Primeiro vencimento'), '2026-11-10');
    await user.selectOptions(screen.getByLabelText('Índice de reajuste'), 'fixed');
    await user.type(screen.getByLabelText('Percentual fixo (%)'), '4,5');
    await user.type(screen.getByLabelText('Multa sobre o saldo (%)'), '10');
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(closed).toBe(true));
    const body = s.api.post.mock.calls[0][1] as Record<string, unknown>;
    expect(body).toMatchObject({
      title: 'Suporte mensal', billing_model: 'retainer', amount_cents: 150000, retainer_minutes: 600, excess_rate_cents: 12000, due_day: 10,
      first_due_date: '2026-11-10', readjustment_index: 'fixed', readjustment_percent_bp: 450, penalty_bp: 1000, penalty_cents: 0,
    });
    expect(body).not.toHaveProperty('lines');
    expect(Number.isInteger(body.amount_cents)).toBe(true);
  });

  it('lines replace the amount: the total is derived and `amount_cents` is not sent', async () => {
    const user = userEvent.setup();
    const s = mount({ 'POST /api/contracts': ok(contract({ id: 'n' })) });
    await user.type(screen.getByLabelText('Título'), 'Pacote');
    await user.type(screen.getByLabelText('Primeiro vencimento'), '2026-11-10');
    await user.click(screen.getByRole('button', { name: 'Adicionar linha' }));
    await user.type(screen.getByLabelText('Descrição 1'), 'Gestão');
    await user.clear(screen.getByLabelText('Qtd. 1'));
    await user.type(screen.getByLabelText('Qtd. 1'), '2');
    await user.type(screen.getByLabelText('Preço unitário 1'), '500');
    expect(screen.getByLabelText('Valor (soma das linhas)')).toHaveValue('1000,00');
    expect(screen.getByLabelText('Valor (soma das linhas)')).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(s.api.post).toHaveBeenCalled());
    const body = s.api.post.mock.calls[0][1] as Record<string, unknown>;
    expect(body.lines).toEqual([{ description: 'Gestão', quantity: 2, unit_price_cents: 50000 }]);
    expect(body).not.toHaveProperty('amount_cents');
  });

  it('client-side validation blocks the call with a pt-BR message', async () => {
    const user = userEvent.setup();
    const s = mount({});
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Informe o título.');
    expect(s.api.post).not.toHaveBeenCalled();
  });

  it('a server refusal is mapped to its pt-BR message and the dialog stays open', async () => {
    const user = userEvent.setup();
    mount({ 'POST /api/contracts': () => { throw new ApiError(409, 'dup', { error: { code: 'numero_duplicado', message: 'dup' } }); } });
    await user.type(screen.getByLabelText('Título'), 'X');
    await user.type(screen.getByLabelText('Valor por período'), '10');
    await user.type(screen.getByLabelText('Primeiro vencimento'), '2026-11-10');
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Já existe um contrato com este número.');
  });
});

describe('buildContractInput', () => {
  const base = {
    title: 'T', number: '', partyId: null, partyName: 'Ana', partyDoc: '***.982.247-**', model: 'installments' as const, amount: '1.000,00',
    installments: '3', frequency: 'monthly' as const, dueDay: '', firstDue: '2026-11-10', start: '', end: '', autoRenew: false, renewalMonths: '12',
    hours: '', excessRate: '', index: 'none' as const, indexPercent: '', indexEvery: '12', notice: '0', penalty: '', penaltyPercent: '', notes: '', lines: [],
  };
  it('never sends a masked document back', () => {
    const r = buildContractInput(base);
    expect('input' in r && r.input.party_doc).toBeUndefined();
    expect('input' in r && r.input.installments_count).toBe(3);
  });
  it('refuses a bad parcel count / zero amount / missing date', () => {
    expect(buildContractInput({ ...base, installments: '0' })).toEqual({ error: 'Informe o número de parcelas.' });
    expect(buildContractInput({ ...base, amount: '0' })).toEqual({ error: 'Informe um valor maior que zero.' });
    expect(buildContractInput({ ...base, firstDue: '' })).toEqual({ error: 'Informe o primeiro vencimento ou a data de início.' });
  });
});

describe('ContractEditor — existing contract', () => {
  it('first load shows a skeleton and never a lying empty/not-found', async () => {
    let resolve!: (v: unknown) => void;
    const s = setup({ ...DETAIL() });
    s.api.route('GET /api/contracts/c1', () => new Promise((r) => (resolve = r)));
    render(<s.Wrapper><ContractEditor hooks={s.hooks} open contractId="c1" onClose={() => undefined} canWrite /></s.Wrapper>);
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    expect(screen.queryByText('Contrato não encontrado.')).not.toBeInTheDocument();
  });

  it('a draft is editable and offers activate + delete; saving PATCHes', async () => {
    const user = userEvent.setup();
    const s = mount({ ...DETAIL(), 'PATCH /api/contracts/c1': ok(contract({ title: 'Novo' })), 'POST /api/contracts/c1/activate': ok(contract({ status: 'active' })) }, { contractId: 'c1' });
    const title = await screen.findByLabelText('Título');
    expect(title).toHaveValue('Gestão de tráfego');
    await user.clear(title);
    await user.type(title, 'Novo título');
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(s.api.patch).toHaveBeenCalledWith('/api/contracts/c1', expect.objectContaining({ title: 'Novo título', amount_cents: 150000 })));
    await user.click(screen.getByRole('button', { name: 'Ativar contrato' }));
    await waitFor(() => expect(s.api.post).toHaveBeenCalledWith('/api/contracts/c1/activate', {}));
    expect(screen.getByRole('button', { name: 'Excluir rascunho' })).toBeInTheDocument();
  });

  it('a masked party document is shown locked and the timeline + preview render', async () => {
    mount({ ...DETAIL(contract({ party_doc: '***.982.247-**' })), 'GET /api/contracts/c1/billing-preview': ok({ items: [{ period_key: '2026-11-10', kind: 'fixed', due_date: '2026-11-10', competence_month: '2026-11-01', amount_cents: 150000, description: 'Mensal — 11/2026' }], billed: 2 }) }, { contractId: 'c1' });
    expect(await screen.findByLabelText('CPF/CNPJ da parte')).toBeDisabled();
    expect(await screen.findByText('Termos iniciais', { selector: 'p' })).toBeInTheDocument();
    expect(await screen.findByText('Mensal — 11/2026')).toBeInTheDocument();
    expect(screen.getByText('2 já faturadas')).toBeInTheDocument();
  });

  it('an active contract is read-only: terms cannot be edited, the action bar appears', async () => {
    mount(DETAIL(contract({ status: 'active' })), { contractId: 'c1' });
    expect(await screen.findByLabelText('Título')).toBeEnabled();
    expect(screen.getByLabelText('Valor por período')).toBeDisabled();
    expect(screen.getByText('Contrato vigente: os termos só mudam por aditivo.')).toBeInTheDocument();
    for (const n of ['Suspender', 'Novo aditivo', 'Encerrar']) expect(screen.getByRole('button', { name: n })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Salvar' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reajustar' })).toBeInTheDocument(); // recurring
  });

  it('one-time contracts have no readjust action; staff (no canWrite) see no actions at all', async () => {
    mount(DETAIL(contract({ status: 'active', billing_model: 'one_time' })), { contractId: 'c1' });
    await screen.findByLabelText('Título');
    expect(screen.queryByRole('button', { name: 'Reajustar' })).not.toBeInTheDocument();
    cleanup();
    mount(DETAIL(contract({ status: 'active' })), { contractId: 'c1', canWrite: false });
    await screen.findByLabelText('Título');
    expect(screen.getByText('Somente leitura: apenas administradores editam contratos.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Encerrar' })).not.toBeInTheDocument();
  });

  it('a suspended contract offers resume; resume POSTs', async () => {
    const user = userEvent.setup();
    const s = mount({ ...DETAIL(contract({ status: 'suspended' })), 'POST /api/contracts/c1/resume': ok(contract({ status: 'active' })) }, { contractId: 'c1' });
    await user.click(await screen.findByRole('button', { name: 'Retomar' }));
    await waitFor(() => expect(s.api.post).toHaveBeenCalledWith('/api/contracts/c1/resume', {}));
  });

  it('not found is stated, not an empty form', async () => {
    mount({ 'GET /api/contracts/zz': () => { throw new ApiError(404, 'nf', {}); } }, { contractId: 'zz' });
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
  });

  it('amendment panel posts only what changed; readjust previews then applies', async () => {
    const user = userEvent.setup();
    const s = mount({
      ...DETAIL(contract({ status: 'active', readjustment_index: 'IPCA' })),
      'POST /api/contracts/c1/amendments': ok(contract({ status: 'active' })),
      'POST /api/contracts/c1/readjust': (_p: string, body: any) => ok({ applied: !!body.apply, index: 'IPCA', percent_bp: body.percent_bp, effective_on: '2026-11-01', amount_cents_before: 150000, amount_cents_after: 156750, excess_rate_cents_before: null, excess_rate_cents_after: null }),
    }, { contractId: 'c1' });
    await user.click(await screen.findByRole('button', { name: 'Novo aditivo' }));
    await user.type(screen.getByLabelText('Resumo do aditivo'), 'Aumento de escopo');
    const amount = screen.getByLabelText('Novo valor');
    await user.clear(amount);
    await user.type(amount, '1.800,00');
    await user.click(screen.getByRole('button', { name: 'Registrar aditivo' }));
    await waitFor(() => expect(s.api.post).toHaveBeenCalledWith('/api/contracts/c1/amendments', { summary: 'Aumento de escopo', changes: { amount_cents: 180000 }, effective_on: undefined }));

    await user.click(screen.getByRole('button', { name: 'Reajustar' }));
    expect(screen.getByText(/sem consulta externa/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Aplicar reajuste' })).toBeDisabled(); // must simulate first
    await user.type(screen.getByLabelText('Percentual do índice (%)'), '4,5');
    await user.click(screen.getByRole('button', { name: 'Simular' }));
    expect(await screen.findByRole('status')).toHaveTextContent('R$ 1.500,00 → R$ 1.567,50');
    expect(s.api.post).toHaveBeenLastCalledWith('/api/contracts/c1/readjust', expect.objectContaining({ percent_bp: 450, apply: false }));
  });
});
