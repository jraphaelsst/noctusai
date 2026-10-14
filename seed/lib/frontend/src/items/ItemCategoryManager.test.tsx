import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ItemCategoryManager, flattenCategories } from './ItemCategoryManager';
import { createItemsHooks } from './hooks';
import { ApiError } from '../api';
import { category, makeApi, wrapperFor } from './testUtils';

afterEach(cleanup);

const root = category({ id: 'r', name: 'Ferragens' });
const kid = category({ id: 'k', name: 'Parafusos', parent_id: 'r' });

function mount(rows = [kid, root], props: Record<string, unknown> = {}) {
  const api = makeApi();
  api.get.mockResolvedValue({ data: rows });
  const hooks = createItemsHooks(api);
  const Wrapper = wrapperFor();
  render(<Wrapper><ItemCategoryManager hooks={hooks} {...props} /></Wrapper>);
  return api;
}

describe('flattenCategories', () => {
  it('orders depth-first by name and treats orphans as roots', () => {
    const orphan = category({ id: 'o', name: 'Ótica', parent_id: 'missing' });
    expect(flattenCategories([kid, orphan, root]).map(([c, d]) => [c.name, d])).toEqual([['Ferragens', 0], ['Parafusos', 1], ['Ótica', 0]]);
  });
  it('does not loop on a corrupt cycle', () => {
    const a = category({ id: 'a', name: 'A', parent_id: 'b' });
    const b = category({ id: 'b', name: 'B', parent_id: 'a' });
    expect(flattenCategories([a, b])).toEqual([]);
  });
});

describe('ItemCategoryManager', () => {
  it('skeleton, then the tree', async () => {
    mount();
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    expect(await screen.findByText('Ferragens')).toBeInTheDocument();
    expect(screen.getByText('Parafusos')).toBeInTheDocument();
  });

  it('empty state and error state', async () => {
    mount([]);
    expect(await screen.findByText('Nenhuma categoria cadastrada.')).toBeInTheDocument();
    cleanup();
    const api = makeApi();
    api.get.mockRejectedValue(new ApiError(500, 'boom'));
    const hooks = createItemsHooks(api);
    const Wrapper = wrapperFor();
    render(<Wrapper><ItemCategoryManager hooks={hooks} /></Wrapper>);
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
  });

  it('creates a category under a parent', async () => {
    const user = userEvent.setup();
    const api = mount();
    api.post.mockResolvedValue({ data: category({ id: 'n' }) });
    await screen.findByText('Ferragens');
    await user.click(screen.getByRole('button', { name: 'Nova categoria' }));
    await user.type(screen.getByLabelText(/Nome/), ' Porcas ');
    await user.selectOptions(screen.getByLabelText('Categoria pai'), 'r');
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/items/categories', { name: 'Porcas', parent_id: 'r' }));
  });

  it('cannot pick itself or a descendant as parent when editing', async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByText('Ferragens');
    const li = screen.getByText('Ferragens').closest('li') as HTMLElement;
    await user.click(within(li).getByRole('button', { name: 'Editar' }));
    const options = within(screen.getByLabelText('Categoria pai')).getAllByRole('option').map((o) => o.textContent);
    expect(options).toEqual(['Nenhuma (raiz)']);
  });

  it('delete needs a confirm and surfaces a 409 categoria_em_uso', async () => {
    const user = userEvent.setup();
    const api = mount();
    api.delete.mockRejectedValue(new ApiError(409, 'A categoria tem subcategorias ou itens e não pode ser excluída.'));
    await screen.findByText('Ferragens');
    const li = screen.getByText('Ferragens').closest('li') as HTMLElement;
    await user.click(within(li).getByRole('button', { name: 'Remover' }));
    expect(api.delete).not.toHaveBeenCalled();
    await user.click(within(li).getByRole('button', { name: 'Confirmar' }));
    expect(await screen.findByText(/não pode ser excluída/)).toBeInTheDocument();
    expect(api.delete).toHaveBeenCalledWith('/api/items/categories/r');
  });

  it('canWrite=false is read-only', async () => {
    mount(undefined, { canWrite: false });
    await screen.findByText('Ferragens');
    expect(screen.queryByRole('button')).toBeNull();
  });
});
