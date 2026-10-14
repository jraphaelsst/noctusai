import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ItemsImport } from './ItemsImport';
import { createItemsHooks } from './hooks';
import { ApiError } from '../api';
import { makeApi, wrapperFor } from './testUtils';

afterEach(cleanup);

function mount() {
  const api = makeApi();
  const hooks = createItemsHooks(api);
  const Wrapper = wrapperFor();
  render(<Wrapper><ItemsImport hooks={hooks} /></Wrapper>);
  return api;
}
const file = () => new File(['sku,name\nA,a\n'], 'itens.csv', { type: 'text/csv' });

describe('ItemsImport', () => {
  it('needs a file; validates first (dry run default) and says nothing was written', async () => {
    const user = userEvent.setup();
    const api = mount();
    api.upload.mockResolvedValue({ data: { created: 2, updated: 1, dry_run: true } });
    expect(screen.getByRole('button', { name: 'Importar' })).toBeDisabled();
    await user.upload(screen.getByLabelText(/Arquivo CSV/), file());
    await user.click(screen.getByRole('button', { name: 'Importar' }));
    expect(await screen.findByText(/Validação ok: 2 a criar, 1 a atualizar. Nada foi gravado./)).toBeInTheDocument();
    expect((api.upload.mock.calls[0][1] as FormData).get('dry_run')).toBe('true');
  });

  it('a real import reports the counts', async () => {
    const user = userEvent.setup();
    const api = mount();
    api.upload.mockResolvedValue({ data: { created: 3, updated: 0, dry_run: false } });
    await user.upload(screen.getByLabelText(/Arquivo CSV/), file());
    await user.click(screen.getByLabelText('Apenas validar (não grava)'));
    await user.click(screen.getByLabelText('Atualizar itens com SKU existente'));
    await user.click(screen.getByRole('button', { name: 'Importar' }));
    expect(await screen.findByText('3 criado(s), 0 atualizado(s).')).toBeInTheDocument();
    const form = api.upload.mock.calls[0][1] as FormData;
    expect([form.get('dry_run'), form.get('update_existing')]).toEqual(['false', 'true']);
  });

  it('lists every row problem of a 422 importacao_invalida', async () => {
    const user = userEvent.setup();
    const api = mount();
    api.upload.mockRejectedValue(new ApiError(422, 'x', {
      error: { code: 'importacao_invalida', message: 'x', details: { error_count: 2, errors: [
        { line: 3, field: 'ncm', code: 'ncm_invalido', message: 'NCM inválido: 8 dígitos.' },
        { line: 5, field: 'sku', code: 'sku_duplicado', message: 'SKU repetido no arquivo (linha 2).' },
      ] } },
    }));
    await user.upload(screen.getByLabelText(/Arquivo CSV/), file());
    await user.click(screen.getByRole('button', { name: 'Importar' }));
    expect(await screen.findByText(/Linha 3 · ncm: NCM inválido/)).toBeInTheDocument();
    expect(screen.getByText(/Linha 5 · sku: SKU repetido/)).toBeInTheDocument();
  });

  it('shows other failures as a plain error', async () => {
    const user = userEvent.setup();
    const api = mount();
    api.upload.mockRejectedValue(new ApiError(413, 'O arquivo é grande demais.'));
    await user.upload(screen.getByLabelText(/Arquivo CSV/), file());
    await user.click(screen.getByRole('button', { name: 'Importar' }));
    await waitFor(() => expect(screen.getByText(/grande demais/)).toBeInTheDocument());
  });
});
