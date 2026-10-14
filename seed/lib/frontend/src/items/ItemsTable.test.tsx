import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ItemsTable } from './ItemsTable';
import { createItemsHooks } from './hooks';
import { ApiError } from '../api';
import { category, item, makeApi, page, routeGet, wrapperFor } from './testUtils';

afterEach(cleanup);

function mount(rows = [item(), item({ id: 'i2', sku: 'SRV-1', name: 'Instalação', item_type: 'service', unit: 'H', is_active: false, price_cents: null })], props: Record<string, unknown> = {}) {
  const api = makeApi();
  routeGet(api, { '/api/items/categories': { data: [category()] }, '/api/items': page(rows) });
  const hooks = createItemsHooks(api);
  const Wrapper = wrapperFor();
  render(<Wrapper><ItemsTable hooks={hooks} {...props} /></Wrapper>);
  return api;
}

describe('ItemsTable', () => {
  it('shows a skeleton first, then the rows with formatted money and status', async () => {
    mount();
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    expect(await screen.findByText('PAR-1')).toBeInTheDocument();
    const table = within(screen.getByRole('table'));
    expect(table.getByText('Mercadoria')).toBeInTheDocument();
    expect(table.getByText('Serviço')).toBeInTheDocument();
    expect(table.getAllByText(/R\$\s?1,50/)).toHaveLength(2); // cost, both rows
    expect(table.getByText(/R\$\s?3,00/)).toBeInTheDocument();
    expect(table.getByText('Arquivado')).toBeInTheDocument();
    expect(table.getByText('—')).toBeInTheDocument(); // no reference price
  });

  it('shows the empty state, and a different one when a filter is active', async () => {
    const user = userEvent.setup();
    mount([]);
    expect(await screen.findByText('Nenhum item cadastrado.')).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Situação'), '');
    expect(await screen.findByText('Nenhum item encontrado para esta busca.')).toBeInTheDocument();
  });

  it('shows a retryable error when the first load fails', async () => {
    const api = makeApi();
    api.get.mockRejectedValue(new ApiError(500, 'boom'));
    const hooks = createItemsHooks(api);
    const Wrapper = wrapperFor();
    render(<Wrapper><ItemsTable hooks={hooks} /></Wrapper>);
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument();
  });

  it('debounces the search and sends it to the API', async () => {
    const user = userEvent.setup();
    const api = mount();
    await screen.findByText('PAR-1');
    await user.type(screen.getByLabelText('Buscar por SKU, nome ou GTIN'), 'par');
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/items', expect.objectContaining({ q: 'par' })));
  });

  it('filters by type and status through the query', async () => {
    const user = userEvent.setup();
    const api = mount();
    await screen.findByText('PAR-1');
    await user.selectOptions(screen.getByLabelText('Tipo'), 'service');
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/items', expect.objectContaining({ item_type: 'service' })));
    await user.selectOptions(screen.getByLabelText('Situação'), 'false');
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/items', expect.objectContaining({ active: 'false' })));
  });

  it('archives an active row and restores an archived one', async () => {
    const user = userEvent.setup();
    const api = mount();
    api.post.mockResolvedValue({ data: item() });
    await screen.findByText('PAR-1');
    const rows = screen.getAllByRole('row');
    await user.click(within(rows[1]).getByRole('button', { name: 'Arquivar' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/items/i1/archive'));
    await user.click(within(rows[2]).getByRole('button', { name: 'Reativar' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/items/i2/unarchive'));
  });

  it('surfaces an archive failure instead of swallowing it', async () => {
    const user = userEvent.setup();
    const api = mount();
    api.post.mockRejectedValue(new ApiError(403, 'Admin only'));
    await screen.findByText('PAR-1');
    await user.click(within(screen.getAllByRole('row')[1]).getByRole('button', { name: 'Arquivar' }));
    expect(await screen.findByText(/Admin only/)).toBeInTheDocument();
  });

  it('row click selects; the create button calls onCreate; canWrite=false hides write controls', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const onCreate = vi.fn();
    mount(undefined, { onSelect, onCreate });
    await user.click(await screen.findByText('Parafuso'));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 'i1' }));
    await user.click(screen.getByRole('button', { name: 'Novo item' }));
    expect(onCreate).toHaveBeenCalled();
    cleanup();
    mount(undefined, { onSelect, onCreate, canWrite: false });
    await screen.findByText('PAR-1');
    expect(screen.queryByRole('button', { name: 'Arquivar' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Novo item' })).toBeNull();
  });

  it('paginates', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    routeGet(api, { '/api/items/categories': { data: [] }, '/api/items': page([item()], 45) });
    const hooks = createItemsHooks(api);
    const Wrapper = wrapperFor();
    render(<Wrapper><ItemsTable hooks={hooks} /></Wrapper>);
    expect(await screen.findByText('Página 1 de 3')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Próxima' }));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/items', expect.objectContaining({ page: 2 })));
  });

  it('exports the CSV through the injected saver', async () => {
    const user = userEvent.setup();
    const saveBlob = vi.fn();
    const api = mount(undefined, { saveBlob });
    const blob = new Blob(['sku\n']);
    api.download.mockResolvedValue(blob);
    await screen.findByText('PAR-1');
    await user.click(screen.getByRole('button', { name: 'Exportar CSV' }));
    await waitFor(() => expect(saveBlob).toHaveBeenCalledWith(blob, 'itens.csv'));
    expect(api.download).toHaveBeenCalledWith('/api/items/export.csv?active=true');
  });

  it('shows an export failure', async () => {
    const user = userEvent.setup();
    const api = mount();
    api.download.mockRejectedValue(new ApiError(422, 'Filtre antes'));
    await screen.findByText('PAR-1');
    await user.click(screen.getByRole('button', { name: 'Exportar CSV' }));
    expect(await screen.findByText(/Não foi possível exportar.*Filtre antes/)).toBeInTheDocument();
  });
});
