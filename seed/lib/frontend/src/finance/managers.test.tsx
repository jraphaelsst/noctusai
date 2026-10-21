import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AccountsManager } from './AccountsManager';
import { FinanceCategoryManager, flattenCategories } from './CategoryManager';
import { CostCentersManager } from './CostCentersManager';
import { RecurrencesManager } from './RecurrencesManager';
import { TransferDialog } from './TransferDialog';
import { ApiError } from '../api';
import { ACC_BANK, ACC_GW, CAT_RENT, CAT_RENT_SUB, CAT_SALES, CAT_TRANSFER, CC, baseRoutes, hooksFor, makeRoutedApi, ok, wrapperFor } from './testUtils';
import type { Recurrence } from './types';

afterEach(cleanup);
const nbsp = (s: string) => s.replace(/ /g, ' ');

describe('AccountsManager', () => {
  const routes = () => ({
    ...baseRoutes(),
    'GET /api/finance/accounts/acc-bank/balance': ok({ account_id: 'acc-bank', on: 'x', opening_balance_cents: 100000, movement_cents: 5000, balance_cents: 105000 }),
    'GET /api/finance/accounts/acc-gw/balance': ok({ account_id: 'acc-gw', on: 'x', opening_balance_cents: 0, movement_cents: 0, balance_cents: 0 }),
  });

  it('lists accounts with balance; staff see no actions', async () => {
    render(<AccountsManager hooks={hooksFor(makeRoutedApi(routes()))} />, { wrapper: wrapperFor() });
    expect(await screen.findByText('Itaú')).toBeInTheDocument();
    expect(await screen.findByLabelText('Saldo: Itaú')).toHaveTextContent('R$ 1.050,00');
    expect(screen.getByText(/Gateway de pagamento · asaas/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Nova conta' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Editar' })).not.toBeInTheDocument();
  });

  it('skeleton, empty and error states', async () => {
    const { unmount } = render(<AccountsManager hooks={hooksFor(makeRoutedApi({ 'GET /api/finance/accounts': () => new Promise(() => {}) }))} />, { wrapper: wrapperFor() });
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    unmount();
    render(<AccountsManager hooks={hooksFor(makeRoutedApi({ 'GET /api/finance/accounts': ok([]) }))} />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Nenhuma conta cadastrada/)).toBeInTheDocument();
    cleanup();
    render(<AccountsManager hooks={hooksFor(makeRoutedApi({ 'GET /api/finance/accounts': () => Promise.reject(new ApiError(500, 'x')) }))} />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
  });

  it('creates a gateway account (gateway name required) with a negative opening balance in cents', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ ...routes(), 'POST /api/finance/accounts': ok(ACC_GW) });
    render(<AccountsManager hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
    await user.click(await screen.findByRole('button', { name: 'Nova conta' }));
    const form = screen.getByRole('form', { name: 'Dados da conta' });
    await user.type(within(form).getByLabelText(/^Nome da conta/), 'Stripe');
    await user.selectOptions(within(form).getByLabelText('Tipo'), 'gateway');
    await user.click(within(form).getByRole('button', { name: 'Salvar' }));
    expect(await within(form).findByText(/Informe o gateway/)).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
    await user.type(within(form).getByLabelText(/^Gateway/), 'stripe');
    await user.type(within(form).getByLabelText(/Saldo inicial \(R\$\)/), '-12,50');
    await user.click(within(form).getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post.mock.calls[0][1]).toMatchObject({ name: 'Stripe', kind: 'gateway', gateway: 'stripe', opening_balance_cents: -1250 });
  });

  it('deactivates an account via PATCH active=false', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ ...routes(), 'PATCH /api/finance/accounts/acc-bank': ok({ ...ACC_BANK, active: false }) });
    render(<AccountsManager hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
    const row = (await screen.findByText('Itaú')).closest('li')!;
    await user.click(within(row).getByRole('button', { name: 'Desativar' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/finance/accounts/acc-bank', { active: false }));
  });
});

describe('AccountsManager delete', () => {
  const routes = () => ({
    ...baseRoutes(),
    'GET /api/finance/accounts/acc-bank/balance': ok({ account_id: 'acc-bank', on: 'x', opening_balance_cents: 0, movement_cents: 0, balance_cents: 0 }),
    'GET /api/finance/accounts/acc-gw/balance': ok({ account_id: 'acc-gw', on: 'x', opening_balance_cents: 0, movement_cents: 0, balance_cents: 0 }),
  });

  it('deletes an account after a second confirmation (admin only)', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ ...routes(), 'DELETE /api/finance/accounts/acc-bank': null });
    render(<AccountsManager hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
    const row = (await screen.findByText('Itaú')).closest('li')!;
    await user.click(within(row).getByRole('button', { name: 'Excluir' }));
    expect(api.delete).not.toHaveBeenCalled();
    await user.click(within(row).getByRole('button', { name: 'Sim, excluir' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/finance/accounts/acc-bank'));
  });

  it('surfaces the 409 message inline when the account has movements', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ ...routes(), 'DELETE /api/finance/accounts/acc-bank': () => Promise.reject(new ApiError(409, 'A conta tem movimentações; desative-a.')) });
    render(<AccountsManager hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
    const row = (await screen.findByText('Itaú')).closest('li')!;
    await user.click(within(row).getByRole('button', { name: 'Excluir' }));
    await user.click(within(row).getByRole('button', { name: 'Sim, excluir' }));
    expect(await screen.findByText(/A conta tem movimentações; desative-a\./)).toBeInTheDocument();
  });

  it('staff see no Excluir', async () => {
    render(<AccountsManager hooks={hooksFor(makeRoutedApi(routes()))} />, { wrapper: wrapperFor() });
    await screen.findByText('Itaú');
    expect(screen.queryByRole('button', { name: 'Excluir' })).not.toBeInTheDocument();
  });
});

describe('TransferDialog', () => {
  it('rejects the same account twice, then posts cents', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ ...baseRoutes(), 'POST /api/finance/transfers': ok({ transfer_group: 'g' }) });
    render(<TransferDialog hooks={hooksFor(api)} open onClose={() => {}} defaultFromId="acc-bank" />, { wrapper: wrapperFor() });
    const dialog = await screen.findByRole('dialog');
    await within(dialog).findAllByRole('option', { name: 'Asaas' });
    await user.selectOptions(within(dialog).getByLabelText(/^Entra na conta/), 'acc-bank');
    await user.type(within(dialog).getByLabelText(/^Valor/), '250,00');
    await user.click(within(dialog).getByRole('button', { name: 'Transferir' }));
    expect(await within(dialog).findByText('Escolha duas contas diferentes.')).toBeInTheDocument();
    await user.selectOptions(within(dialog).getByLabelText(/^Entra na conta/), 'acc-gw');
    await user.click(within(dialog).getByRole('button', { name: 'Transferir' }));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post.mock.calls[0][1]).toMatchObject({ from_account_id: 'acc-bank', to_account_id: 'acc-gw', amount_cents: 25000 });
  });
});

describe('FinanceCategoryManager (DRE line + behavior mapping)', () => {
  it('flattens a hierarchy depth-first, grouped by direction', () => {
    const rows = flattenCategories([CAT_RENT_SUB, CAT_TRANSFER, CAT_RENT, CAT_SALES]);
    expect(rows.map((r) => `${r.depth}:${r.cat.name}`)).toEqual(['0:Vendas', '0:Aluguel', '1:Condomínio', '0:Entre contas']);
  });

  it('shows the mapping columns, hides them for transfers, warns about unmapped categories', async () => {
    render(<FinanceCategoryManager hooks={hooksFor(makeRoutedApi(baseRoutes()))} />, { wrapper: wrapperFor() });
    expect(await screen.findByText('Vendas')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Linha do DRE' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Comportamento' })).toBeInTheDocument();
    const rent = screen.getByText('Aluguel').closest('tr')!;
    expect(within(rent).getByText('Sem linha (não classificada)')).toBeInTheDocument();
    expect(within(screen.getByText('Condomínio').closest('tr')!).getByText('Despesas administrativas')).toBeInTheDocument();
    expect(within(screen.getByText('Entre contas').closest('tr')!).getByText('Fora do DRE')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('1 categoria(s) sem linha do DRE');
  });

  it('admin maps a category inline: PATCH dre_line, offering only lines valid for its direction', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ ...baseRoutes(), 'PATCH /api/finance/categories/cat-rent': ok({ ...CAT_RENT, dre_line: 'administrative_expenses' }) });
    render(<FinanceCategoryManager hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
    const select = await screen.findByLabelText('Linha do DRE: Aluguel');
    const options = within(select).getAllByRole('option').map((o) => o.getAttribute('value'));
    expect(options).toContain('cost_of_sales');
    expect(options).not.toContain('gross_revenue'); // an income line on an expense category
    await user.selectOptions(select, 'administrative_expenses');
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/finance/categories/cat-rent', { dre_line: 'administrative_expenses' }));
    await user.selectOptions(screen.getByLabelText('Comportamento: Aluguel'), 'fixed');
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/finance/categories/cat-rent', { behavior: 'fixed' }));
  });

  it('staff see read-only text, no selects', async () => {
    render(<FinanceCategoryManager hooks={hooksFor(makeRoutedApi(baseRoutes()))} />, { wrapper: wrapperFor() });
    await screen.findByText('Vendas');
    expect(screen.queryByLabelText('Linha do DRE: Vendas')).not.toBeInTheDocument();
    expect(within(screen.getByText('Vendas').closest('tr')!).getByText('Receita bruta')).toBeInTheDocument();
    expect(within(screen.getByText('Vendas').closest('tr')!).getByText(/Variável/)).toBeInTheDocument();
  });

  it('creates a child category under a parent of the same direction with the mapping', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ ...baseRoutes(), 'POST /api/finance/categories': ok({ ...CAT_RENT, id: 'new' }) });
    render(<FinanceCategoryManager hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
    await user.click(await screen.findByRole('button', { name: 'Nova categoria' }));
    const form = screen.getByRole('form', { name: 'Dados da categoria' });
    await user.type(within(form).getByLabelText(/^Nome/), 'Água');
    const parentOptions = within(within(form).getByLabelText('Dentro de')).getAllByRole('option').map((o) => o.textContent);
    expect(parentOptions).toContain('Aluguel');
    expect(parentOptions).not.toContain('Vendas');
    await user.selectOptions(within(form).getByLabelText('Dentro de'), 'cat-rent');
    await user.selectOptions(within(form).getByLabelText('Linha do DRE'), 'administrative_expenses');
    await user.selectOptions(within(form).getByLabelText('Comportamento'), 'fixed');
    await user.click(within(form).getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post.mock.calls[0][1]).toEqual({ name: 'Água', direction: 'expense', parent_id: 'cat-rent', dre_line: 'administrative_expenses', behavior: 'fixed', is_das: false });
  });

  it('delete needs confirmation, is hidden for default categories, and shows a server refusal', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ ...baseRoutes(), 'DELETE /api/finance/categories/cat-rent-sub': () => Promise.reject(new ApiError(409, 'Categoria em uso')) });
    render(<FinanceCategoryManager hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
    const row = (await screen.findByText('Condomínio')).closest('tr')!;
    expect(within(screen.getByText('Vendas').closest('tr')!).queryByRole('button', { name: 'Excluir' })).not.toBeInTheDocument();
    await user.click(within(row).getByRole('button', { name: 'Excluir' }));
    expect(api.delete).not.toHaveBeenCalled();
    await user.click(within(row).getByRole('button', { name: 'Confirmar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Categoria em uso');
  });
});

describe('CostCentersManager', () => {
  it('lists, requires code and name, creates', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ ...baseRoutes(), 'POST /api/finance/cost-centers': ok(CC) });
    render(<CostCentersManager hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
    expect(await screen.findByText('LOJA')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Novo centro de custo' }));
    const form = screen.getByRole('form', { name: 'Dados do centro de custo' });
    await user.click(within(form).getByRole('button', { name: 'Salvar' }));
    expect(await within(form).findAllByText('Campo obrigatório')).toHaveLength(2);
    await user.type(within(form).getByLabelText(/^Código/), 'MKT');
    await user.type(within(form).getByLabelText(/^Nome/), 'Marketing');
    await user.click(within(form).getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/finance/cost-centers', { code: 'MKT', name: 'Marketing' }));
  });
  it('empty and error', async () => {
    render(<CostCentersManager hooks={hooksFor(makeRoutedApi({ 'GET /api/finance/cost-centers': ok([]) }))} />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Nenhum centro de custo/)).toBeInTheDocument();
    cleanup();
    render(<CostCentersManager hooks={hooksFor(makeRoutedApi({ 'GET /api/finance/cost-centers': () => Promise.reject(new ApiError(500, 'x')) }))} />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
  });
});

describe('RecurrencesManager', () => {
  const rec: Recurrence = {
    id: 'r1', frequency: 'monthly', next_date: '2026-11-05', end_date: null, active: true,
    template: { direction: 'payable', description: 'Aluguel da loja', amount_cents: 350000, category_id: 'cat-rent' },
  };
  it('lists with frequency and next date, pauses via PATCH', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ ...baseRoutes(), 'GET /api/finance/recurrences': ok([rec]), 'PATCH /api/finance/recurrences/r1': ok({ ...rec, active: false }) });
    render(<RecurrencesManager hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
    const row = (await screen.findByText('Aluguel da loja')).closest('li')!;
    expect(nbsp(row.textContent!)).toContain('R$ 3.500,00');
    expect(row.textContent).toContain('Todo mês');
    expect(row.textContent).toContain('05/11/2026');
    await user.click(within(row).getByRole('button', { name: 'Pausar' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/finance/recurrences/r1', { active: false }));
  });
  it('creates with a template body; end date before next date is refused client-side', async () => {
    const user = userEvent.setup();
    const api = makeRoutedApi({ ...baseRoutes(), 'GET /api/finance/recurrences': ok([]), 'POST /api/finance/recurrences': ok(rec) });
    render(<RecurrencesManager hooks={hooksFor(api)} isAdmin />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Nenhuma recorrência/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Nova recorrência' }));
    const form = screen.getByRole('form', { name: 'Dados da recorrência' });
    await user.type(within(form).getByLabelText(/^Descrição/), 'Internet');
    await user.type(within(form).getByLabelText(/^Valor/), '99,90');
    await user.clear(within(form).getByLabelText(/^Próxima data/));
    await user.type(within(form).getByLabelText(/^Próxima data/), '2026-11-10');
    await user.type(within(form).getByLabelText(/^Termina em/), '2026-11-01');
    await user.click(within(form).getByRole('button', { name: 'Salvar' }));
    expect(await within(form).findByText(/não pode ser antes/)).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
    await user.clear(within(form).getByLabelText(/^Termina em/));
    await user.click(within(form).getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post.mock.calls[0][1]).toMatchObject({
      frequency: 'monthly', next_date: '2026-11-10', end_date: null,
      template: { direction: 'payable', description: 'Internet', amount_cents: 9990 },
    });
  });
});
