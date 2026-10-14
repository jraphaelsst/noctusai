import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, act, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ContractsTable } from './ContractsTable';
import { ApiError } from '../api';
import { contract, ok, page, setup } from './testUtils';

afterEach(cleanup);

function mount(routes: Record<string, unknown>, props: Partial<React.ComponentProps<typeof ContractsTable>> = {}) {
  const s = setup(routes);
  render(<s.Wrapper><ContractsTable hooks={s.hooks} {...props} /></s.Wrapper>);
  return s;
}

describe('ContractsTable', () => {
  it('skeleton on first load, then rows with status, model, per-period amount and the masked party', async () => {
    let resolve!: (v: unknown) => void;
    const s = setup();
    s.api.route('GET /api/contracts', () => new Promise((r) => (resolve = r)));
    render(<s.Wrapper><ContractsTable hooks={s.hooks} /></s.Wrapper>);
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    expect(screen.queryByText('Nenhum contrato ainda.')).not.toBeInTheDocument();
    await act(async () => resolve(page([
      contract({ status: 'active', end_date: '2027-10-31' }),
      contract({ id: 'c2', title: 'Site', billing_model: 'one_time', amount_cents: 500000, number: null, end_date: null, status: 'expired', lapsed: false }),
      contract({ id: 'c3', title: 'Vencido', status: 'active', end_date: '2026-01-31', lapsed: true }),
    ])));
    expect(await screen.findByText('Gestão de tráfego')).toBeInTheDocument();
    const row = screen.getByText('Gestão de tráfego').closest('tr')!;
    expect(within(row).getByText('Ativo')).toBeInTheDocument();
    expect(within(row).getByText('Recorrente')).toBeInTheDocument();
    expect(within(row).getByText(/R\$\s*1\.500,00\/período/)).toBeInTheDocument();
    expect(within(row).getByText(/até 31\/10\/2027/)).toBeInTheDocument();
    expect(screen.getByText(/R\$\s*5\.000,00$/)).toBeInTheDocument();
    expect(screen.getByText('Vencido', { selector: 'span' })).toBeInTheDocument(); // the lapsed badge
  });

  it('empty: plain state, and a different one under a filter', async () => {
    const user = userEvent.setup();
    mount({ 'GET /api/contracts': page([]) });
    expect(await screen.findByText('Nenhum contrato ainda.')).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Situação'), 'terminated');
    expect(await screen.findByText('Nenhum contrato encontrado para esse filtro.')).toBeInTheDocument();
  });

  it('a failed first load shows the retryable error, never an empty claim', async () => {
    const user = userEvent.setup();
    let fail = true;
    mount({ 'GET /api/contracts': () => { if (fail) throw new ApiError(500, 'boom', {}); return page([contract()]); } });
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
    expect(screen.queryByText('Nenhum contrato ainda.')).not.toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole('button', { name: 'Tentar novamente' }));
    expect(await screen.findByText('Gestão de tráfego')).toBeInTheDocument();
  });

  it('sends the filters to the API and pages', async () => {
    const user = userEvent.setup();
    const s = mount({ 'GET /api/contracts': page([contract()], { total: 45, total_pages: 3 }) });
    await screen.findByText('Gestão de tráfego');
    await user.selectOptions(screen.getByLabelText('Cobrança'), 'retainer');
    await screen.findByText('Gestão de tráfego');
    expect(s.api.get).toHaveBeenLastCalledWith('/api/contracts', expect.objectContaining({ billing_model: 'retainer', page: 1 }));
    await user.click(screen.getByRole('button', { name: 'Próxima' }));
    await screen.findByText('2 / 3');
  });

  it('the create button is a write affordance only', async () => {
    mount({ 'GET /api/contracts': page([]) });
    await screen.findByText('Nenhum contrato ainda.');
    expect(screen.queryByRole('button', { name: 'Novo contrato' })).not.toBeInTheDocument();
    cleanup();
    mount({ 'GET /api/contracts': page([]) }, { canWrite: true });
    expect(await screen.findByRole('button', { name: 'Novo contrato' })).toBeInTheDocument();
  });

  it('row click opens the editor on that contract (or calls onSelect)', async () => {
    const user = userEvent.setup();
    const picked: string[] = [];
    mount({ 'GET /api/contracts': page([contract()]), 'GET /api/contracts/c1': ok(contract()), 'GET /api/contracts/c1/versions': ok([]), 'GET /api/contracts/c1/billing-preview': ok({ items: [], billed: 0 }) }, { onSelect: (id) => picked.push(id) });
    await user.click(await screen.findByText('Gestão de tráfego'));
    expect(picked).toEqual(['c1']);
  });
});
