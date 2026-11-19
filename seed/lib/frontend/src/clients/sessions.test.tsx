/** Weekly care + session detail: the clinical note's gate, the month summary, the weekly slot form, the history. */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { ApiError } from '../api';
import { ClientSchedulesTab } from './ClientSchedulesTab';
import { ClientsMonthSummary } from './ClientsMonthSummary';
import { createClientsHooks } from './hooks';
import { SessionDetailDialog } from './SessionDetailDialog';
import { client, env, finance, makeApi, schedule, session, wrapperFor } from './testUtils';

const NOTE = 'Falou do luto do pai.';
const pending = session({ id: 's1', status: 'realizada', charge_status: 'pendente', amount_cents: 20000, entry_id: 'e1', payment_status: 'open', notes: 'chegou atrasada' });
const event = (over: Record<string, unknown>) => ({ id: 'ev', client_id: 'c1', session_id: 's1', schedule_id: null, from: null, to: null, actor: null, data: {}, occurred_at: '2026-11-03T13:00:00Z', kind: 'session_created', ...over });
const forbidden = () => Promise.reject(new ApiError(403, 'x', { error: { code: 'FORBIDDEN', message: 'x' } }));

function open(api: ReturnType<typeof makeApi>, over: { isAdmin?: boolean; s?: typeof pending } = {}) {
  render(<SessionDetailDialog hooks={createClientsHooks(api)} open onClose={() => {}} session={over.s ?? pending} isAdmin={over.isAdmin} />, { wrapper: wrapperFor() });
}

describe('SessionDetailDialog: the clinical note', () => {
  it('the therapist reads and saves it; the server keeps the text out of the history', async () => {
    let stored = NOTE; // the server keeps what was last saved: the settle refetch must agree with the committed write
    const api = makeApi({
      'GET /api/clients/sessions/s1/events': env([event({ kind: 'clinical_note_saved' })]),
      'GET /api/clients/sessions/s1/clinical-note': () => env({ session_id: 's1', body: stored, updated_at: null, updated_by: null }),
      'PUT /api/clients/sessions/s1/clinical-note': (_p: string, arg?: unknown) => {
        stored = (arg as { body: string }).body;
        return env({ session_id: 's1', body: stored, updated_at: '2026-11-04T00:00:00Z', updated_by: 'u1' });
      },
    });
    open(api);
    const text = await screen.findByTestId('detail-clinical-text');
    await waitFor(() => expect(text).toHaveValue(NOTE));
    expect(screen.getByTestId('detail-clinical-save')).toBeDisabled(); // nothing changed yet
    await userEvent.type(text, ' Mais.');
    await userEvent.click(screen.getByTestId('detail-clinical-save'));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/api/clients/sessions/s1/clinical-note', { body: `${NOTE} Mais.` }));
    await waitFor(() => expect(screen.getByTestId('detail-clinical-text')).toHaveValue(`${NOTE} Mais.`));
  });

  it('for any other role (403) NOTHING of it is shown: no section, no placeholder, no error', async () => {
    const api = makeApi({ 'GET /api/clients/sessions/s1/events': env([]), 'GET /api/clients/sessions/s1/clinical-note': forbidden });
    open(api);
    await screen.findByTestId('detail-admin-notes');
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/clients/sessions/s1/clinical-note'));
    await waitFor(() => expect(screen.queryByTestId('detail-clinical')).not.toBeInTheDocument());
    expect(screen.queryByText(/Anotações clínicas/)).not.toBeInTheDocument();
    expect(api.get.mock.calls.filter(([p]) => String(p).endsWith('clinical-note'))).toHaveLength(1); // a 403 is never retried
  });

  it('a product with the clinical note off never asks for it', async () => {
    const api = makeApi({ 'GET /api/clients/config': env({ ...(await makeApi().get('/api/clients/config')).data, clinical_notes: false }), 'GET /api/clients/sessions/s1/events': env([]) });
    open(api);
    await screen.findByTestId('detail-admin-notes');
    expect(api.get.mock.calls.some(([p]) => String(p).endsWith('clinical-note'))).toBe(false);
    expect(screen.queryByTestId('detail-clinical')).not.toBeInTheDocument();
  });

  it('a load failure other than the gate offers a retry, and an empty note cannot be saved', async () => {
    const api = makeApi({
      'GET /api/clients/sessions/s1/events': env([]),
      'GET /api/clients/sessions/s1/clinical-note': () => Promise.reject(new ApiError(500, 'boom')),
    });
    open(api);
    expect(await screen.findByText(/Não foi possível carregar a anotação/)).toBeInTheDocument();
    api.route('GET /api/clients/sessions/s1/clinical-note', env({ session_id: 's1', body: '', updated_at: null, updated_by: null }));
    await userEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }));
    const text = await screen.findByTestId('detail-clinical-text');
    await userEvent.type(text, '   ');
    await userEvent.click(screen.getByTestId('detail-clinical-save'));
    expect(await screen.findByText('Escreva a anotação.')).toBeInTheDocument();
    expect(api.put).not.toHaveBeenCalled();
  });
});

describe('SessionDetailDialog: the rest of the session', () => {
  const routes = (extra: Record<string, unknown> = {}) =>
    makeApi({
      'GET /api/clients/sessions/s1/clinical-note': forbidden,
      'GET /api/clients/sessions/s1/events': env([
        event({ id: 'e1', kind: 'session_materialized' }),
        event({ id: 'e2', kind: 'session_status_changed', from: 'agendada', to: 'realizada' }),
        event({ id: 'e3', kind: 'payment_recorded', to: 'pix', data: { method: 'pix', amount_cents: 20000 } }),
      ]),
      ...extra,
    });

  it('shows the history in pt-BR, the charge and what was received', async () => {
    open(routes());
    const history = await screen.findByTestId('detail-history');
    expect(await within(history).findByText(/Sessão criada pelo atendimento semanal/)).toBeInTheDocument();
    expect(within(history).getByText(/Situação: Agendada → Realizada/)).toBeInTheDocument();
    expect(within(history).getByText(/Pagamento registrado \(pix, R\$\s*200,00\)/)).toBeInTheDocument();
    expect(screen.getByTestId('detail-charge')).toHaveTextContent(/Pendente/);
  });

  it('marks the status, saves the administrative note and reschedules', async () => {
    const api = routes({
      'PATCH /api/clients/sessions/s1': env({ ...pending, status: 'falta' }),
      'POST /api/clients/sessions/s1/reschedule': env(session({ id: 's2' })),
    });
    open(api);
    const select = await screen.findByTestId('detail-status');
    await within(select).findByRole('option', { name: 'Falta' });
    await userEvent.selectOptions(select, 'falta');
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/clients/sessions/s1', { status: 'falta' }));
    const notes = within(screen.getByTestId('detail-admin-notes')).getByRole('textbox');
    await userEvent.clear(notes);
    await userEvent.type(notes, 'remarcou');
    await userEvent.click(screen.getByTestId('detail-admin-notes-save'));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/clients/sessions/s1', { notes: 'remarcou' }));
    await userEvent.click(screen.getByTestId('detail-reschedule-toggle'));
    const box = await screen.findByTestId('detail-reschedule');
    const [d, t] = within(box).getAllByDisplayValue(/./);
    await userEvent.clear(d);
    await userEvent.type(d, '2026-11-11');
    await userEvent.clear(t);
    await userEvent.type(t, '16:00');
    await userEvent.click(screen.getByTestId('detail-reschedule-confirm'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/clients/sessions/s1/reschedule', { starts_at: '2026-11-11T16:00:00-03:00' }));
  });

  it('only an admin sees "Registrar pagamento", preselecting this session', async () => {
    const entry = { entry_id: 'e1', session_id: 's1', description: 'Sessão — Ana', amount_cents: 20000, settled_cents: 0, due_date: '2026-11-03', status: 'open', overdue: false };
    const api = routes({
      'GET /api/clients/c1': env(client()),
      'GET /api/clients/c1/finance': env(finance({ open_cents: 35000, entries: [entry, { ...entry, entry_id: 'e2', session_id: 's9', amount_cents: 15000 }] })),
      'GET /api/finance/accounts': env([{ id: 'a1', name: 'Caixa' }]),
    });
    open(api, { isAdmin: true });
    await userEvent.click(await screen.findByTestId('detail-pay'));
    const form = await screen.findByTestId('payment-form');
    expect(within(form).getByLabelText(/Valor recebido/)).toHaveValue('200,00');
    expect(within(form).getByTestId('payment-entry-e1')).toBeChecked();
  });

  it('a non-admin is told who registers payments instead', async () => {
    open(routes());
    expect(await screen.findByText('Apenas administradores registram pagamentos.')).toBeInTheDocument();
    expect(screen.queryByTestId('detail-pay')).not.toBeInTheDocument();
  });

  it('a status refusal is shown, not swallowed', async () => {
    const api = routes({ 'PATCH /api/clients/sessions/s1': () => Promise.reject(new ApiError(409, 'x', { error: { code: 'SESSAO_COM_PAGAMENTO', message: 'x' } })) });
    open(api);
    const select = await screen.findByTestId('detail-status');
    await within(select).findByRole('option', { name: 'Cancelada pela paciente' });
    await userEvent.selectOptions(select, 'cancelada_paciente');
    expect(await screen.findByText(/já tem pagamento registrado/)).toBeInTheDocument();
  });
});

describe('ClientsMonthSummary', () => {
  const month = { month: '2026-11', sessions: 5, by_status: { agendada: 1, realizada: 3, falta: 1 }, charged_cents: 80000, received_cents: 60000, open_cents: 20000, overdue_cents: 0 };

  it('shows sessions, done, absences, charged, received and open; the arrows move the month', async () => {
    const api = makeApi({ 'GET /api/clients/summary': (_p: string, q?: unknown) => env((q as { month: string }).month === '2026-12' ? { ...month, month: '2026-12', sessions: 0 } : month) });
    render(<ClientsMonthSummary hooks={createClientsHooks(api)} month="2026-11" />, { wrapper: wrapperFor() });
    expect(await screen.findByTestId('month-sessions')).toHaveTextContent('5');
    expect(screen.getByTestId('month-label')).toHaveTextContent('novembro de 2026');
    expect(screen.getByTestId('month-done')).toHaveTextContent('3');
    expect(screen.getByTestId('month-absences')).toHaveTextContent('1');
    expect(screen.getByTestId('month-received')).toHaveTextContent(/600,00/);
    expect(screen.getByTestId('month-open')).toHaveTextContent(/200,00/);
    await userEvent.click(screen.getByTestId('month-next'));
    expect(await screen.findByText('Nenhuma sessão neste mês.')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/api/clients/summary', { month: '2026-12' });
  });

  it('says so when the load fails', async () => {
    const api = makeApi({ 'GET /api/clients/summary': () => Promise.reject(new ApiError(500, 'x')) });
    render(<ClientsMonthSummary hooks={createClientsHooks(api)} month="2026-11" />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Não foi possível carregar o resumo do mês/)).toBeInTheDocument();
  });
});

describe('ClientSchedulesTab: atendimento semanal', () => {
  const c = client();

  it('a new slot leaves "a partir de" to the server and charges absences by default', async () => {
    const api = makeApi({ 'GET /api/clients/c1/schedules': env([]), 'POST /api/clients/c1/schedules': env(schedule()) });
    render(<ClientSchedulesTab hooks={createClientsHooks(api)} client={c} />, { wrapper: wrapperFor() });
    await userEvent.click(await screen.findByTestId('schedules-new'));
    const form = await screen.findByTestId('schedule-form');
    expect(within(form).getByTestId('schedule-charge-absences')).toBeChecked();
    expect(within(form).queryByTestId('schedule-apply-existing')).not.toBeInTheDocument();
    await userEvent.type(within(form).getByLabelText(/Horário/), '14:00');
    await userEvent.click(within(form).getByTestId('schedule-save'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/clients/c1/schedules', expect.objectContaining({ weekday: 0, time: '14:00', charge_absences: true, ends_on: null })));
    expect((api.post.mock.calls[0][1] as { starts_on?: string }).starts_on).toBeUndefined();
  });

  it('shows the status and, per slot, whether absences are charged; pausing and ending are offered, an ended one is read-only', async () => {
    const api = makeApi({
      'GET /api/clients/c1/schedules': env([
        schedule({ id: 'h1', charge_absences: false }),
        schedule({ id: 'h2', status: 'pausada', active: false }),
        schedule({ id: 'h3', status: 'encerrada', ends_on: '2026-10-20' }),
      ]),
      'PATCH /api/clients/schedules/h1': env(schedule({ id: 'h1', charge_absences: false })),
    });
    render(<ClientSchedulesTab hooks={createClientsHooks(api)} client={c} />, { wrapper: wrapperFor() });
    expect(await screen.findByTestId('schedule-status-h1')).toHaveTextContent('Ativa');
    expect(screen.getByTestId('schedule-row-h1')).toHaveTextContent('não cobra faltas');
    expect(screen.getByTestId('schedule-status-h2')).toHaveTextContent('Pausada');
    expect(screen.getByTestId('schedule-status-h3')).toHaveTextContent('Encerrada');
    expect(screen.queryByTestId('schedule-toggle-h3')).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId('schedule-toggle-h1'));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/clients/schedules/h1', { active: false }));
  });

  it('an edit can leave the session already created alone', async () => {
    const api = makeApi({ 'GET /api/clients/c1/schedules': env([schedule({ id: 'h1' })]), 'PATCH /api/clients/schedules/h1': env(schedule({ id: 'h1', time: '15:00' })) });
    render(<ClientSchedulesTab hooks={createClientsHooks(api)} client={c} />, { wrapper: wrapperFor() });
    await userEvent.click(await screen.findByLabelText('Editar'));
    const form = await screen.findByTestId('schedule-form');
    await userEvent.clear(within(form).getByLabelText(/Horário/));
    await userEvent.type(within(form).getByLabelText(/Horário/), '15:00');
    await userEvent.click(within(form).getByTestId('schedule-apply-existing'));
    await userEvent.click(within(form).getByTestId('schedule-save'));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/clients/schedules/h1', expect.objectContaining({ time: '15:00', apply_to_existing: false })));
  });
});
