/** Organ behaviour: every state (skeleton, error+retry, empty, data, refreshing) and each write path. */
import { afterEach, describe, expect, it } from 'vitest';
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ApiError } from '../api';
import { createInventoryHooks } from '../inventory/hooks';
import { createItemsHooks } from '../items/hooks';
import { createPartiesHooks } from '../parties/hooks';
import { createPurchasingHooks } from './hooks';
import { PurchaseApproveButton } from './PurchaseApproveButton';
import { PurchaseOrderEditor } from './PurchaseOrderEditor';
import { PurchaseOrdersTable } from './PurchaseOrdersTable';
import { PurchaseReceiptsList } from './PurchaseReceiptsList';
import { PurchaseReceiveDialog } from './PurchaseReceiveDialog';
import { detail, line, LINE1, LINE2, makeApi, order, ORDER_ID, page, receipt, routeGet, wrapperFor } from './testUtils';

afterEach(cleanup);

function mount(ui: (hooks: ReturnType<typeof createPurchasingHooks>) => React.ReactElement, routes: Record<string, unknown> = {}) {
  const api = makeApi();
  routeGet(api, routes);
  const hooks = createPurchasingHooks(api);
  const Wrapper = wrapperFor();
  render(<Wrapper>{ui(hooks)}</Wrapper>);
  return api;
}

describe('PurchaseOrdersTable', () => {
  it('skeleton first, then rows with the status badge and the total', async () => {
    mount((h) => <PurchaseOrdersTable hooks={h} onOpen={() => undefined} />, { '/orders': page([order({ status: 'partially_received' })]) });
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    const row = await screen.findByTestId('order-row');
    expect(within(row).getByText('Recebido parcialmente')).toBeInTheDocument();
    expect(within(row).getByText('#7')).toBeInTheDocument();
    expect(within(row).getByText('Tintas Ltda')).toBeInTheDocument();
    expect(row.textContent).toContain('R$');
    expect(row.textContent).toContain('20/10/2026');
  });

  it('empty state, and error-with-retry that recovers (never a blank panel)', async () => {
    mount((h) => <PurchaseOrdersTable hooks={h} />, { '/orders': page([]) });
    expect(await screen.findByText('Nenhum pedido de compra.')).toBeInTheDocument();
    cleanup();
    const api = makeApi();
    api.get.mockRejectedValueOnce(new Error('rede caiu')).mockResolvedValue(page([order()]));
    const Wrapper = wrapperFor();
    const user = userEvent.setup();
    render(<Wrapper><PurchaseOrdersTable hooks={createPurchasingHooks(api)} /></Wrapper>);
    expect(await screen.findByText(/rede caiu/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Tentar novamente' }));
    expect(await screen.findByTestId('order-row')).toBeInTheDocument();
  });

  it('a status filter refetches and keeps the rows on screen meanwhile (no skeleton flash)', async () => {
    const user = userEvent.setup();
    const api = mount((h) => <PurchaseOrdersTable hooks={h} />, { '/orders': page([order()]) });
    await screen.findByTestId('order-row');
    let resolve!: (v: unknown) => void;
    api.get.mockImplementationOnce(() => new Promise((r) => (resolve = r)));
    await user.selectOptions(screen.getByLabelText('Status'), 'approved');
    expect(screen.queryByTestId('list-loading')).toBeNull();
    expect(screen.getByTestId('order-row')).toBeInTheDocument();
    expect(await screen.findByRole('status')).toHaveTextContent('Atualizando');
    await act(async () => resolve(page([order({ status: 'approved' })])));
    await waitFor(() => expect(screen.queryByRole('status')).toBeNull());
    expect(api.get).toHaveBeenLastCalledWith('/api/purchasing/orders', { status: 'approved', page: 1 });
  });

  it('the new-order button only shows for writers', async () => {
    mount((h) => <PurchaseOrdersTable hooks={h} onNew={() => undefined} />, { '/orders': page([order()]) });
    await screen.findByTestId('order-row');
    expect(screen.queryByRole('button', { name: 'Novo pedido' })).toBeNull();
    cleanup();
    mount((h) => <PurchaseOrdersTable hooks={h} canWrite onNew={() => undefined} />, { '/orders': page([order()]) });
    expect(await screen.findByRole('button', { name: 'Novo pedido' })).toBeInTheDocument();
  });
});

describe('PurchaseApproveButton', () => {
  function setup(props: Partial<React.ComponentProps<typeof PurchaseApproveButton>> = {}, status: 'draft' | 'approved' | 'received' = 'draft') {
    const api = makeApi();
    api.post.mockResolvedValue({ data: order({ status: 'approved' }) });
    const hooks = createPurchasingHooks(api);
    const Wrapper = wrapperFor();
    const done: unknown[] = [];
    render(<Wrapper><PurchaseApproveButton hooks={hooks} order={{ id: ORDER_ID, status, total_cents: 10500 }} onDone={(o) => done.push(o)} {...props} /></Wrapper>);
    return { api, done };
  }

  it('draft: approve posts to the approve route and reports the new order', async () => {
    const user = userEvent.setup();
    const { api, done } = setup();
    await user.click(screen.getByRole('button', { name: 'Aprovar' }));
    await waitFor(() => expect(done).toHaveLength(1));
    expect(api.post).toHaveBeenCalledWith(`/api/purchasing/orders/${ORDER_ID}/approve`);
  });

  it('a server refusal is rendered with its stable code\'s pt-BR copy', async () => {
    const user = userEvent.setup();
    const { api } = setup();
    api.post.mockRejectedValue(new ApiError(403, 'x', { error: { code: 'aprovacao_acima_do_limite', message: 'x' } }));
    await user.click(screen.getByRole('button', { name: 'Aprovar' }));
    expect(await screen.findByText(/acima do limite de aprovação/)).toBeInTheDocument();
  });

  it('warns up front when the order is above the org threshold, and hides approve when the host says the user cannot', () => {
    setup({ thresholdCents: 5000 });
    expect(screen.getByTestId('approve-above')).toHaveTextContent('R$');
    cleanup();
    setup({ canApprove: false });
    expect(screen.queryByRole('button', { name: 'Aprovar' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Cancelar pedido' })).toBeInTheDocument();
  });

  it('approved: send; received: no lifecycle action; cancel only for managers', async () => {
    const user = userEvent.setup();
    const { api } = setup({}, 'approved');
    await user.click(screen.getByRole('button', { name: 'Marcar como enviado' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(`/api/purchasing/orders/${ORDER_ID}/send`));
    cleanup();
    setup({}, 'received');
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    cleanup();
    setup({ canManage: false }, 'approved');
    expect(screen.queryAllByRole('button')).toHaveLength(0);
  });
});

describe('PurchaseReceiveDialog', () => {
  const lines = [line({ qty: 10, received_qty: 4 }), line({ id: LINE2, line_no: 2, description: 'Pincel', qty: 2.5, received_qty: 2.5 }), line({ id: 'line-3', line_no: 3, description: 'Rolo', qty: 3, received_qty: 0 })];
  function setup(answer: unknown = { data: { ...receipt(), replayed: false, order_status: 'received' } }) {
    const api = makeApi();
    api.post.mockResolvedValue(answer);
    const hooks = createPurchasingHooks(api);
    const Wrapper = wrapperFor();
    const closed: number[] = [];
    render(<Wrapper><PurchaseReceiveDialog hooks={hooks} open onClose={() => closed.push(1)} order={{ id: ORDER_ID, number: 7, lines }} /></Wrapper>);
    return { api, closed };
  }

  it('lists only lines with an open balance, defaulting each quantity to what is open', () => {
    setup();
    const rows = screen.getAllByTestId('receive-line');
    expect(rows).toHaveLength(2); // the fully received line is not offered
    expect(within(rows[0]).getByLabelText(/Receber agora Tinta/)).toHaveValue('6');
    expect(within(rows[1]).getByLabelText(/Receber agora Rolo/)).toHaveValue('3');
  });

  it('a partial receipt sends decimal strings, the date, the note and ONE idempotency key', async () => {
    const user = userEvent.setup();
    const { api, closed } = setup();
    const tinta = screen.getByLabelText(/Receber agora Tinta/);
    await user.clear(tinta);
    await user.type(tinta, '2,5');
    await user.clear(screen.getByLabelText(/Receber agora Rolo/));
    await user.type(screen.getByLabelText('Observação (nota fiscal, etc.)'), 'NF 123');
    await user.click(screen.getByRole('button', { name: 'Registrar recebimento' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    const [path, body] = api.post.mock.calls[0];
    expect(path).toBe(`/api/purchasing/orders/${ORDER_ID}/receipts`);
    expect(body.lines).toEqual([{ order_line_id: LINE1, qty: '2.5' }]);
    expect(body.note).toBe('NF 123');
    expect(body.received_on).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(body.idempotency_key).toBeTruthy();
    await waitFor(() => expect(closed).toHaveLength(1));
  });

  it('refuses a quantity above the open balance or invalid, before any request', async () => {
    const user = userEvent.setup();
    const { api } = setup();
    const tinta = screen.getByLabelText(/Receber agora Tinta/);
    await user.clear(tinta);
    await user.type(tinta, '6,5');
    await user.click(screen.getByRole('button', { name: 'Registrar recebimento' }));
    expect(await screen.findByText('A quantidade excede o saldo em aberto.')).toBeInTheDocument();
    await user.clear(tinta);
    await user.type(tinta, 'abc');
    await user.click(screen.getByRole('button', { name: 'Registrar recebimento' }));
    expect(await screen.findByText(/Informe ao menos uma quantidade válida/)).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('a retry after a failure reuses the SAME idempotency key (a replay, never a second receipt)', async () => {
    const user = userEvent.setup();
    const { api } = setup();
    api.post.mockRejectedValueOnce(new ApiError(409, 'x', { error: { code: 'recebimento_excede_pedido', message: 'x' } }));
    await user.click(screen.getByRole('button', { name: 'Registrar recebimento' }));
    expect(await screen.findByText('A quantidade recebida excede o saldo do pedido.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Registrar recebimento' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    expect(api.post.mock.calls[0][1].idempotency_key).toBe(api.post.mock.calls[1][1].idempotency_key);
  });

  it('a committed receipt whose posting did not finish says so, stays open, and can be reposted', async () => {
    const user = userEvent.setup();
    const { api, closed } = setup({ data: { ...receipt({ finance_posted_at: null, posted: false, posting_error: 'categoria_inativa: A categoria está inativa.' }), replayed: false, order_status: 'received' } });
    await user.click(screen.getByRole('button', { name: 'Registrar recebimento' }));
    const warning = await screen.findByTestId('posting-warning');
    expect(warning).toHaveTextContent('categoria_inativa');
    expect(closed).toHaveLength(0);
    api.post.mockResolvedValueOnce({ data: receipt() });
    await user.click(within(warning).getByRole('button', { name: 'Reprocessar' }));
    await waitFor(() => expect(api.post).toHaveBeenLastCalledWith('/api/purchasing/receipts/rc-1/post'));
    await waitFor(() => expect(closed).toHaveLength(1));
  });

  it('nothing open: says so and offers no submit', () => {
    const api = makeApi();
    const Wrapper = wrapperFor();
    render(<Wrapper><PurchaseReceiveDialog hooks={createPurchasingHooks(api)} open onClose={() => undefined} order={{ id: ORDER_ID, number: 7, lines: [line({ received_qty: 10 })] }} /></Wrapper>);
    expect(screen.getByText('Não há saldo em aberto neste pedido.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Registrar recebimento' })).toBeDisabled();
  });
});

describe('PurchaseReceiptsList', () => {
  it('skeleton, rows with posting state, empty and error states', async () => {
    mount((h) => <PurchaseReceiptsList hooks={h} orderId={ORDER_ID} />, { '/receipts': page([receipt(), receipt({ id: 'rc-2', receipt_no: 2, stock_posted_at: null, posted: false, posting_error: 'deposito_inativo: O depósito está inativo.' })]) });
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    const rows = await screen.findAllByTestId('receipt-row');
    expect(within(rows[0]).getByText('Lançado')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Pendente')).toBeInTheDocument();
    expect(rows[1].textContent).toContain('deposito_inativo');
    expect(screen.queryByRole('button', { name: 'Reprocessar' })).toBeNull(); // read-only user
    cleanup();
    mount((h) => <PurchaseReceiptsList hooks={h} />, { '/receipts': page([]) });
    expect(await screen.findByText('Nenhum recebimento.')).toBeInTheDocument();
  });

  it('a writer can repost a pending receipt', async () => {
    const user = userEvent.setup();
    const api = mount((h) => <PurchaseReceiptsList hooks={h} canWrite />, { '/receipts': page([receipt({ finance_posted_at: null, posted: false })]) });
    api.post.mockResolvedValue({ data: receipt() });
    await user.click(await screen.findByRole('button', { name: 'Reprocessar' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/purchasing/receipts/rc-1/post'));
  });
});

describe('PurchaseOrderEditor', () => {
  it('free-text supplier + manual lines: computes the totals the server will and sends the whole order', async () => {
    const user = userEvent.setup();
    const api = mount((h) => <PurchaseOrderEditor hooks={h} />);
    api.post.mockResolvedValue({ data: order() });
    await user.type(screen.getByLabelText('Nome do fornecedor'), 'Tintas Ltda');
    await user.click(screen.getByRole('button', { name: 'Adicionar item' }));
    await user.type(screen.getByLabelText('Descrição'), 'Tinta');
    const qty = screen.getByLabelText('Qtd.');
    await user.clear(qty);
    await user.type(qty, '2,5');
    await user.type(screen.getByLabelText('Custo unit. (R$)'), '3,33');
    await user.type(screen.getByLabelText('Frete (R$)'), '10');
    await user.type(screen.getByLabelText('Desconto (R$)'), '5');
    const totals = screen.getByTestId('editor-totals');
    expect(totals.textContent).toContain('8,33'); // round(2.5 x 333) = 833 cents
    expect(totals.textContent).toContain('13,33'); // + 10,00 freight - 5,00 discount
    await user.click(screen.getByRole('button', { name: 'Salvar rascunho' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    const [path, body] = api.post.mock.calls[0];
    expect(path).toBe('/api/purchasing/orders');
    expect(body).toMatchObject({ supplier_name: 'Tintas Ltda', freight_cents: 1000, discount_cents: 500, other_cents: 0, installments_count: 1, first_due_days: 30, interval_days: 30 });
    expect(body.lines).toEqual([{ item_id: null, description: 'Tinta', unit: null, qty: '2.5', unit_cost_cents: 333 }]);
  });

  it('validates before sending: supplier, lines, money, terms', async () => {
    const user = userEvent.setup();
    const api = mount((h) => <PurchaseOrderEditor hooks={h} />);
    await user.click(screen.getByRole('button', { name: 'Salvar rascunho' }));
    expect(await screen.findByText('Informe o fornecedor.')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Nome do fornecedor'), 'X');
    await user.click(screen.getByRole('button', { name: 'Salvar rascunho' }));
    expect(await screen.findByText(/com quantidade e custo/)).toBeInTheDocument();
    await user.type(screen.getByLabelText('Frete (R$)'), 'abc');
    await user.click(screen.getByRole('button', { name: 'Salvar rascunho' }));
    expect(await screen.findByText(/Valor inválido/)).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('picks the supplier from the parties organ and item lines from the items organ (default unit cost from the item)', async () => {
    const user = userEvent.setup();
    const partiesApi = makeApi();
    partiesApi.get.mockResolvedValue({ data: [{ id: 'party-9', legal_name: 'Razão SA', trade_name: 'Razão', is_active: true, roles: ['supplier'] }], pagination: { page: 1, page_size: 8, total: 1 } });
    const itemsApi = makeApi();
    itemsApi.get.mockResolvedValue({ data: [{ id: 'item-9', sku: 'TNT-1', name: 'Tinta branca', unit: 'L', cost_cents: 1250 }], pagination: { page: 1, page_size: 20, total: 1 } });
    const invApi = makeApi();
    invApi.get.mockResolvedValue({ data: [{ id: 'wh-1', name: 'Matriz', code: 'MTZ', is_default: true, active: true }] });
    const api = mount((h) => (
      <PurchaseOrderEditor
        hooks={h}
        partiesHooks={createPartiesHooks(partiesApi as never)}
        itemsHooks={createItemsHooks(itemsApi as never)}
        inventoryHooks={createInventoryHooks(invApi)}
      />
    ));
    api.post.mockResolvedValue({ data: order() });
    await user.click(await screen.findByRole('button', { name: 'Razão' }));
    expect(screen.getByTestId('supplier-chosen')).toHaveTextContent('Razão');
    await waitFor(() => expect(screen.getByLabelText('Depósito de entrada')).toHaveValue('wh-1'));
    await user.click(await screen.findByRole('button', { name: /TNT-1/ }));
    expect(screen.getByLabelText('Custo unit. (R$)')).toHaveValue('12,50');
    expect(partiesApi.get).toHaveBeenCalledWith('/api/parties', expect.objectContaining({ role: 'supplier' }));
    await user.click(screen.getByRole('button', { name: 'Salvar rascunho' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    const body = api.post.mock.calls[0][1];
    expect(body.party_id).toBe('party-9');
    expect(body.supplier_name).toBeUndefined(); // the server snapshots it from the party
    expect(body.warehouse_id).toBe('wh-1');
    expect(body.lines[0]).toMatchObject({ item_id: 'item-9', unit: 'L', unit_cost_cents: 1250, qty: '1' });
  });

  it('editing a draft loads it and PUTs the replacement; a non-draft opens read-only', async () => {
    const user = userEvent.setup();
    const api = mount((h) => <PurchaseOrderEditor hooks={h} orderId={ORDER_ID} />, { [`/orders/${ORDER_ID}`]: { data: detail() } });
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    expect(await screen.findByDisplayValue('Tinta acrílica')).toBeInTheDocument();
    expect(screen.getByTestId('supplier-chosen')).toHaveTextContent('Tintas Ltda');
    api.put.mockResolvedValue({ data: order() });
    await user.click(screen.getByRole('button', { name: 'Salvar rascunho' }));
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1));
    expect(api.put.mock.calls[0][0]).toBe(`/api/purchasing/orders/${ORDER_ID}`);
    expect(api.put.mock.calls[0][1]).toMatchObject({ party_id: 'party-1', freight_cents: 1000, discount_cents: 500, installments_count: 2, interval_days: 15 });
    cleanup();
    mount((h) => <PurchaseOrderEditor hooks={h} orderId={ORDER_ID} />, { [`/orders/${ORDER_ID}`]: { data: detail({ status: 'approved' }) } });
    expect(await screen.findByTestId('editor-readonly')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Salvar rascunho' })).toBeNull();
  });

  it('loading an order that fails shows the error with retry, not an empty form', async () => {
    const api = makeApi();
    api.get.mockRejectedValue(new Error('sem rede'));
    const Wrapper = wrapperFor();
    render(<Wrapper><PurchaseOrderEditor hooks={createPurchasingHooks(api)} orderId={ORDER_ID} /></Wrapper>);
    expect(await screen.findByText(/sem rede/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument();
  });

  it('a server refusal on save is shown with its pt-BR copy', async () => {
    const user = userEvent.setup();
    const api = mount((h) => <PurchaseOrderEditor hooks={h} />);
    api.post.mockRejectedValue(new ApiError(409, 'x', { error: { code: 'pedido_nao_editavel', message: 'x' } }));
    await user.type(screen.getByLabelText('Nome do fornecedor'), 'X');
    await user.click(screen.getByRole('button', { name: 'Adicionar item' }));
    await user.type(screen.getByLabelText('Descrição'), 'a');
    await user.type(screen.getByLabelText('Custo unit. (R$)'), '1');
    await user.click(screen.getByRole('button', { name: 'Salvar rascunho' }));
    expect(await screen.findByText('Só é possível editar um pedido em rascunho.')).toBeInTheDocument();
  });
});
