import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PartiesTable } from './PartiesTable';
import { createPartiesHooks } from './hooks';
import { ApiError } from '../api';
import { makeApi, page, party, wrapperFor } from './testUtils';

afterEach(cleanup);

function mount(api = makeApi(), props: Partial<React.ComponentProps<typeof PartiesTable>> = {}) {
  const hooks = createPartiesHooks(api);
  const Wrapper = wrapperFor();
  render(<Wrapper><PartiesTable hooks={hooks} {...props} /></Wrapper>);
  return api;
}

describe('PartiesTable', () => {
  it('shows a skeleton on the first load, then the rows with role chips and the server-masked doc', async () => {
    let resolve!: (v: unknown) => void;
    const api = makeApi();
    api.get.mockImplementation(() => new Promise((r) => (resolve = r)));
    mount(api);
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    expect(screen.queryByText('Nenhum cadastro ainda.')).not.toBeInTheDocument(); // no lying empty state while loading

    await act(async () => resolve(page([
      party({ doc: '***.982.247-**', roles: ['customer', 'supplier'], trade_name: 'Aninha' }),
      party({ id: 'p2', kind: 'PJ', legal_name: 'Beta Ltda', doc: '11222333000181', roles: [], is_active: false, email: null, phones: [] }),
    ])));
    expect(await screen.findByText('Ana Souza')).toBeInTheDocument();
    expect(screen.getByText('Aninha')).toBeInTheDocument();
    expect(screen.getByText('***.982.247-**')).toBeInTheDocument();
    expect(screen.getByText('11.222.333/0001-81')).toBeInTheDocument();
    const row = screen.getByText('Ana Souza').closest('tr')!;
    expect(within(row).getByText('Cliente')).toBeInTheDocument();
    expect(within(row).getByText('Fornecedor')).toBeInTheDocument();
    expect(screen.getByText('Sem papel')).toBeInTheDocument();
    expect(screen.getByText('Arquivado')).toBeInTheDocument();
    expect(screen.queryByTestId('list-loading')).not.toBeInTheDocument();
  });

  it('empty list: the plain empty state, and a different one when a filter is active', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    api.get.mockResolvedValue(page([]));
    mount(api);
    expect(await screen.findByText('Nenhum cadastro ainda.')).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Papel'), 'carrier');
    expect(await screen.findByText('Nenhum cadastro encontrado para esse filtro.')).toBeInTheDocument();
  });

  it('error with no data: message + retry that recovers', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    api.get.mockRejectedValueOnce(new ApiError(500, 'indisponível'));
    mount(api);
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
    api.get.mockResolvedValueOnce(page([party()]));
    await user.click(screen.getByRole('button', { name: 'Tentar novamente' }));
    expect(await screen.findByText('Ana Souza')).toBeInTheDocument();
  });

  it('a failed filter change shows the error with retry — never an empty-list claim', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    api.get.mockResolvedValueOnce(page([party()]));
    mount(api);
    await screen.findByText('Ana Souza');
    api.get.mockRejectedValueOnce(new ApiError(500, 'x'));
    await user.selectOptions(screen.getByLabelText('Situação'), 'all');
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
    expect(screen.queryByText('Nenhum cadastro encontrado para esse filtro.')).not.toBeInTheDocument();
    api.get.mockResolvedValueOnce(page([party({ id: 'p3', legal_name: 'Voltou' })]));
    await user.click(screen.getByRole('button', { name: 'Tentar novamente' }));
    expect(await screen.findByText('Voltou')).toBeInTheDocument();
  });

  it('refreshing over data shows the indicator and never unmounts the rows', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    api.get.mockResolvedValueOnce(page([party()]));
    mount(api);
    await screen.findByText('Ana Souza');
    let resolve!: (v: unknown) => void;
    api.get.mockImplementationOnce(() => new Promise((r) => (resolve = r)));
    await user.selectOptions(screen.getByLabelText('Tipo'), 'PF');
    expect(await screen.findByText('Atualizando…')).toBeInTheDocument();
    expect(screen.getByText('Ana Souza')).toBeInTheDocument();
    expect(screen.queryByTestId('list-loading')).not.toBeInTheDocument();
    await act(async () => resolve(page([party({ id: 'p9', legal_name: 'Zeca' })])));
    expect(await screen.findByText('Zeca')).toBeInTheDocument();
  });

  it('search is debounced into a single request and resets to page 1; filters go on the wire', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    api.get.mockResolvedValue(page([party()]));
    mount(api);
    await screen.findByText('Ana Souza');
    await user.type(screen.getByLabelText('Buscar por nome, CPF/CNPJ ou e-mail'), 'beta');
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/api/parties', expect.objectContaining({ q: 'beta', active: true, page: 1 })));
    const searched = api.get.mock.calls.filter(([, p]) => p.q === 'beta');
    expect(searched).toHaveLength(1); // 4 keystrokes, one request
    await user.selectOptions(screen.getByLabelText('Papel'), 'supplier');
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/api/parties', expect.objectContaining({ role: 'supplier', q: 'beta' })));
    await user.selectOptions(screen.getByLabelText('Situação'), 'archived');
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/api/parties', expect.objectContaining({ active: false })));
  });

  it('paginates', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    api.get.mockResolvedValue(page([party()], { total: 45, page_size: 20 }));
    mount(api);
    await screen.findByText('Ana Souza');
    expect(screen.getByText('1 / 3')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Anterior' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Próxima' }));
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/api/parties', expect.objectContaining({ page: 2 })));
  });

  it('read-only by default: no "Novo cadastro", no import; export is always there', async () => {
    const api = makeApi();
    api.get.mockResolvedValue(page([party()]));
    mount(api);
    await screen.findByText('Ana Souza');
    expect(screen.queryByRole('button', { name: 'Novo cadastro' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Importar CSV' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Exportar CSV' })).toBeInTheDocument();
  });

  it('canWrite: "Novo cadastro" opens the editor pre-selecting the filtered role; a row click opens the party', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    api.get.mockImplementation((path: string) =>
      path === '/api/parties' ? Promise.resolve(page([party()])) : Promise.resolve({ data: party() }));
    mount(api, { canWrite: true, initialRole: 'supplier' });
    await screen.findByText('Ana Souza');
    await user.click(screen.getByRole('button', { name: 'Novo cadastro' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('checkbox', { name: 'Fornecedor' })).toHaveAttribute('aria-checked', 'true');
    await user.click(within(dialog).getByRole('button', { name: 'Cancelar' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    await user.click(screen.getByText('Ana Souza'));
    const edit = await screen.findByRole('dialog');
    expect(await within(edit).findByDisplayValue('Ana Souza')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/api/parties/p1');
  });

  it('onSelect replaces the built-in editor', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    api.get.mockResolvedValue(page([party()]));
    const picked: string[] = [];
    mount(api, { onSelect: (id) => picked.push(id) });
    await user.click(await screen.findByText('Ana Souza'));
    expect(picked).toEqual(['p1']);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
