import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ItemEditor, buildItemInput } from './ItemEditor';
import { createItemsHooks } from './hooks';
import { ApiError } from '../api';
import { EAN13, category, item, makeApi, routeGet, wrapperFor } from './testUtils';

afterEach(cleanup);

function mount(props: Record<string, unknown> = {}, routes: Record<string, unknown> = {}) {
  const api = makeApi();
  routeGet(api, { '/api/items/categories': { data: [category()] }, '/api/items/i1': { data: item({ ncm: '73181500', origem: 1 }) }, ...routes });
  const hooks = createItemsHooks(api);
  const Wrapper = wrapperFor();
  render(<Wrapper><ItemEditor hooks={hooks} {...props} /></Wrapper>);
  return api;
}

describe('buildItemInput', () => {
  const base = {
    sku: 'ab-1', name: ' Parafuso ', description: '', item_type: 'goods', unit: 'UN', category_id: '', cost: '12,50', price: '',
    is_active: true, ncm: '7318.15.00', cest: '', cfop: '5.102', origem: '0', gtin: EAN13, weight: '10', length: '', width: '', height: '',
  };
  it('turns reais into integer cents and canonicalises the fiscal block', () => {
    const { body, errors } = buildItemInput(base);
    expect(errors).toEqual({});
    expect(body).toMatchObject({
      sku: 'AB-1', name: 'Parafuso', cost_cents: 1250, price_cents: null, ncm: '73181500', cfop_default: '5102', origem: 0,
      gtin: EAN13, weight_g: 10, length_mm: null, category_id: null, description: null,
    });
  });
  it('reports every bad field with a pt-BR message and builds no body', () => {
    const { body, errors } = buildItemInput({ ...base, sku: 'a b', name: '', ncm: '1', cfop: '4102', gtin: '7891000100104', cost: 'x', weight: '1.5' });
    expect(body).toBeNull();
    expect(Object.keys(errors).sort()).toEqual(['cfop', 'cost', 'gtin', 'name', 'ncm', 'sku', 'weight']);
  });
});

describe('ItemEditor — create', () => {
  it('saves a new item with cents and calls onSaved', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    const api = mount({ onSaved });
    api.post.mockResolvedValue({ data: item({ id: 'new' }) });
    await user.type(screen.getByLabelText(/SKU/), 'x-1');
    await user.type(screen.getByLabelText(/Nome/), 'Novo');
    await user.clear(screen.getByLabelText(/Custo/));
    await user.type(screen.getByLabelText(/Custo/), '1.234,56');
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ id: 'new' })));
    expect(api.post).toHaveBeenCalledWith('/api/items', expect.objectContaining({ sku: 'X-1', name: 'Novo', cost_cents: 123456, item_type: 'goods', unit: 'UN', is_active: true }));
  });

  it('blocks save on a bad fiscal field and jumps to the Fiscal tab with the message', async () => {
    const user = userEvent.setup();
    const api = mount();
    await user.type(screen.getByLabelText(/SKU/), 'x-1');
    await user.type(screen.getByLabelText(/Nome/), 'Novo');
    await user.click(screen.getByRole('tab', { name: /Fiscal/ }));
    await user.type(screen.getByLabelText('GTIN / EAN'), '7891000100104');
    await user.click(screen.getByRole('tab', { name: /Geral/ }));
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    expect(await screen.findByText(/GTIN\/EAN inválido/)).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Fiscal/ })).toHaveAttribute('aria-selected', 'true');
    expect(api.post).not.toHaveBeenCalled();
  });

  it('maps a server 422 (details.field) onto its field', async () => {
    const user = userEvent.setup();
    const api = mount();
    api.post.mockRejectedValue(new ApiError(409, 'x', { error: { code: 'sku_duplicado', message: 'Já existe um item com este SKU.', details: { field: 'sku' } } }));
    await user.type(screen.getByLabelText(/SKU/), 'x-1');
    await user.type(screen.getByLabelText(/Nome/), 'Novo');
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    expect(await screen.findByText('Já existe um item com este SKU.')).toBeInTheDocument();
  });

  it('shows a non-field server error in the form banner', async () => {
    const user = userEvent.setup();
    const api = mount();
    api.post.mockRejectedValue(new ApiError(500, 'Servidor indisponível'));
    await user.type(screen.getByLabelText(/SKU/), 'x-1');
    await user.type(screen.getByLabelText(/Nome/), 'Novo');
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    expect(await screen.findByText(/Servidor indisponível/)).toBeInTheDocument();
  });

  it('offers no stock fields (inventory owns stock)', () => {
    mount();
    expect(screen.queryByLabelText(/estoque/i)).toBeNull();
    expect(screen.getByText('Novo item')).toBeInTheDocument();
  });
});

describe('ItemEditor — edit', () => {
  it('shows a skeleton, then loads the item into the fields (fiscal tab included)', async () => {
    const user = userEvent.setup();
    mount({ itemId: 'i1' });
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    expect(await screen.findByDisplayValue('PAR-1')).toBeInTheDocument();
    expect(screen.getByDisplayValue('1,50')).toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: /Fiscal/ }));
    expect(screen.getByDisplayValue('73181500')).toBeInTheDocument();
    expect(screen.getByLabelText('Origem da mercadoria')).toHaveValue('1');
  });

  it('patches the item by id', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    const api = mount({ itemId: 'i1', onSaved });
    api.patch.mockResolvedValue({ data: item() });
    const name = await screen.findByDisplayValue('Parafuso');
    await user.clear(name);
    await user.type(name, 'Parafuso M8');
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(api.patch).toHaveBeenCalledWith('/api/items/i1', expect.objectContaining({ name: 'Parafuso M8', ncm: '73181500', origem: 1 }));
  });

  it('shows a retryable error / not-found instead of a blank form', async () => {
    const api = makeApi();
    api.get.mockRejectedValue(new ApiError(500, 'boom'));
    const hooks = createItemsHooks(api);
    const Wrapper = wrapperFor();
    render(<Wrapper><ItemEditor hooks={hooks} itemId="i1" /></Wrapper>);
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
  });
});
