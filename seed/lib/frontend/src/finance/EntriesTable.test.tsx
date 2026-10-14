import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EntriesTable } from './EntriesTable';
import { ApiError } from '../api';
import { ACC_BANK, ACC_GW, baseRoutes, entry, hooksFor, makeRoutedApi, ok, page, wrapperFor } from './testUtils';
import type { FinanceEntryDetail, Settlement } from './types';

afterEach(cleanup);

const SETTLEMENT: Settlement = {
  id: 's1', entry_id: 'e1', account_id: 'acc-bank', kind: 'payment', settled_on: '2026-10-10', amount_cents: 3000,
  fee_cents: 0, method: 'pix', external_ref: null, reversed_at: null, reversal_reason: null,
};
const detail = (over: Partial<FinanceEntryDetail> = {}): FinanceEntryDetail => ({
  ...entry({ status: 'partial', settled_cents: 3000 }), settlements: [SETTLEMENT], attachments: [], ...over,
});

function mount(routes: Record<string, unknown> = {}, props: { isAdmin?: boolean; direction?: 'receivable' | 'payable' } = {}) {
  const api = makeRoutedApi({ ...baseRoutes(), 'GET /api/finance/entries': page([entry(), entry({ id: 'e2', description: 'Pedido #101', overdue: true, due_date: '2026-09-01' })]), ...routes });
  const hooks = hooksFor(api);
  const Wrapper = wrapperFor();
  render(<EntriesTable hooks={hooks} direction="receivable" {...props} />, { wrapper: Wrapper });
  return api;
}

describe('EntriesTable states', () => {
  it('shows the skeleton on first load, never an empty state', () => {
    mount({ 'GET /api/finance/entries': () => new Promise(() => {}) });
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    expect(screen.queryByText(/Nenhum lançamento/)).not.toBeInTheDocument();
  });

  it('error state with retry that refetches', async () => {
    let fail = true;
    const api = mount({ 'GET /api/finance/entries': () => (fail ? Promise.reject(new ApiError(500, 'caiu')) : page([entry()])) });
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
    fail = false;
    await userEvent.setup().click(screen.getByRole('button', { name: 'Tentar novamente' }));
    expect(await screen.findByText('Pedido #100')).toBeInTheDocument();
    expect(api.get.mock.calls.filter((c) => c[0] === '/api/finance/entries').length).toBeGreaterThan(1);
  });

  it('empty state', async () => {
    mount({ 'GET /api/finance/entries': page([]) });
    expect(await screen.findByText(/Nenhum lançamento encontrado/)).toBeInTheDocument();
  });

  it('success: rows, overdue chip, category name, remaining; staff has no write actions', async () => {
    mount();
    expect(await screen.findByText('Pedido #100')).toBeInTheDocument();
    expect(screen.getByText('Vencido')).toBeInTheDocument();
    expect(within(screen.getByText('Pedido #100').closest('tr')!).getByText('Em aberto')).toBeInTheDocument();
    expect(screen.getAllByText('Vendas').length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /Dar baixa/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Novo lançamento' })).not.toBeInTheDocument();
  });

  it('keeps rows on screen while refetching after a filter change (no skeleton, no empty flash)', async () => {
    const user = userEvent.setup();
    let release!: (v: unknown) => void;
    const api = mount();
    await screen.findByText('Pedido #100');
    api.route('GET /api/finance/entries', () => new Promise((r) => (release = r)));
    await user.selectOptions(screen.getByLabelText('Filtrar por situação'), 'paid');
    expect(screen.getByText('Pedido #100')).toBeInTheDocument();
    expect(screen.queryByTestId('list-loading')).not.toBeInTheDocument();
    expect(await screen.findByText('Atualizando…')).toBeInTheDocument();
    release(page([]));
    expect(await screen.findByText(/Nenhum lançamento encontrado/)).toBeInTheDocument();
    const last = api.get.mock.calls.filter((c) => c[0] === '/api/finance/entries').slice(-1)[0][1] as Record<string, unknown>;
    expect(last).toMatchObject({ direction: 'receivable', status: 'paid', page: 1 });
  });
});

describe('settle (baixa)', () => {
  it('partial settlement posts the lowered amount, shows the rest, and defaults the expected account', async () => {
    const user = userEvent.setup();
    const api = mount({ 'POST /api/finance/entries/e1/settlements': ok({ settlement: SETTLEMENT, entry: entry({ status: 'partial' }), replayed: false }) }, { isAdmin: true });
    await user.click(await screen.findByRole('button', { name: 'Dar baixa: Pedido #100' }));
    const dialog = screen.getByRole('dialog');
    const amount = within(dialog).getByLabelText(/Valor baixado/);
    expect(amount).toHaveValue('100,00');
    expect(within(dialog).getByLabelText(/^Conta/)).toHaveValue('acc-bank');
    await user.clear(amount);
    await user.type(amount, '40,00');
    expect(within(dialog).getByText(/Baixa parcial: depois dela ainda ficam .*60,00/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Confirmar baixa' }));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const [path, body] = api.post.mock.calls[0];
    expect(path).toBe('/api/finance/entries/e1/settlements');
    expect(body).toMatchObject({ account_id: 'acc-bank', kind: 'payment', amount_cents: 4000, fee_cents: 0 });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('blocks an amount above what is open, and requires an account', async () => {
    const user = userEvent.setup();
    const api = mount({}, { isAdmin: true });
    await user.click(await screen.findByRole('button', { name: 'Dar baixa: Pedido #100' }));
    const dialog = screen.getByRole('dialog');
    await user.selectOptions(within(dialog).getByLabelText(/^Conta/), '');
    const amount = within(dialog).getByLabelText(/Valor baixado/);
    await user.clear(amount);
    await user.type(amount, '100,01');
    await user.click(within(dialog).getByRole('button', { name: 'Confirmar baixa' }));
    expect(await within(dialog).findByText(/não pode passar do que está em aberto/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Escolha a conta onde/)).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('shows the server refusal inside the dialog', async () => {
    const user = userEvent.setup();
    mount({ 'POST /api/finance/entries/e1/settlements': () => Promise.reject(new ApiError(409, 'Esta referência já foi usada')) }, { isAdmin: true });
    await user.click(await screen.findByRole('button', { name: 'Dar baixa: Pedido #100' }));
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Confirmar baixa' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Esta referência já foi usada');
  });
});

describe('entry detail', () => {
  async function openDetail(user: ReturnType<typeof userEvent.setup>, extra: Record<string, unknown> = {}) {
    const api = mount({ 'GET /api/finance/entries/e1': ok(detail()), 'GET /api/finance/entries/e1/attachments': ok([]), ...extra }, { isAdmin: true });
    await user.click(await screen.findByRole('button', { name: 'Pedido #100' }));
    return { api, dialog: await screen.findByRole('dialog') };
  }

  it('lists settlements and reverses one with a mandatory reason', async () => {
    const user = userEvent.setup();
    const { api, dialog } = await openDetail(user, { 'POST /api/finance/settlements/s1/reverse': ok({ settlement: SETTLEMENT, entry: entry() }) });
    expect(await within(dialog).findByText(/Pagamento .*30,00/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Estornar' }));
    await user.click(within(dialog).getByRole('button', { name: 'Confirmar estorno' }));
    expect(await within(dialog).findByText(/pelo menos 3 letras/)).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
    await user.type(within(dialog).getByLabelText(/Motivo do estorno/), 'Cliente pagou em duplicidade');
    await user.click(within(dialog).getByRole('button', { name: 'Confirmar estorno' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/finance/settlements/s1/reverse', { reason: 'Cliente pagou em duplicidade' }));
  });

  it('a reversed settlement shows as history, not as an action', async () => {
    const user = userEvent.setup();
    const { dialog } = await openDetail(user, {
      'GET /api/finance/entries/e1': ok(detail({ settlements: [{ ...SETTLEMENT, reversed_at: '2026-10-11T10:00:00Z', reversal_reason: 'Engano' }] })),
    });
    expect(await within(dialog).findByText(/Estornada: Engano/)).toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: 'Estornar' })).not.toBeInTheDocument();
  });

  it('cancels an unsettled entry only after a second confirmation', async () => {
    const user = userEvent.setup();
    const { api, dialog } = await openDetail(user, {
      'GET /api/finance/entries/e1': ok(detail({ status: 'open', settled_cents: 0, settlements: [] })),
      'POST /api/finance/entries/e1/cancel': ok(entry({ status: 'cancelled' })),
    });
    await user.click(await within(dialog).findByRole('button', { name: 'Cancelar lançamento' }));
    expect(api.post).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole('button', { name: 'Sim, cancelar' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/finance/entries/e1/cancel', {}));
  });

  it('attachments: upload, list and delete', async () => {
    const user = userEvent.setup();
    const att = { id: 'att1', entry_id: 'e1', filename: 'nota.pdf', content_type: 'application/pdf', size_bytes: 2048, at: '2026-10-10T10:00:00Z', url: 'https://s/x', expires_in_seconds: 300, disposition: 'attachment' };
    const { api, dialog } = await openDetail(user, {
      'GET /api/finance/entries/e1/attachments': ok([att]),
      'UPLOAD /api/finance/entries/e1/attachments': ok(att),
      'DELETE /api/finance/attachments/att1': null,
    });
    const link = await within(dialog).findByRole('link', { name: 'nota.pdf' });
    expect(link).toHaveAttribute('href', 'https://s/x');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
    await user.upload(within(dialog).getByLabelText('Escolher arquivo para anexar'), new File(['%PDF-'], 'novo.pdf', { type: 'application/pdf' }));
    await waitFor(() => expect(api.upload).toHaveBeenCalled());
    await user.click(within(dialog).getByRole('button', { name: 'Remover' }));
    await user.click(within(dialog).getByRole('button', { name: 'Confirmar' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/finance/attachments/att1'));
  });

  it('staff cannot upload, delete, settle or cancel', async () => {
    const api = makeRoutedApi({ ...baseRoutes(), 'GET /api/finance/entries': page([entry()]), 'GET /api/finance/entries/e1': ok(detail()), 'GET /api/finance/entries/e1/attachments': ok([]) });
    render(<EntriesTable hooks={hooksFor(api)} direction="receivable" />, { wrapper: wrapperFor() });
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Pedido #100' }));
    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByText(/Pagamento/);
    for (const name of ['Anexar arquivo', 'Estornar', 'Dar baixa', 'Cancelar lançamento', 'Editar']) {
      expect(within(dialog).queryByRole('button', { name })).not.toBeInTheDocument();
    }
  });
});

describe('create / edit entry', () => {
  it('creates an installment receivable with the competence month of the due date', async () => {
    const user = userEvent.setup();
    const api = mount({ 'POST /api/finance/entries': ok([entry()]) }, { isAdmin: true });
    await user.click(await screen.findByRole('button', { name: 'Novo lançamento' }));
    const dialog = screen.getByRole('dialog');
    await user.type(within(dialog).getByLabelText(/^Descrição/), 'Plano anual');
    await user.type(within(dialog).getByLabelText(/^Valor/), '1.200,00');
    const due = within(dialog).getByLabelText(/^Vencimento/);
    await user.clear(due);
    await user.type(due, '2026-11-15');
    await user.clear(within(dialog).getByLabelText('Parcelas'));
    await user.type(within(dialog).getByLabelText('Parcelas'), '3');
    await user.selectOptions(within(dialog).getByLabelText('Categoria'), 'cat-sales');
    await user.click(within(dialog).getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post.mock.calls[0][1]).toMatchObject({
      direction: 'receivable', description: 'Plano anual', amount_cents: 120000, due_date: '2026-11-15',
      competence_month: '2026-11-01', installments: 3, category_id: 'cat-sales',
    });
  });

  it('validates required fields before calling the API; only income categories on a receivable', async () => {
    const user = userEvent.setup();
    const api = mount({}, { isAdmin: true });
    await user.click(await screen.findByRole('button', { name: 'Novo lançamento' }));
    const dialog = screen.getByRole('dialog');
    const cats = within(within(dialog).getByLabelText('Categoria')).getAllByRole('option').map((o) => o.textContent);
    expect(cats).toContain('Vendas');
    expect(cats).not.toContain('Aluguel');
    await user.click(within(dialog).getByRole('button', { name: 'Salvar' }));
    expect(await within(dialog).findAllByText('Campo obrigatório')).not.toHaveLength(0);
    expect(within(dialog).getByText(/Informe um valor maior que zero/)).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('an account list with a gateway is selectable as expected account', async () => {
    const user = userEvent.setup();
    mount({}, { isAdmin: true });
    await user.click(await screen.findByRole('button', { name: 'Novo lançamento' }));
    const opts = within(within(screen.getByRole('dialog')).getByLabelText('Conta prevista')).getAllByRole('option').map((o) => o.textContent);
    expect(opts).toEqual(['Ainda não sei', ACC_BANK.name, ACC_GW.name]);
  });
});
