import { describe, it, expect, afterEach, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PartiesCsvActions } from './PartiesCsvActions';
import { createPartiesHooks } from './hooks';
import { ApiError } from '../api';
import { makeApi, wrapperFor } from './testUtils';

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => 'blob:x');
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {}); // jsdom cannot navigate to a blob: URL
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function mount(api = makeApi(), props: Partial<React.ComponentProps<typeof PartiesCsvActions>> = {}) {
  const hooks = createPartiesHooks(api);
  const Wrapper = wrapperFor();
  render(<Wrapper><PartiesCsvActions hooks={hooks} {...props} /></Wrapper>);
  return api;
}

const csv = () => new File(['kind,legal_name\nPF,Ana\n'], 'p.csv', { type: 'text/csv' });

describe('PartiesCsvActions', () => {
  it('exports with the current filters and triggers a browser download', async () => {
    const api = makeApi();
    api.download.mockResolvedValue(new Blob(['x']));
    mount(api, { filters: { role: 'supplier', active: 'active' } });
    await userEvent.setup().click(screen.getByRole('button', { name: 'Exportar CSV' }));
    await waitFor(() => expect(api.download).toHaveBeenCalledWith('/api/parties/export.csv?role=supplier&active=true'));
    expect(URL.createObjectURL).toHaveBeenCalled();
  });

  it('an export failure is shown, not swallowed', async () => {
    const api = makeApi();
    api.download.mockRejectedValue(new ApiError(422, 'A exportação tem 30000 linhas'));
    mount(api);
    await userEvent.setup().click(screen.getByRole('button', { name: 'Exportar CSV' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('30000 linhas');
  });

  it('import is hidden without write access', () => {
    mount();
    expect(screen.queryByRole('button', { name: 'Importar CSV' })).not.toBeInTheDocument();
  });

  it('import reports created / skipped / per-line errors', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    api.upload.mockResolvedValue({
      data: {
        dry_run: false, created: 3, skipped: [{ line: 5, reason: 'documento_duplicado' }],
        errors: [{ line: 4, field: 'doc', code: 'documento_invalido', message: 'CPF inválido para uma pessoa física.' }],
      },
    });
    mount(api, { canWrite: true });
    await user.upload(screen.getByLabelText('Importar CSV', { selector: 'input' }), csv());
    expect(await screen.findByText('3 cadastros criados')).toBeInTheDocument();
    expect(screen.getByText('1 ignorados (CPF/CNPJ já cadastrado)')).toBeInTheDocument();
    expect(screen.getByText('1 linhas com erro')).toBeInTheDocument();
    expect(screen.getByText(/Linha 4: CPF inválido/)).toBeInTheDocument();
    expect((api.upload.mock.calls[0][1] as FormData).get('dry_run')).toBe('false');
  });

  it('"só validar" sends dry_run and words the result as a preview', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    api.upload.mockResolvedValue({ data: { dry_run: true, created: 2, skipped: [], errors: [] } });
    mount(api, { canWrite: true });
    await user.click(screen.getByLabelText('Só validar (não grava)'));
    await user.upload(screen.getByLabelText('Importar CSV', { selector: 'input' }), csv());
    expect(await screen.findByText('2 cadastros seriam criados')).toBeInTheDocument();
    expect((api.upload.mock.calls[0][1] as FormData).get('dry_run')).toBe('true');
  });

  it('an import failure (413 / 422) is shown', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    api.upload.mockRejectedValue(new ApiError(422, 'O cabeçalho precisa das colunas kind'));
    mount(api, { canWrite: true });
    await user.upload(screen.getByLabelText('Importar CSV', { selector: 'input' }), csv());
    expect(await screen.findByRole('alert')).toHaveTextContent('O cabeçalho precisa');
  });
});
