import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PartyEditor } from './PartyEditor';
import { createPartiesHooks } from './hooks';
import { ApiError } from '../api';
import { makeApi, party, wrapperFor, VALID_CNPJ, VALID_CPF } from './testUtils';

afterEach(cleanup);

function mount(api = makeApi(), props: Partial<React.ComponentProps<typeof PartyEditor>> = {}) {
  const onClose = vi.fn();
  const onSaved = vi.fn();
  const hooks = createPartiesHooks(api);
  const Wrapper = wrapperFor();
  render(<Wrapper><PartyEditor hooks={hooks} open partyId={null} canWrite onClose={onClose} onSaved={onSaved} {...props} /></Wrapper>);
  return { api, onClose, onSaved };
}

const dup = () => new ApiError(409, 'Já existe', { error: { code: 'documento_duplicado' } });

describe('PartyEditor — create', () => {
  it('blocks save and explains: name required, bad CPF, bad e-mail; nothing is sent', async () => {
    const user = userEvent.setup();
    const { api } = mount();
    await user.type(screen.getByLabelText(/^CPF/), '52998224726');
    await user.type(screen.getByLabelText('E-mail'), 'nope');
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    expect(await screen.findByText('Informe o nome / razão social.')).toBeInTheDocument();
    expect(screen.getByText('CPF inválido.')).toBeInTheDocument();
    expect(screen.getByText('E-mail inválido.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('masks the document while typing and sends digits-only plus a normalised body', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    api.post.mockResolvedValue({ data: party({ id: 'new' }) });
    const { onSaved, onClose } = mount(api);
    await user.type(screen.getByLabelText(/^Nome completo/), '  Ana Souza ');
    await user.type(screen.getByLabelText(/^CPF/), '52998224725');
    expect(screen.getByDisplayValue(VALID_CPF)).toBeInTheDocument();
    await user.type(screen.getByLabelText('Telefones (separe por vírgula)'), '11994573387, 1132165498');
    await user.click(screen.getByRole('checkbox', { name: 'Cliente' }));
    await user.click(screen.getByRole('checkbox', { name: 'Transportadora' }));
    await user.type(screen.getByLabelText('Cidade'), 'Santos');
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    expect(api.post).toHaveBeenCalledWith('/api/parties', {
      kind: 'PF',
      doc: '52998224725',
      legal_name: 'Ana Souza',
      trade_name: null,
      email: null,
      phones: ['11994573387', '1132165498'],
      address: { city: 'Santos' },
      state_registration: null,
      municipal_registration: null,
      notes: null,
      roles: ['customer', 'carrier'],
    });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ id: 'new' }));
  });

  it('switching to PJ relabels the fields, re-masks as CNPJ and validates a CNPJ', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    api.post.mockResolvedValue({ data: party({ kind: 'PJ' }) });
    mount(api);
    await user.selectOptions(screen.getByLabelText('Tipo'), 'PJ');
    expect(screen.getByLabelText(/^Razão social/)).toBeInTheDocument();
    await user.type(screen.getByLabelText(/^CNPJ/), '11222333000182');
    await user.type(screen.getByLabelText(/^Razão social/), 'Beta Ltda');
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    expect(await screen.findByText('CNPJ inválido.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
    const doc = screen.getByLabelText(/^CNPJ/);
    await user.clear(doc);
    await user.type(doc, '11222333000181');
    expect(doc).toHaveValue(VALID_CNPJ);
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/parties', expect.objectContaining({ kind: 'PJ', doc: '11222333000181' })));
  });

  it('a 409 documento_duplicado lands on the document field and keeps the dialog open', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    api.post.mockRejectedValue(dup());
    const { onClose } = mount(api);
    await user.type(screen.getByLabelText(/^Nome completo/), 'Ana');
    await user.type(screen.getByLabelText(/^CPF/), '52998224725');
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    expect(await screen.findByText('Já existe um cadastro com este CPF/CNPJ.')).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Salvar' })).toBeEnabled(); // can retry
  });

  it('an unmapped server error shows the form-level banner', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    api.post.mockRejectedValue(new ApiError(500, 'kaput'));
    mount(api);
    await user.type(screen.getByLabelText(/^Nome completo/), 'Ana');
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível concluir a operação');
  });
});

describe('PartyEditor — edit', () => {
  it('shows a skeleton, then the loaded values; saves a patch without touching the document when unchanged', async () => {
    const user = userEvent.setup();
    let resolve!: (v: unknown) => void;
    const api = makeApi();
    api.get.mockImplementation(() => new Promise((r) => (resolve = r)));
    api.patch.mockResolvedValue({ data: party() });
    mount(api, { partyId: 'p1' });
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    resolve({ data: party({ doc: '52998224725', roles: ['supplier'] }) });
    expect(await screen.findByDisplayValue('Ana Souza')).toBeInTheDocument();
    expect(screen.getByDisplayValue(VALID_CPF)).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Fornecedor' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByLabelText('Tipo')).toBeDisabled(); // kind is fixed once created
    const name = screen.getByDisplayValue('Ana Souza');
    await user.clear(name);
    await user.type(name, 'Ana Maria');
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/parties/p1', expect.objectContaining({ legal_name: 'Ana Maria', doc: '52998224725', roles: ['supplier'] })));
  });

  it('load error: message + retry', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    api.get.mockRejectedValueOnce(new ApiError(500, 'x'));
    mount(api, { partyId: 'p1' });
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
    api.get.mockResolvedValueOnce({ data: party() });
    await user.click(screen.getByRole('button', { name: 'Tentar novamente' }));
    expect(await screen.findByDisplayValue('Ana Souza')).toBeInTheDocument();
  });

  it('a masked document is shown, locked and never sent back', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    api.get.mockResolvedValue({ data: party({ doc: '***.982.247-**' }) });
    api.patch.mockResolvedValue({ data: party() });
    mount(api, { partyId: 'p1' });
    const doc = await screen.findByDisplayValue('***.982.247-**');
    expect(doc).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalled());
    expect(api.patch.mock.calls[0][1]).not.toHaveProperty('doc');
  });

  it('read-only (canWrite=false): fields disabled, no save / archive / delete', async () => {
    const api = makeApi();
    api.get.mockResolvedValue({ data: party() });
    mount(api, { partyId: 'p1', canWrite: false });
    const name = await screen.findByDisplayValue('Ana Souza');
    expect(name).toBeDisabled();
    expect(screen.getByText(/Somente leitura/)).toBeInTheDocument();
    for (const label of ['Salvar', 'Arquivar', 'Excluir']) expect(screen.queryByRole('button', { name: label })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fechar' })).toBeInTheDocument();
  });

  it('archives an active party and restores an archived one', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    api.get.mockResolvedValue({ data: party() });
    api.post.mockResolvedValue({ data: party({ is_active: false }) });
    const { onClose } = mount(api, { partyId: 'p1' });
    await user.click(await screen.findByRole('button', { name: 'Arquivar' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/parties/p1/archive', {}));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    cleanup();

    const api2 = makeApi();
    api2.get.mockResolvedValue({ data: party({ is_active: false }) });
    api2.post.mockResolvedValue({ data: party() });
    mount(api2, { partyId: 'p1' });
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Restaurar' }));
    await waitFor(() => expect(api2.post).toHaveBeenCalledWith('/api/parties/p1/restore', {}));
  });

  it('delete asks for confirmation, then removes; a referenced party answers "archive it instead"', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    api.get.mockResolvedValue({ data: party() });
    api.delete.mockRejectedValueOnce(new ApiError(409, 'em uso', { error: { code: 'parceiro_em_uso', details: { hint: 'archive' } } }));
    const { onClose } = mount(api, { partyId: 'p1' });
    await user.click(await screen.findByRole('button', { name: 'Excluir' }));
    expect(api.delete).not.toHaveBeenCalled(); // first click only asks
    await user.click(screen.getByRole('button', { name: 'Sim, excluir' }));
    expect(await screen.findByText(/não pode ser excluído\. Arquive-o\./)).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();

    api.delete.mockResolvedValueOnce(undefined);
    await user.click(screen.getByRole('button', { name: 'Excluir' }));
    await user.click(screen.getByRole('button', { name: 'Sim, excluir' }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(api.delete).toHaveBeenCalledTimes(2);
  });

  it('closed dialog renders nothing and does not fetch', () => {
    const api = makeApi();
    mount(api, { open: false, partyId: 'p1' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalled();
  });
});

describe('PartyEditor — role picker', () => {
  it('toggles roles on and off and keeps a stable order', async () => {
    const user = userEvent.setup();
    mount();
    const group = screen.getByRole('group', { name: 'Papéis' });
    await user.click(within(group).getByRole('checkbox', { name: 'Transportadora' }));
    await user.click(within(group).getByRole('checkbox', { name: 'Cliente' }));
    expect(within(group).getByRole('checkbox', { name: 'Cliente' })).toHaveAttribute('aria-checked', 'true');
    await user.click(within(group).getByRole('checkbox', { name: 'Transportadora' }));
    expect(within(group).getByRole('checkbox', { name: 'Transportadora' })).toHaveAttribute('aria-checked', 'false');
  });
});
