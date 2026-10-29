import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api';
import { ClientDetailPage } from './ClientDetailPage';
import { ClientsAgenda } from './ClientsAgenda';
import { ClientsList } from './ClientsList';
import { createClientsHooks } from './hooks';
import { SessionFormDialog } from './SessionFormDialog';
import { client, env, finance, makeApi, schedule, session, wrapperFor } from './testUtils';

const DAY = 86_400_000;
const ana = client({
  id: 'c1',
  name: 'Ana Souza',
  tags: ['online', 'quinzenal'],
  summary: { next_session_at: '2026-11-03T14:00:00-03:00', last_session_at: null, sessions_done: 4, open_cents: 35000, overdue_cents: 15000, paid_cents: 80000 },
});
const bia = client({ id: 'c2', name: 'Bia', status: 'pausado' });

const lastButton = (name: string | RegExp) => {
  const all = screen.getAllByRole('button', { name });
  return all[all.length - 1];
};

describe('ClientsList', () => {
  it('shows name, coloured status, tag chips, next session and the open amount; the noun is config', async () => {
    const api = makeApi({ 'GET /api/clients': { data: [ana, bia], next_cursor: null } });
    render(<ClientsList hooks={createClientsHooks(api)} onOpenClient={() => {}} />, { wrapper: wrapperFor() });
    const row = await screen.findByTestId('client-row-c1');
    expect(within(row).getByText('Ativo').className).toContain('text-success');
    expect(within(row).getByText('online')).toBeInTheDocument();
    expect(within(row).getByText('ter, 03/11/2026 14:00')).toBeInTheDocument();
    expect(within(row).getByText(/350,00/)).toBeInTheDocument();
    expect(within(screen.getByTestId('client-row-c2')).getByText('Pausado').className).toContain('text-warning');
    expect(screen.getByTestId('clients-new')).toHaveTextContent('Novo paciente');
  });

  it('a row opens the client', async () => {
    const onOpen = vi.fn();
    const api = makeApi({ 'GET /api/clients': { data: [ana], next_cursor: null } });
    render(<ClientsList hooks={createClientsHooks(api)} onOpenClient={onOpen} />, { wrapper: wrapperFor() });
    await userEvent.click(await screen.findByText('Ana Souza'));
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: 'c1' }));
  });

  it('status / tag / search go to the server; an empty filtered result names the filter', async () => {
    const api = makeApi({
      'GET /api/clients': (_p: string, params?: any) => ({ data: params?.status ? [] : [ana], next_cursor: null }),
      'GET /api/clients/tags': env(['online', 'vip']),
    });
    render(<ClientsList hooks={createClientsHooks(api)} onOpenClient={() => {}} />, { wrapper: wrapperFor() });
    await screen.findByTestId('client-row-c1');
    await userEvent.selectOptions(screen.getByLabelText('Situação'), 'encerrado');
    expect(await screen.findByText('Nenhum paciente encontrado para esses filtros.')).toBeInTheDocument();
    expect(api.get).toHaveBeenLastCalledWith('/api/clients', { status: 'encerrado', limit: 50 });
    await waitFor(() => expect(screen.getByRole('option', { name: 'vip' })).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText('Etiqueta'), 'vip');
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/api/clients', { status: 'encerrado', tag: 'vip', limit: 50 }));
    fireEvent.change(screen.getByLabelText('Buscar por nome, telefone ou e-mail'), { target: { value: 'ana' } });
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/api/clients', { q: 'ana', status: 'encerrado', tag: 'vip', limit: 50 }));
  });

  it('a failed first load offers a retry, not an empty table', async () => {
    const api = makeApi({ 'GET /api/clients': () => Promise.reject(new ApiError(500, 'fora do ar')) });
    render(<ClientsList hooks={createClientsHooks(api)} onOpenClient={() => {}} />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Não foi possível carregar os pacientes/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument();
    expect(screen.queryByText('Nenhum paciente ainda.')).not.toBeInTheDocument();
  });

  it('"Novo" creates the client and opens it', async () => {
    const onOpen = vi.fn();
    const api = makeApi({ 'GET /api/clients': { data: [], next_cursor: null }, 'POST /api/clients': env(client({ id: 'n', name: 'Nova' })) });
    render(<ClientsList hooks={createClientsHooks(api)} onOpenClient={onOpen} />, { wrapper: wrapperFor() });
    expect(await screen.findByText('Nenhum paciente ainda.')).toBeInTheDocument();
    await userEvent.click(screen.getByTestId('clients-new'));
    await userEvent.type(await screen.findByLabelText(/Nome/), 'Nova');
    await userEvent.type(screen.getByLabelText(/Valor da sessão/), '180');
    await userEvent.click(screen.getByTestId('client-form-save'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/clients', expect.objectContaining({ name: 'Nova', default_price_cents: 18000, tags: [] })));
    await waitFor(() => expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: 'n' })));
  });
});

describe('ClientDetailPage', () => {
  const future = session({ id: 'sf', starts_at: new Date(Date.now() + 2 * DAY).toISOString() });
  const past = session({ id: 'sp', starts_at: new Date(Date.now() - 7 * DAY).toISOString(), status: 'realizada', payment_status: 'overdue', entry_id: 'e1' });
  const routes = (extra: Record<string, unknown> = {}) => ({
    'GET /api/clients/c1': env(ana),
    'GET /api/clients/c1/sessions': env([future, past]),
    'GET /api/clients/c1/schedules': env([schedule()]),
    'GET /api/clients/c1/finance': env(
      finance({
        open_cents: 35000,
        overdue_cents: 15000,
        paid_cents: 80000,
        entries: [
          { entry_id: 'e1', session_id: 'sp', description: 'Sessão — Ana', amount_cents: 15000, settled_cents: 0, due_date: '2026-10-20', status: 'open', overdue: true },
          { entry_id: 'e2', session_id: null, description: 'Sessão — Ana 2', amount_cents: 20000, settled_cents: 0, due_date: '2026-10-27', status: 'open', overdue: false },
        ],
      }),
    ),
    'GET /api/finance/accounts': env([{ id: 'a1', name: 'Conta PJ' }]),
    ...extra,
  });

  it('header + sessions: upcoming and past split, coloured status switch, payment chip', async () => {
    render(<ClientDetailPage hooks={createClientsHooks(makeApi(routes()))} clientId="c1" />, { wrapper: wrapperFor() });
    expect(await screen.findByRole('heading', { name: 'Ana Souza' })).toBeInTheDocument();
    expect(screen.getByTestId('client-status')).toHaveTextContent('Ativo');
    expect(screen.getByTestId('client-done')).toHaveTextContent('4');
    expect(await within(await screen.findByTestId('sessions-upcoming')).findByTestId('session-row-sf')).toBeInTheDocument();
    const pastRow = within(screen.getByTestId('sessions-past')).getByTestId('session-row-sp');
    expect(within(pastRow).getByText('Vencido').className).toContain('text-destructive');
    expect(screen.getByTestId('session-status-sp').className).toContain('text-success');
  });

  it('the quick status switch patches the session', async () => {
    const api = makeApi(routes({ 'PATCH /api/clients/sessions/sf': env({ ...future, status: 'falta' }) }));
    render(<ClientDetailPage hooks={createClientsHooks(api)} clientId="c1" />, { wrapper: wrapperFor() });
    await userEvent.selectOptions(await screen.findByTestId('session-status-sf'), 'falta');
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/clients/sessions/sf', { status: 'falta' }));
  });

  it('"Nova sessão" posts the typed date + time in the org zone', async () => {
    const api = makeApi(routes({ 'POST /api/clients/c1/sessions': env(session({ id: 'n1' })) }));
    render(<ClientDetailPage hooks={createClientsHooks(api)} clientId="c1" />, { wrapper: wrapperFor() });
    await userEvent.click(await screen.findByTestId('sessions-new'));
    const form = await screen.findByTestId('session-form');
    fireEvent.change(within(form).getByLabelText(/Data/), { target: { value: '2026-11-10' } });
    fireEvent.change(within(form).getByLabelText(/Horário/), { target: { value: '09:30' } });
    await userEvent.click(within(form).getByTestId('session-save'));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/clients/c1/sessions', expect.objectContaining({ starts_at: '2026-11-10T09:30:00-03:00', duration_min: 50, waive_charge: false })),
    );
  });

  it('agenda fixa lists the weekly slots', async () => {
    render(<ClientDetailPage hooks={createClientsHooks(makeApi(routes()))} clientId="c1" tab="agenda" />, { wrapper: wrapperFor() });
    expect(await screen.findByText('Toda terça, 14:00')).toBeInTheDocument();
  });

  it('financeiro: tiles + entries; a non-admin cannot register a payment', async () => {
    render(<ClientDetailPage hooks={createClientsHooks(makeApi(routes()))} clientId="c1" tab="financeiro" />, { wrapper: wrapperFor() });
    expect(await screen.findByTestId('finance-entry-e1')).toBeInTheDocument();
    expect(screen.getByTestId('finance-overdue')).toHaveTextContent(/150,00/);
    expect(screen.queryByTestId('finance-pay')).not.toBeInTheDocument();
    expect(screen.getByText('Apenas administradores registram pagamentos.')).toBeInTheDocument();
  });

  it('an admin registers a payment: amount prefilled with the open total, the single account preselected, method required', async () => {
    const after = finance({ paid_cents: 115000 });
    const api = makeApi(routes({ 'POST /api/clients/c1/payments': env({ settlement_ids: ['x'], finance: after }) }));
    render(<ClientDetailPage hooks={createClientsHooks(api)} clientId="c1" tab="financeiro" isAdmin />, { wrapper: wrapperFor() });
    await userEvent.click(await screen.findByTestId('finance-pay'));
    const form = await screen.findByTestId('payment-form');
    expect(within(form).getByLabelText(/Valor recebido/)).toHaveValue('350,00');
    await waitFor(() => expect(within(form).getByLabelText(/Conta/)).toHaveValue('a1'));
    await userEvent.click(within(form).getByTestId('payment-submit'));
    expect(await within(form).findByText('Escolha a forma de pagamento.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
    await userEvent.click(within(form).getByTestId('payment-entry-e1'));
    expect(within(form).getByLabelText(/Valor recebido/)).toHaveValue('150,00');
    await userEvent.selectOptions(within(form).getByLabelText(/Forma de pagamento/), 'pix');
    await userEvent.click(within(form).getByTestId('payment-submit'));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/clients/c1/payments', expect.objectContaining({ amount_cents: 15000, account_id: 'a1', method: 'pix', entry_ids: ['e1'] })),
    );
  });

  it('a payment refusal is shown in the dialog', async () => {
    const api = makeApi(routes({ 'POST /api/clients/c1/payments': () => Promise.reject(new ApiError(422, 'x', { error: { code: 'VALOR_EXCEDE_ABERTO', message: 'x' } })) }));
    render(<ClientDetailPage hooks={createClientsHooks(api)} clientId="c1" tab="financeiro" isAdmin />, { wrapper: wrapperFor() });
    await userEvent.click(await screen.findByTestId('finance-pay'));
    const form = await screen.findByTestId('payment-form');
    await userEvent.selectOptions(within(form).getByLabelText(/Forma de pagamento/), 'pix');
    await waitFor(() => expect(within(form).getByLabelText(/Conta/)).toHaveValue('a1'));
    await userEvent.click(within(form).getByTestId('payment-submit'));
    expect(await within(form).findByText('O valor é maior do que o total em aberto.')).toBeInTheDocument();
  });

  it('dados: a delete refused for finance offers to close the client instead', async () => {
    const api = makeApi(
      routes({
        'DELETE /api/clients/c1': () => Promise.reject(new ApiError(409, 'x', { error: { code: 'CLIENTE_COM_FINANCEIRO', message: 'x' } })),
        'PATCH /api/clients/c1': env({ ...ana, status: 'encerrado', updated_at: '2026-11-01T00:00:00Z' }),
      }),
    );
    const onDeleted = vi.fn();
    render(<ClientDetailPage hooks={createClientsHooks(api)} clientId="c1" tab="dados" isAdmin onDeleted={onDeleted} />, { wrapper: wrapperFor() });
    await userEvent.click(await screen.findByTestId('client-delete'));
    await userEvent.click(lastButton('Excluir'));
    expect(await screen.findByText(/não pode ser excluído\. Encerre-o/)).toBeInTheDocument();
    expect(onDeleted).not.toHaveBeenCalled();
    await userEvent.click(screen.getByTestId('client-close-instead'));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/clients/c1', { status: 'encerrado' }));
  });

  it('dados: a non-admin edits but cannot delete; only changed fields are sent', async () => {
    const api = makeApi(routes({ 'PATCH /api/clients/c1': env({ ...ana, notes: 'x' }) }));
    render(<ClientDetailPage hooks={createClientsHooks(api)} clientId="c1" tab="dados" />, { wrapper: wrapperFor() });
    const form = await screen.findByTestId('client-form');
    expect(screen.queryByTestId('client-delete')).not.toBeInTheDocument();
    await userEvent.type(within(form).getByLabelText(/Observações/), 'x');
    await userEvent.click(within(form).getByTestId('client-form-save'));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/clients/c1', { notes: 'x' }));
  });

  it('a missing client says so', async () => {
    const api = makeApi({ 'GET /api/clients/zz': () => Promise.reject(new ApiError(404, 'não encontrado')) });
    render(<ClientDetailPage hooks={createClientsHooks(api)} clientId="zz" />, { wrapper: wrapperFor() });
    expect(await screen.findByText('Este paciente não existe mais.')).toBeInTheDocument();
  });
});

describe('ClientsAgenda', () => {
  const now = Date.parse('2026-11-04T15:00:00Z'); // Wednesday in São Paulo
  const a = session({ id: 'a', starts_at: '2026-11-03T14:00:00-03:00', status: 'realizada' });
  const b = session({ id: 'b', client_id: 'c2', client_name: 'Bia', starts_at: '2026-11-03T09:00:00-03:00' });

  it('shows the week Monday-Sunday with chips in time order, coloured by status', async () => {
    const api = makeApi({ 'GET /api/clients/sessions': env([a, b]) });
    render(<ClientsAgenda hooks={createClientsHooks(api)} now={now} />, { wrapper: wrapperFor() });
    const tue = await screen.findByTestId('agenda-day-2026-11-03');
    await waitFor(() => expect(within(tue).getAllByRole('button').map((x) => x.textContent)).toEqual(['09:00 Bia', '14:00 Ana Souza']));
    expect(screen.getByTestId('agenda-session-a').className).toContain('text-success');
    expect(api.get).toHaveBeenCalledWith('/api/clients/sessions', { from: '2026-11-02', to: '2026-11-08' });
    expect(within(screen.getByTestId('agenda-day-2026-11-05')).getByText('Livre')).toBeInTheDocument();
  });

  it('next / previous week fetch their range', async () => {
    const api = makeApi({ 'GET /api/clients/sessions': env([]) });
    render(<ClientsAgenda hooks={createClientsHooks(api)} now={now} />, { wrapper: wrapperFor() });
    await screen.findByTestId('agenda-day-2026-11-02');
    await userEvent.click(screen.getByTestId('agenda-next'));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/clients/sessions', { from: '2026-11-09', to: '2026-11-15' }));
    await userEvent.click(screen.getByTestId('agenda-prev'));
    await userEvent.click(screen.getByTestId('agenda-prev'));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/clients/sessions', { from: '2026-10-26', to: '2026-11-01' }));
  });

  it('a chip opens the session; "Abrir paciente" goes to the client', async () => {
    const onOpenClient = vi.fn();
    const api = makeApi({ 'GET /api/clients/sessions': env([b]) });
    render(<ClientsAgenda hooks={createClientsHooks(api)} now={now} onOpenClient={onOpenClient} />, { wrapper: wrapperFor() });
    await userEvent.click(await screen.findByTestId('agenda-session-b'));
    const form = await screen.findByTestId('session-form');
    expect(within(form).getByLabelText(/Horário/)).toHaveValue('09:00');
    await userEvent.click(within(form).getByTestId('session-open-client'));
    expect(onOpenClient).toHaveBeenCalledWith('c2');
  });

  it('a failed week load offers a retry', async () => {
    const api = makeApi({ 'GET /api/clients/sessions': () => Promise.reject(new ApiError(500, 'x')) });
    render(<ClientsAgenda hooks={createClientsHooks(api)} now={now} />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Não foi possível carregar a agenda/)).toBeInTheDocument();
  });
});

describe('SessionFormDialog', () => {
  it('a refusal to delete a paid session is shown in the form', async () => {
    const s = session({ id: 's9', status: 'realizada', payment_status: 'paid' });
    const api = makeApi({ 'DELETE /api/clients/sessions/s9': () => Promise.reject(new ApiError(409, 'x', { error: { code: 'SESSAO_COM_PAGAMENTO', message: 'x' } })) });
    render(<SessionFormDialog hooks={createClientsHooks(api)} open onClose={() => {}} clientId="c1" session={s} />, { wrapper: wrapperFor() });
    await userEvent.click(await screen.findByTestId('session-delete'));
    await userEvent.click(lastButton('Excluir'));
    expect(await screen.findByText(/já tem pagamento registrado/)).toBeInTheDocument();
  });
});
