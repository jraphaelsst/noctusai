import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RemindersPage, offsetLabel } from './RemindersPage';
import { createFinanceReminderHooks } from './reminderHooks';
import { MESSAGES } from './messages';
import { REMINDER_LOG_STATUSES, REMINDER_SKIP_REASONS, REMINDER_VARIABLES, type ReminderPreview, type ReminderRule } from './reminderTypes';
import { ApiError } from '../api';
import { makeRoutedApi, ok, page, wrapperFor } from './testUtils';
import type { FinanceApi } from './hooks';

afterEach(cleanup);

const B = '/api/finance/reminders';
const SETTINGS_OFF = { enabled: false, timezone: 'America/Sao_Paulo', variables: [...REMINDER_VARIABLES] };
const SETTINGS_ON = { ...SETTINGS_OFF, enabled: true };
const RULE_BEFORE: ReminderRule = { id: 'r1', channel: 'whatsapp', offset_days: -3, template: 'Oi {nome}, vence em 3 dias', enabled: true };
const RULE_AFTER: ReminderRule = { id: 'r2', channel: 'whatsapp', offset_days: 7, template: 'Oi {nome}, atrasou {dias_atraso} dias', enabled: false };
const PREVIEW: ReminderPreview = {
  on: '2026-10-20', enabled: true,
  planned: [{ entry_id: 'e1', rule_id: 'r1', channel: 'whatsapp', offset_days: -3, cycle_date: '2026-10-23', recipient: '11999998888', text: 'Oi Maria, vence em 3 dias', already: null, description: 'Mensalidade Maria' }],
  skipped: [{ entry_id: 'e2', rule_id: 'r1', reason: 'receivable_opt_out', description: 'Mensalidade João' }],
};

function hooksOf(routes: Record<string, unknown>) {
  const api = makeRoutedApi(routes);
  return { api, hooks: createFinanceReminderHooks(api as unknown as FinanceApi) };
}

describe('RemindersPage — switch', () => {
  it('shows the OFF notice, and an admin enabling sends only {enabled:true}', async () => {
    const user = userEvent.setup();
    const { api, hooks } = hooksOf({ [`GET ${B}/settings`]: ok(SETTINGS_OFF), [`PUT ${B}/settings`]: ok(SETTINGS_ON), [`GET ${B}/rules`]: ok([]) });
    render(<RemindersPage hooks={hooks} isAdmin />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Os lembretes estão desligados/)).toBeInTheDocument();
    await user.click(screen.getByRole('switch', { name: 'Lembretes ativados' }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith(`${B}/settings`, { enabled: true }));
  });

  it('staff can read but not toggle or edit', async () => {
    const { hooks } = hooksOf({ [`GET ${B}/settings`]: ok(SETTINGS_ON), [`GET ${B}/rules`]: ok([RULE_BEFORE]) });
    render(<RemindersPage hooks={hooks} />, { wrapper: wrapperFor() });
    expect(await screen.findByText('Oi {nome}, vence em 3 dias')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Lembretes ativados' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Nova regra' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Editar' })).not.toBeInTheDocument();
  });

  it('skeleton then error with retry', async () => {
    const { unmount } = render(<RemindersPage hooks={hooksOf({ [`GET ${B}/settings`]: () => new Promise(() => {}) }).hooks} />, { wrapper: wrapperFor() });
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    unmount();
    render(<RemindersPage hooks={hooksOf({ [`GET ${B}/settings`]: () => Promise.reject(new ApiError(500, 'x')) }).hooks} />, { wrapper: wrapperFor() });
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
  });
});

describe('RemindersPage — rules', () => {
  const routes = () => ({ [`GET ${B}/settings`]: ok(SETTINGS_ON), [`GET ${B}/rules`]: ok([RULE_AFTER, RULE_BEFORE]) });

  it('lists the rules ordered by offset with human labels', async () => {
    const { hooks } = hooksOf(routes());
    render(<RemindersPage hooks={hooks} isAdmin />, { wrapper: wrapperFor() });
    const items = await screen.findAllByRole('listitem');
    expect(items[0]).toHaveTextContent('3 dias antes');
    expect(items[1]).toHaveTextContent('7 dias depois');
    expect(offsetLabel(0)).toBe('No dia do vencimento');
    expect(offsetLabel(1)).toBe('1 dia depois');
    expect(offsetLabel(-1)).toBe('1 dia antes');
  });

  it('creates a rule; variable chips insert at the cursor', async () => {
    const user = userEvent.setup();
    const { api, hooks } = hooksOf({ ...routes(), [`POST ${B}/rules`]: ok({ ...RULE_BEFORE, id: 'r3', offset_days: 0 }) });
    render(<RemindersPage hooks={hooks} isAdmin />, { wrapper: wrapperFor() });
    await user.click(await screen.findByRole('button', { name: 'Nova regra' }));
    const form = screen.getByRole('form', { name: 'Dados da regra' });
    await user.type(within(form).getByLabelText(/^Dias em relação ao vencimento/), '0');
    const box = within(form).getByLabelText(/^Mensagem/);
    await user.type(box, 'Olá ');
    await user.click(within(form).getByRole('button', { name: '{nome}' }));
    await user.click(within(form).getByRole('button', { name: '{link_pagamento}' }));
    expect(box).toHaveValue('Olá {nome}{link_pagamento}');
    await user.click(within(form).getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post.mock.calls[0]).toEqual([`${B}/rules`, { offset_days: 0, template: 'Olá {nome}{link_pagamento}', enabled: true }]);
  });

  it('validates locally, and renders the server message for an unknown variable', async () => {
    const user = userEvent.setup();
    const { api, hooks } = hooksOf({ ...routes(), [`POST ${B}/rules`]: () => Promise.reject(new ApiError(422, 'Variáveis desconhecidas: {nom}.')) });
    render(<RemindersPage hooks={hooks} isAdmin />, { wrapper: wrapperFor() });
    await user.click(await screen.findByRole('button', { name: 'Nova regra' }));
    const form = screen.getByRole('form', { name: 'Dados da regra' });
    await user.click(within(form).getByRole('button', { name: 'Salvar' }));
    expect(await within(form).findByText('Informe um número inteiro de dias.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
    await user.type(within(form).getByLabelText(/^Dias em relação ao vencimento/), '2');
    await user.type(within(form).getByLabelText(/^Mensagem/), 'Oi {{nom}');
    await user.click(within(form).getByRole('button', { name: 'Salvar' }));
    expect(await within(form).findByText(/Variáveis desconhecidas: \{nom\}/)).toBeInTheDocument();
    expect(form).toBeInTheDocument(); // stays open so the user can fix it
  });

  it('toggles a rule, edits, deletes with confirmation, and adds the defaults', async () => {
    const user = userEvent.setup();
    const { api, hooks } = hooksOf({
      ...routes(),
      [`PATCH ${B}/rules/r2`]: ok(RULE_AFTER), [`PATCH ${B}/rules/r1`]: ok(RULE_BEFORE),
      [`DELETE ${B}/rules/r1`]: ok({}), [`POST ${B}/rules/defaults`]: ok([]),
    });
    render(<RemindersPage hooks={hooks} isAdmin />, { wrapper: wrapperFor() });
    await user.click(await screen.findByRole('switch', { name: 'Regra ativa: 7 dias depois' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith(`${B}/rules/r2`, { enabled: true }));
    await user.click(screen.getByRole('button', { name: 'Adicionar regras padrão' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(`${B}/rules/defaults`));
    const first = (await screen.findAllByRole('listitem'))[0];
    await user.click(within(first).getByRole('button', { name: 'Excluir' }));
    expect(api.delete).not.toHaveBeenCalled();
    await user.click(within(first).getByRole('button', { name: 'Excluir regra' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith(`${B}/rules/r1`));
    await user.click(within((await screen.findAllByRole('listitem'))[0]).getByRole('button', { name: 'Editar' }));
    const form = screen.getByRole('form', { name: 'Dados da regra' });
    expect(within(form).getByLabelText(/^Dias em relação ao vencimento/)).toHaveValue(-3);
    await user.click(within(form).getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith(`${B}/rules/r1`, { offset_days: -3, template: 'Oi {nome}, vence em 3 dias', enabled: true }));
  });

  it('shows the empty state', async () => {
    const { hooks } = hooksOf({ [`GET ${B}/settings`]: ok(SETTINGS_ON), [`GET ${B}/rules`]: ok([]) });
    render(<RemindersPage hooks={hooks} isAdmin />, { wrapper: wrapperFor() });
    expect(await screen.findByText('Nenhuma regra cadastrada.')).toBeInTheDocument();
  });
});

describe('RemindersPage — today', () => {
  const open = async (routes: Record<string, unknown>, isAdmin = true) => {
    const user = userEvent.setup();
    const h = hooksOf({ [`GET ${B}/settings`]: ok(SETTINGS_ON), [`GET ${B}/rules`]: ok([]), ...routes });
    render(<RemindersPage hooks={h.hooks} isAdmin={isAdmin} />, { wrapper: wrapperFor() });
    await user.click(await screen.findByRole('tab', { name: 'Saem hoje' }));
    return { user, ...h };
  };

  it('lists what would go out and what is skipped, with reasons', async () => {
    await open({ [`GET ${B}/preview`]: ok(PREVIEW) });
    expect(await screen.findByText('Oi Maria, vence em 3 dias')).toBeInTheDocument();
    expect(screen.getByText('Mensalidade Maria')).toBeInTheDocument();
    expect(screen.getByText(/Conta marcada para não receber lembretes/)).toBeInTheDocument();
  });

  it('opt-out and opt-in call the receivable endpoint', async () => {
    const { user, api } = await open({ [`GET ${B}/preview`]: ok(PREVIEW), [`PUT ${B}/receivables/e1/opt-out`]: ok({}), [`PUT ${B}/receivables/e2/opt-out`]: ok({}) });
    await user.click(await screen.findByRole('button', { name: 'Não lembrar esta conta' }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith(`${B}/receivables/e1/opt-out`, { opt_out: true }));
    await user.click(screen.getByRole('button', { name: 'Voltar a lembrar' }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith(`${B}/receivables/e2/opt-out`, { opt_out: false }));
  });

  it('staff get no opt-out buttons; empty and OFF states', async () => {
    await open({ [`GET ${B}/preview`]: ok(PREVIEW) }, false);
    await screen.findByText('Oi Maria, vence em 3 dias');
    expect(screen.queryByRole('button', { name: 'Não lembrar esta conta' })).not.toBeInTheDocument();
    cleanup();
    await open({ [`GET ${B}/preview`]: ok({ ...PREVIEW, planned: [], skipped: [] }) });
    expect(await screen.findByText('Nenhum lembrete sai hoje.')).toBeInTheDocument();
    cleanup();
    const user = userEvent.setup();
    const h = hooksOf({ [`GET ${B}/settings`]: ok(SETTINGS_OFF), [`GET ${B}/rules`]: ok([]), [`GET ${B}/preview`]: ok({ ...PREVIEW, enabled: false, planned: [], skipped: [] }) });
    render(<RemindersPage hooks={h.hooks} />, { wrapper: wrapperFor() });
    await user.click(await screen.findByRole('tab', { name: 'Saem hoje' }));
    expect(await screen.findByText('Com os lembretes desligados, nada sai hoje.')).toBeInTheDocument();
  });
});

describe('RemindersPage — log', () => {
  const row = (over = {}) => ({
    id: 'l1', entry_id: 'e1', rule_id: 'r1', channel: 'whatsapp', offset_days: -3, cycle_date: '2026-10-23', status: 'sent', attempts: 1,
    recipient: '11999998888', message: 'Oi Maria', last_error: null, sent_at: '2026-10-20T15:00:00Z', created_at: '2026-10-20T15:00:00Z', ...over,
  });

  it('shows rows with status, error, filters and paginates', async () => {
    const user = userEvent.setup();
    const { api, hooks } = hooksOf({
      [`GET ${B}/settings`]: ok(SETTINGS_ON), [`GET ${B}/rules`]: ok([]),
      [`GET ${B}/log`]: (_p: string, params?: { status?: string; page?: number }) =>
        params?.status === 'failed'
          ? page([row({ id: 'l2', status: 'failed', attempts: 3, last_error: 'sem linha de WhatsApp conectada', message: 'Falhou msg' })])
          : page([row()], { total: 45 }),
    });
    render(<RemindersPage hooks={hooks} />, { wrapper: wrapperFor() });
    await user.click(await screen.findByRole('tab', { name: 'Histórico' }));
    expect(await screen.findByText('Oi Maria')).toBeInTheDocument();
    expect(screen.getByText('1 / 3')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Próxima' }));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(`${B}/log`, { status: '', page: 2, page_size: 20 }));
    await user.selectOptions(screen.getByLabelText('Filtrar por situação'), 'failed');
    expect(await screen.findByText('sem linha de WhatsApp conectada')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith(`${B}/log`, { status: 'failed', page: 1, page_size: 20 });
  });

  it('empty state', async () => {
    const user = userEvent.setup();
    const { hooks } = hooksOf({ [`GET ${B}/settings`]: ok(SETTINGS_ON), [`GET ${B}/rules`]: ok([]), [`GET ${B}/log`]: page([]) });
    render(<RemindersPage hooks={hooks} />, { wrapper: wrapperFor() });
    await user.click(await screen.findByRole('tab', { name: 'Histórico' }));
    expect(await screen.findByText('Nenhum lembrete enviado ainda.')).toBeInTheDocument();
  });
});

describe('reminders messages', () => {
  it('every enum value and tab has a label', () => {
    const keys = [
      ...REMINDER_LOG_STATUSES.map((s) => `reminders.status.${s}`),
      ...REMINDER_SKIP_REASONS.map((r) => `reminders.skip.${r}`),
      ...['rules', 'today', 'log'].map((k) => `reminders.tab_${k}`),
    ];
    expect(keys.filter((k) => !(k in MESSAGES))).toEqual([]);
  });
});
