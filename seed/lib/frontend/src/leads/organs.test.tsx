import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api';
import { createLeadsHooks } from './hooks';
import { LeadCard } from './LeadCard';
import { LeadDetailModal } from './LeadDetailModal';
import { LeadFormDialog } from './LeadFormDialog';
import { LeadsBoard } from './LeadsBoard';
import { LeadsList } from './LeadsList';
import { board, CONFIG, env, lead, makeApi, wrapperFor } from './testUtils';

const ana = lead({ id: 'a', name: 'Ana Souza', stage: 'lead', first_contact_at: new Date(Date.now() - 5 * 86_400_000).toISOString() });
const bia = lead({ id: 'b', name: 'Bia', stage: 'atendimento', origin: 'instagram', whatsapp_chat_id: null, last_message_preview: null, phone: null });

const lastButton = (name: string) => {
  const all = screen.getAllByRole('button', { name });
  return all[all.length - 1];
};

describe('LeadCard', () => {
  it('shows name, phone, origin, days since first contact and the last-message preview', () => {
    render(<LeadCard lead={ana} originLabel="WhatsApp" />);
    expect(screen.getByText('Ana Souza')).toBeInTheDocument();
    expect(screen.getByText('+5511994573387')).toBeInTheDocument();
    expect(screen.getByText('WhatsApp')).toBeInTheDocument();
    expect(screen.getByText('há 5 dias')).toBeInTheDocument();
    expect(screen.getByText('Oi, queria marcar uma conversa')).toBeInTheDocument();
  });

  it('says so when there is no phone and omits an empty preview', () => {
    render(<LeadCard lead={bia} originLabel="Instagram" />);
    expect(screen.getByText('Sem telefone')).toBeInTheDocument();
    expect(screen.queryByText(/Oi, queria/)).not.toBeInTheDocument();
  });
});

describe('LeadsBoard', () => {
  const routes = () => ({ 'GET /api/leads/board': env(board([ana], [bia], [])) });

  it('renders one column per stage with totals and the cards', async () => {
    render(<LeadsBoard hooks={createLeadsHooks(makeApi(routes()))} />, { wrapper: wrapperFor() });
    expect(await screen.findByText('Ana Souza')).toBeInTheDocument();
    for (const label of ['Lead', 'Atendimento', 'Fechado']) expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.getByText('Bia')).toBeInTheDocument();
    expect(screen.getAllByText('Nenhum lead nesta etapa.')).toHaveLength(1);
  });

  it('does not claim "loading" once data is on screen while the board refetches', async () => {
    render(<LeadsBoard hooks={createLeadsHooks(makeApi(routes()))} />, { wrapper: wrapperFor() });
    await screen.findByText('Ana Souza');
    expect(screen.queryByRole('status', { name: /carregando/i })).not.toBeInTheDocument();
  });

  it('a card click opens the detail modal with the lead', async () => {
    render(<LeadsBoard hooks={createLeadsHooks(makeApi({ ...routes(), 'GET /api/leads/a': env(ana) }))} />, { wrapper: wrapperFor() });
    await userEvent.click(await screen.findByText('Ana Souza'));
    const modal = await screen.findByTestId('lead-detail-modal');
    expect(within(modal).getByText('Ana Souza')).toBeInTheDocument();
    expect(within(modal).getByText('+5511994573387')).toBeInTheDocument();
  });

  it('sends the typed search to the board (raw: the server matches phones by digits)', async () => {
    const api = makeApi(routes());
    render(<LeadsBoard hooks={createLeadsHooks(api)} />, { wrapper: wrapperFor() });
    await screen.findByText('Ana Souza');
    fireEvent.change(screen.getByLabelText('Buscar por nome, telefone ou e-mail'), { target: { value: '(11) 99457-3387' } });
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/leads/board', { q: '(11) 99457-3387' }));
  });

  it('shows the error with a message (not an empty board) when the first load fails', async () => {
    const api = makeApi({ 'GET /api/leads/board': () => Promise.reject(new ApiError(500, 'banco fora')) });
    render(<LeadsBoard hooks={createLeadsHooks(api)} />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Não foi possível carregar o funil/)).toBeInTheDocument();
  });

  it('"Novo lead" opens the form and creating one posts it', async () => {
    const api = makeApi({ ...routes(), 'POST /api/leads': env(lead({ id: 'n', name: 'Nova' })) });
    render(<LeadsBoard hooks={createLeadsHooks(api)} />, { wrapper: wrapperFor() });
    await userEvent.click(await screen.findByTestId('leads-new'));
    await userEvent.type(await screen.findByLabelText(/Nome/), 'Nova');
    await userEvent.click(screen.getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/leads', expect.objectContaining({ name: 'Nova' })));
    await waitFor(() => expect(screen.queryByText('Novo lead', { selector: 'h2' })).not.toBeInTheDocument());
  });
});

describe('LeadDetailModal', () => {
  it('is closed without a lead', () => {
    render(<LeadDetailModal hooks={createLeadsHooks(makeApi())} lead={null} onClose={() => {}} />, { wrapper: wrapperFor() });
    expect(screen.queryByTestId('lead-detail-modal')).not.toBeInTheDocument();
  });

  it('offers "abrir conversa" only for a lead that came from a chat', async () => {
    const onOpen = vi.fn();
    const hooks = createLeadsHooks(makeApi({ 'GET /api/leads/a': env(ana), 'GET /api/leads/b': env(bia) }));
    const { rerender } = render(<LeadDetailModal hooks={hooks} lead={ana} onClose={() => {}} onOpenConversation={onOpen} />, { wrapper: wrapperFor() });
    await userEvent.click(await screen.findByTestId('lead-detail-open-chat'));
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: 'a' }));
    rerender(<LeadDetailModal hooks={hooks} lead={bia} onClose={() => {}} onOpenConversation={onOpen} />);
    await screen.findByText('Bia');
    expect(screen.queryByTestId('lead-detail-open-chat')).not.toBeInTheDocument();
  });

  it('delete asks first; cancelling deletes nothing, confirming deletes and closes', async () => {
    const onClose = vi.fn();
    const api = makeApi({ 'GET /api/leads/a': env(ana), 'DELETE /api/leads/a': null });
    render(<LeadDetailModal hooks={createLeadsHooks(api)} lead={ana} onClose={onClose} />, { wrapper: wrapperFor() });
    await userEvent.click(await screen.findByTestId('lead-detail-delete'));
    await userEvent.click(await screen.findByRole('button', { name: 'Cancelar' }));
    expect(api.delete).not.toHaveBeenCalled();
    await userEvent.click(screen.getByTestId('lead-detail-delete'));
    await userEvent.click(lastButton('Excluir')); // the confirm dialog's button is the last one
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/leads/a'));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('a failed delete says so and keeps the modal open', async () => {
    const onClose = vi.fn();
    const api = makeApi({ 'GET /api/leads/a': env(ana), 'DELETE /api/leads/a': () => Promise.reject(new ApiError(500, 'indisponível')) });
    render(<LeadDetailModal hooks={createLeadsHooks(api)} lead={ana} onClose={onClose} />, { wrapper: wrapperFor() });
    await userEvent.click(await screen.findByTestId('lead-detail-delete'));
    await userEvent.click(lastButton('Excluir'));
    expect(await screen.findByText(/Não foi possível excluir o lead/)).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe('LeadFormDialog', () => {
  it('requires a name before sending anything', async () => {
    const api = makeApi({});
    render(<LeadFormDialog hooks={createLeadsHooks(api)} open lead={null} onClose={() => {}} />, { wrapper: wrapperFor() });
    await userEvent.click(screen.getByRole('button', { name: 'Salvar' }));
    expect(await screen.findByText('Informe o nome.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('shows the server refusal in pt-BR and keeps what was typed', async () => {
    const api = makeApi({
      'POST /api/leads': () => Promise.reject(new ApiError(422, 'x', { error: { code: 'telefone_invalido', message: 'x' } })),
    });
    render(<LeadFormDialog hooks={createLeadsHooks(api)} open lead={null} onClose={() => {}} />, { wrapper: wrapperFor() });
    await userEvent.type(screen.getByLabelText(/Nome/), 'Ana');
    await userEvent.type(screen.getByLabelText(/Telefone/), '12');
    await userEvent.click(screen.getByRole('button', { name: 'Salvar' }));
    expect(await screen.findByText(/Telefone inválido\. Use o DDD/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Telefone/)).toHaveValue('12');
  });

  it('edit patches the lead and does not re-send an untouched first-contact date', async () => {
    const api = makeApi({ 'PATCH /api/leads/a': env({ ...ana, name: 'Ana M' }) });
    const onSaved = vi.fn();
    render(<LeadFormDialog hooks={createLeadsHooks(api)} open lead={ana} onClose={() => {}} onSaved={onSaved} />, { wrapper: wrapperFor() });
    const name = screen.getByLabelText(/Nome/);
    await userEvent.clear(name);
    await userEvent.type(name, 'Ana M');
    await userEvent.click(screen.getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const body = api.patch.mock.calls[0][1] as Record<string, unknown>;
    expect(body.name).toBe('Ana M');
    expect('first_contact_at' in body).toBe(false);
  });
});

describe('LeadsList', () => {
  it('lists leads with origin and stage labels, and an honest empty state', async () => {
    const api = makeApi({ 'GET /api/leads': { data: [ana, bia], next_cursor: null } });
    render(<LeadsList hooks={createLeadsHooks(api)} />, { wrapper: wrapperFor() });
    const row = await screen.findByTestId('lead-row-b');
    expect(within(row).getByText('Instagram')).toBeInTheDocument();
    expect(within(row).getByText('Atendimento')).toBeInTheDocument();
  });

  it('the stage and origin filters go to the server; the empty result names the filter, not "no leads yet"', async () => {
    const api = makeApi({ 'GET /api/leads': (_p: string, params?: any) => ({ data: params?.stage ? [] : [ana], next_cursor: null }) });
    render(<LeadsList hooks={createLeadsHooks(api)} />, { wrapper: wrapperFor() });
    await screen.findByTestId('lead-row-a');
    await userEvent.selectOptions(screen.getByLabelText('Etapa'), 'fechado');
    expect(await screen.findByText('Nenhum lead encontrado para esses filtros.')).toBeInTheDocument();
    expect(api.get).toHaveBeenLastCalledWith('/api/leads', { stage: 'fechado', limit: 50 });
    await userEvent.selectOptions(screen.getByLabelText('Origem'), 'instagram');
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/api/leads', { stage: 'fechado', origin: 'instagram', limit: 50 }));
  });

  it('controlled filters are shared with the host (Funil <-> Lista keep one search)', async () => {
    const api = makeApi({ 'GET /api/leads': { data: [ana], next_cursor: null } });
    const onChange = vi.fn();
    render(<LeadsList hooks={createLeadsHooks(api)} filters={{ origin: 'instagram' }} onFiltersChange={onChange} />, { wrapper: wrapperFor() });
    await screen.findByTestId('lead-row-a');
    expect(api.get).toHaveBeenCalledWith('/api/leads', { origin: 'instagram', limit: 50 });
    await userEvent.selectOptions(screen.getByLabelText('Origem'), 'whatsapp');
    expect(onChange).toHaveBeenCalledWith({ origin: 'whatsapp' });
  });

  it('"Carregar mais" fetches the next page', async () => {
    const api = makeApi({
      'GET /api/leads': (_p: string, params?: any) => (params?.cursor ? { data: [bia], next_cursor: null } : { data: [ana], next_cursor: '1' }),
    });
    render(<LeadsList hooks={createLeadsHooks(api)} />, { wrapper: wrapperFor() });
    await userEvent.click(await screen.findByRole('button', { name: 'Carregar mais' }));
    expect(await screen.findByTestId('lead-row-b')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Carregar mais' })).not.toBeInTheDocument();
  });

  it('a failed first load offers a retry instead of an empty table', async () => {
    const api = makeApi({ 'GET /api/leads': () => Promise.reject(new ApiError(500, 'fora do ar')) });
    render(<LeadsList hooks={createLeadsHooks(api)} />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Não foi possível carregar os leads/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument();
  });
});

it('config labels come from data, not from the organ', async () => {
  const custom = { ...CONFIG, origins: [{ slug: 'whatsapp', label: 'Zap' }, ...CONFIG.origins.slice(1)] };
  const api = makeApi({ 'GET /api/leads/config': env(custom), 'GET /api/leads/board': env(board([ana], [], [])) });
  render(<LeadsBoard hooks={createLeadsHooks(api)} />, { wrapper: wrapperFor() });
  expect(await within(await screen.findByTestId('lead-card-a')).findByText('Zap')).toBeInTheDocument();
});
