/** ERP dashboard: organ-optional groups, every state (skeleton, error+retry, data), the numbers each tile derives. */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ApiError } from '../api';
import { makeRoutedApi } from '../organ-kit/testing';
import { createInventoryHooks, type InventoryApi } from '../inventory/hooks';
import { ErpDashboard } from './ErpDashboard';
import { createErpDashboardTranslator } from './i18n';
import { hooks, NOW, wrapperFor } from './testUtils';

afterEach(cleanup);

function mount(props: React.ComponentProps<typeof ErpDashboard>) {
  const Wrapper = wrapperFor();
  return render(<Wrapper><ErpDashboard now={NOW} {...props} /></Wrapper>);
}
const tile = (id: string) => screen.findByTestId(id);

describe('ErpDashboard', () => {
  it('renders only the groups whose hooks the host passed (organ-optional)', async () => {
    mount({ inventory: hooks.inventory() });
    expect(await tile('erp-inventory')).toBeInTheDocument();
    for (const id of ['erp-finance', 'erp-purchasing', 'erp-contracts', 'erp-quotes']) expect(screen.queryByTestId(id)).toBeNull();
  });

  it('says so when nothing is mounted (never a blank page)', () => {
    mount({});
    expect(screen.getByText('Nenhum módulo conectado a este painel.')).toBeInTheDocument();
  });

  it('finance: month result, cash, open AR/AP and overdue come from the finance reads', async () => {
    mount({ finance: hooks.finance() });
    expect(await within(await tile('erp-month-result')).findByText(/1\.234,56/)).toBeInTheDocument();
    expect(await within(await tile('erp-cash')).findByText(/5\.000,00/)).toBeInTheDocument();
    expect(await within(await tile('erp-open-receivable')).findByText(/3\.000,00/)).toBeInTheDocument();
    expect(await within(await tile('erp-open-payable')).findByText(/2\.000,00/)).toBeInTheDocument();
    expect(await within(await tile('erp-overdue-receivable')).findByText(/700,00/)).toBeInTheDocument();
    expect(await within(await tile('erp-overdue-payable')).findByText(/100,00/)).toBeInTheDocument();
  });

  it('inventory: low-stock count and valuation', async () => {
    mount({ inventory: hooks.inventory() });
    expect(await within(await tile('erp-low-stock')).findByText('3')).toBeInTheDocument();
    expect(await within(await tile('erp-valuation')).findByText(/999,00/)).toBeInTheDocument();
  });

  it('purchasing: approval = drafts; receipt = approved + sent + partially received', async () => {
    mount({ purchasing: hooks.purchasing() });
    expect(await within(await tile('erp-po-approval')).findByText('2')).toBeInTheDocument();
    expect(await within(await tile('erp-po-receipt')).findByText('5')).toBeInTheDocument();
  });

  it('contracts: active, expiring and the billings due within 30 days', async () => {
    mount({ contracts: hooks.contracts() });
    expect(await within(await tile('erp-contracts-active')).findByText('2')).toBeInTheDocument();
    expect(await within(await tile('erp-contracts-expiring')).findByText('2')).toBeInTheDocument();
    // only c1 bills inside 30 days of 14/10: R$ 1.000,00
    expect(await within(await tile('erp-contracts-billings')).findByText(/1\.000,00/)).toBeInTheDocument();
  });

  it('quotes: open total and those expiring within 7 days', async () => {
    mount({ quotes: hooks.quotes() });
    expect(await within(await tile('erp-quotes-open')).findByText('2')).toBeInTheDocument();
    expect(await within(await tile('erp-quotes-expiring')).findByText('1')).toBeInTheDocument();
  });

  it('shows a skeleton first (not an em-dash), then the value', async () => {
    mount({ inventory: hooks.inventory() });
    const t = screen.getByTestId('erp-low-stock');
    expect(within(t).queryByText('—')).toBeNull();
    expect(await within(t).findByText('3')).toBeInTheDocument();
  });

  it('a failing tile shows an error with retry while its siblings still load', async () => {
    const api = makeRoutedApi<InventoryApi>({
      'GET /api/inventory/low-stock': () => { throw new ApiError(500, 'rede caiu'); },
      'GET /api/inventory/valuation': { data: { method: 'average_cost', total_cents: 5_000, items: 1, by_warehouse: [] } },
    });
    mount({ inventory: createInventoryHooks(api) });
    const err = await tile('erp-low-stock-error');
    expect(within(err).getByText(/rede caiu/)).toBeInTheDocument();
    expect(await within(await tile('erp-valuation')).findByText(/50,00/)).toBeInTheDocument();
    await userEvent.click(within(err).getByRole('button', { name: 'Tentar novamente' }));
    expect(api.get.mock.calls.filter(([p]) => String(p).endsWith('/low-stock')).length).toBeGreaterThan(1);
  });

  it('honours a translator override', async () => {
    mount({ inventory: hooks.inventory(), t: createErpDashboardTranslator({ 'inventory.title': 'Stock' }) });
    expect(await screen.findByText('Stock')).toBeInTheDocument();
  });
});
