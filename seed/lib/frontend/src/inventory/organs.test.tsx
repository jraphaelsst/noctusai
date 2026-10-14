/** Organ behaviour: every state (skeleton, error+retry, empty, data, refreshing), and each write path. */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ApiError } from '../api';
import { createInventoryHooks } from './hooks';
import { KardexView } from './KardexView';
import { LowStockAlerts } from './LowStockAlerts';
import { StockAdjustDialog } from './StockAdjustDialog';
import { StockBalancesTable } from './StockBalancesTable';
import { TransferDialog } from './TransferDialog';
import { ValuationTile } from './ValuationTile';
import { WarehousesManager } from './WarehousesManager';
import { balance, ITEM, makeApi, move, page, routeGet, warehouse, WH1, WH2, wrapperFor } from './testUtils';

afterEach(cleanup);

function mount(ui: (hooks: ReturnType<typeof createInventoryHooks>) => React.ReactElement, routes: Record<string, unknown>) {
  const api = makeApi();
  routeGet(api, routes);
  const hooks = createInventoryHooks(api);
  const Wrapper = wrapperFor();
  render(<Wrapper>{ui(hooks)}</Wrapper>);
  return api;
}

const WHS = { '/warehouses': { data: [warehouse(), warehouse({ id: WH2, name: 'Filial', code: 'FIL', is_default: false })] } };

describe('StockBalancesTable', () => {
  it('skeleton first, then rows with available, value and the low-stock badge', async () => {
    mount((hooks) => <StockBalancesTable hooks={hooks} />, { ...WHS, '/balances': page([balance({ min_qty: 9, low_stock: true })]) });
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    const row = await screen.findByTestId('balance-row');
    expect(within(row).getByText('Baixo')).toBeInTheDocument();
    expect(within(row).getByText('Matriz')).toBeInTheDocument();
    expect(row.textContent).toContain('R$');
    expect(within(row).getByText('8')).toBeInTheDocument();
  });

  it('empty state and error-with-retry (never a blank panel)', async () => {
    mount((hooks) => <StockBalancesTable hooks={hooks} />, { ...WHS, '/balances': page([]) });
    expect(await screen.findByText('Nenhum item em estoque.')).toBeInTheDocument();
    cleanup();
    const api = makeApi();
    api.get.mockImplementation((p: string) => (p.endsWith('/warehouses') ? Promise.resolve(WHS['/warehouses']) : Promise.reject(new Error('rede caiu'))));
    const Wrapper = wrapperFor();
    render(<Wrapper><StockBalancesTable hooks={createInventoryHooks(api)} /></Wrapper>);
    expect(await screen.findByText(/rede caiu/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument();
  });

  it('row actions only for writers; the count dialog opens from a row', async () => {
    const user = userEvent.setup();
    mount((hooks) => <StockBalancesTable hooks={hooks} canWrite onOpenKardex={() => undefined} />, { ...WHS, '/balances': page([balance()]) });
    await user.click(await screen.findByRole('button', { name: 'Contagem' }));
    expect(await screen.findByRole('dialog', { name: 'Contagem de estoque' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Kardex' })).toBeInTheDocument();
  });

  it('read-only users get no write actions', async () => {
    mount((hooks) => <StockBalancesTable hooks={hooks} />, { ...WHS, '/balances': page([balance()]) });
    await screen.findByTestId('balance-row');
    expect(screen.queryByRole('button', { name: 'Contagem' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Transferir' })).toBeNull();
  });
});

describe('StockAdjustDialog', () => {
  function open() {
    const api = makeApi();
    routeGet(api, WHS);
    api.post.mockResolvedValue({ data: { status: 'ok', moves: [] } });
    const hooks = createInventoryHooks(api);
    const Wrapper = wrapperFor();
    let closed = 0;
    render(<Wrapper><StockAdjustDialog hooks={hooks} open onClose={() => { closed += 1; }} itemId={ITEM} warehouseId={WH1} currentOnHand={10} /></Wrapper>);
    return { api, closed: () => closed };
  }

  it('shows the signed difference and sends the COUNTED quantity as a decimal string', async () => {
    const user = userEvent.setup();
    const { api, closed } = open();
    await user.type(screen.getByLabelText(/Quantidade contada/), '7,5');
    expect(screen.getByTestId('adjust-delta').textContent).toContain('-2,5');
    await user.type(screen.getByLabelText(/Motivo/), 'quebra');
    await user.click(screen.getByRole('button', { name: 'Registrar contagem' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/inventory/adjust', { item_id: ITEM, warehouse_id: WH1, counted_qty: '7.5', note: 'quebra' }));
    await waitFor(() => expect(closed()).toBe(1));
  });

  it('asks for a unit cost only on a surplus, and sends it as cents', async () => {
    const user = userEvent.setup();
    const { api } = open();
    await user.type(screen.getByLabelText(/Quantidade contada/), '12');
    await user.type(await screen.findByLabelText(/Custo unitário/), '2,50');
    await user.click(screen.getByRole('button', { name: 'Registrar contagem' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/inventory/adjust', { item_id: ITEM, warehouse_id: WH1, counted_qty: '12', unit_cost_cents: 250 }));
  });

  it('blocks an invalid count client-side and maps a server refusal to pt-BR copy', async () => {
    const user = userEvent.setup();
    const { api } = open();
    await user.click(screen.getByRole('button', { name: 'Registrar contagem' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Informe uma quantidade contada válida');
    expect(api.post).not.toHaveBeenCalled();
    api.post.mockRejectedValue(new ApiError(409, 'x', { error: { code: 'abaixo_reservado' } }));
    await user.type(screen.getByLabelText(/Quantidade contada/), '1');
    await user.click(screen.getByRole('button', { name: 'Registrar contagem' }));
    expect(await screen.findByText('A contagem ficaria abaixo da quantidade reservada.')).toBeInTheDocument();
  });
});

describe('TransferDialog', () => {
  it('offers only OTHER warehouses and posts the transfer', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    routeGet(api, WHS);
    api.post.mockResolvedValue({ data: { status: 'ok', moves: [] } });
    const Wrapper = wrapperFor();
    render(<Wrapper><TransferDialog hooks={createInventoryHooks(api)} open onClose={() => undefined} itemId={ITEM} fromWarehouseId={WH1} available={8} /></Wrapper>);
    const select = await screen.findByRole('combobox');
    await waitFor(() => expect(within(select).getAllByRole('option')).toHaveLength(1));
    expect(within(select).getByRole('option', { name: 'Filial' })).toBeInTheDocument();
    await user.type(screen.getByLabelText(/Quantidade/), '3,5');
    await user.click(screen.getByRole('button', { name: 'Transferir' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/inventory/transfer', { item_id: ITEM, from_warehouse_id: WH1, to_warehouse_id: WH2, qty: '3.5' }));
  });

  it('refuses a zero quantity before calling the API', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    routeGet(api, WHS);
    const Wrapper = wrapperFor();
    render(<Wrapper><TransferDialog hooks={createInventoryHooks(api)} open onClose={() => undefined} itemId={ITEM} fromWarehouseId={WH1} /></Wrapper>);
    await screen.findByRole('option', { name: 'Filial' });
    await user.type(screen.getByLabelText(/Quantidade/), '0');
    await user.click(screen.getByRole('button', { name: 'Transferir' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('maior que zero');
    expect(api.post).not.toHaveBeenCalled();
  });
});

describe('KardexView', () => {
  it('renders the running balance and cost, signs outflows, and the empty state', async () => {
    mount(
      (hooks) => <KardexView hooks={hooks} itemId={ITEM} />,
      { ...WHS, '/kardex': page([move(), move({ id: 'm2', seq: 2, kind: 'out', qty: 4, on_hand_after: 6 }), move({ id: 'm3', seq: 3, kind: 'adjust', qty: -1, on_hand_after: 5 })]) },
    );
    const rows = await screen.findAllByTestId('kardex-row');
    expect(rows.map((r) => r.getAttribute('data-kind'))).toEqual(['in', 'out', 'adjust']);
    expect(rows[1].textContent).toContain('-4');
    expect(rows[2].textContent).toContain('-1');
    expect(within(rows[1]).getByText('6')).toBeInTheDocument();
    cleanup();
    mount((hooks) => <KardexView hooks={hooks} itemId={ITEM} />, { ...WHS, '/kardex': page([]) });
    expect(await screen.findByText('Nenhuma movimentação para este item.')).toBeInTheDocument();
  });
});

describe('WarehousesManager', () => {
  it('lists with the default badge and creates a warehouse (writers only)', async () => {
    const user = userEvent.setup();
    const api = mount((hooks) => <WarehousesManager hooks={hooks} canWrite />, WHS);
    api.post.mockResolvedValue({ data: warehouse({ id: 'w3' }) });
    const rows = await screen.findAllByTestId('warehouse-row');
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText('Padrão')).toBeInTheDocument();
    await user.type(screen.getByLabelText(/Nome/), 'Depósito SP');
    await user.type(screen.getByLabelText(/Código/), 'SP1');
    await user.click(screen.getByRole('button', { name: 'Novo depósito' }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/inventory/warehouses', { name: 'Depósito SP', code: 'SP1', address: { city: null, state: null } }),
    );
  });

  it('shows the server refusal (duplicate code) instead of swallowing it', async () => {
    const user = userEvent.setup();
    const api = mount((hooks) => <WarehousesManager hooks={hooks} canWrite />, WHS);
    api.post.mockRejectedValue(new ApiError(409, 'dup', { error: { code: 'deposito_duplicado' } }));
    await screen.findAllByTestId('warehouse-row');
    await user.type(screen.getByLabelText(/Nome/), 'A');
    await user.type(screen.getByLabelText(/Código/), 'MTZ');
    await user.click(screen.getByRole('button', { name: 'Novo depósito' }));
    expect(await screen.findByText('Já existe um depósito com este código.')).toBeInTheDocument();
  });

  it('read-only users see no form and no actions; make-default patches', async () => {
    mount((hooks) => <WarehousesManager hooks={hooks} />, WHS);
    await screen.findAllByTestId('warehouse-row');
    expect(screen.queryByRole('form')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Definir como padrão' })).toBeNull();
    cleanup();
    const user = userEvent.setup();
    const api = mount((hooks) => <WarehousesManager hooks={hooks} canWrite />, WHS);
    api.patch.mockResolvedValue({ data: warehouse() });
    await user.click(await screen.findByRole('button', { name: 'Definir como padrão' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith(`/api/inventory/warehouses/${WH2}`, { is_default: true }));
  });
});

describe('LowStockAlerts + ValuationTile', () => {
  it('lists low items with their threshold, and the empty state', async () => {
    mount((hooks) => <LowStockAlerts hooks={hooks} />, { ...WHS, '/low-stock': { data: [balance({ available: 1, min_qty: 3, low_stock: true })] } });
    const row = await screen.findByTestId('low-stock-row');
    expect(row.textContent).toContain('Disponível 1 · mínimo 3');
    expect(screen.getByText('1 item(ns) abaixo do mínimo')).toBeInTheDocument();
    cleanup();
    mount((hooks) => <LowStockAlerts hooks={hooks} />, { ...WHS, '/low-stock': { data: [] } });
    expect(await screen.findByText('Nenhum item abaixo do mínimo.')).toBeInTheDocument();
  });

  it('valuation shows the total in BRL at average cost, and an empty state when nothing is valued', async () => {
    mount((hooks) => <ValuationTile hooks={hooks} />, { '/valuation': { data: { method: 'average_cost', total_cents: 493800, items: 3, by_warehouse: [] } } });
    expect((await screen.findByTestId('valuation-total')).textContent).toMatch(/4\.938,00/);
    expect(screen.getByText(/Custo médio ponderado/)).toBeInTheDocument();
    cleanup();
    mount((hooks) => <ValuationTile hooks={hooks} />, { '/valuation': { data: { method: 'average_cost', total_cents: 0, items: 0, by_warehouse: [] } } });
    expect(await screen.findByText('Sem estoque valorizado.')).toBeInTheDocument();
  });
});
