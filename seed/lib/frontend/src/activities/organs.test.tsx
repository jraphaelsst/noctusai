/** Organ behaviour: every state (skeleton, error+retry, empty, data, refreshing) and each write path, with pt-BR copy. */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ApiError } from '../api';
import { ActivitiesPanel } from './ActivitiesPanel';
import { createActivitiesHooks } from './hooks';
import { MyTasksPage } from './MyTasksPage';
import { activity, ENTITY, makeApi, page, type as type_, wrapperFor } from './testUtils';

afterEach(cleanup);

const TYPES = { 'GET /api/activities/types': { data: [type_(), type_({ slug: 'visita', label: 'Visita', kind: 'visit', position: 1 })] } };
/** A tiny stateful server: GET answers what the POSTs left behind (the settle refetch must agree with the cache write). */
function server(initial: ReturnType<typeof activity>[]) {
  const rows = [...initial];
  const put = (next: ReturnType<typeof activity>) => {
    const i = rows.findIndex((r) => r.id === next.id);
    if (i === -1) rows.unshift(next);
    else rows[i] = next;
    return { data: next };
  };
  return { rows, put };
}

const ASSIGNEES = [{ id: 'u1', label: 'Ana' }, { id: 'u2', label: 'Beto' }] as const;

function mount(ui: (hooks: ReturnType<typeof createActivitiesHooks>) => React.ReactElement, routes: Record<string, unknown>) {
  const api = makeApi({ ...TYPES, ...routes });
  const hooks = createActivitiesHooks(api);
  const Wrapper = wrapperFor();
  render(<Wrapper>{ui(hooks)}</Wrapper>);
  return api;
}
const panel = (hooks: ReturnType<typeof createActivitiesHooks>, extra: object = {}) => (
  <ActivitiesPanel hooks={hooks} entityKind="lead" entityId={ENTITY} assigneeOptions={ASSIGNEES} assigneeLabel={(id) => ASSIGNEES.find((a) => a.id === id)?.label ?? null} {...extra} />
);

describe('ActivitiesPanel', () => {
  it('skeleton first, then the rows with type, due date, assignee and the overdue flag', async () => {
    mount((h) => panel(h), { 'GET /api/activities': page([activity({ overdue: true, due_at: '2020-01-01T10:00:00Z', assignee_id: 'u2', type_slug: 'visita' })]) });
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    const row = await screen.findByTestId('activity-row');
    expect(within(row).getByText('Ligar para o cliente')).toBeInTheDocument();
    expect(within(row).getByText('Visita')).toBeInTheDocument();
    expect(within(row).getByText('Atrasada')).toBeInTheDocument();
    expect(within(row).getByText('Responsável: Beto')).toBeInTheDocument();
  });

  it('empty state per filter, and error-with-retry (never a blank panel)', async () => {
    mount((h) => panel(h), { 'GET /api/activities': page([]) });
    expect(await screen.findByText('Nenhuma atividade aberta.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Concluídas' }));
    expect(await screen.findByText('Nenhuma atividade concluída.')).toBeInTheDocument();
    cleanup();
    mount((h) => panel(h), { 'GET /api/activities': () => Promise.reject(new Error('rede caiu')) });
    expect(await screen.findByText(/rede caiu/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument();
  });

  it('the list is asked for THIS card, and the filter changes the status asked for', async () => {
    const api = mount((h) => panel(h), { 'GET /api/activities': page([]) });
    await screen.findByText('Nenhuma atividade aberta.');
    expect(api.get).toHaveBeenCalledWith('/api/activities', expect.objectContaining({ entity_kind: 'lead', entity_id: ENTITY, status: 'open' }));
    await userEvent.click(screen.getByRole('button', { name: 'Todas' }));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/activities', expect.objectContaining({ status: 'all' })));
  });

  it('adds an activity: needs a title (said out loud), posts the type, due, assignee and org unit, and shows the server row', async () => {
    const srv = server([]);
    const api = mount((h) => panel(h, { orgUnitId: 'unit-9', defaultAssigneeId: 'u1' }), {
      'GET /api/activities': () => page(srv.rows),
      'POST /api/activities': () => srv.put(activity({ id: 'new', title: 'Visitar o imóvel', type_slug: 'visita' })),
    });
    await screen.findByText('Nenhuma atividade aberta.');
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar' }));
    expect(screen.getByText('Informe o título da atividade.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
    await userEvent.selectOptions(screen.getByLabelText('Tipo'), 'visita');
    await userEvent.type(screen.getByLabelText('Título'), 'Visitar o imóvel');
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar' }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        '/api/activities',
        expect.objectContaining({ entity_kind: 'lead', entity_id: ENTITY, type_slug: 'visita', title: 'Visitar o imóvel', assignee_id: 'u1', org_unit_id: 'unit-9' }),
      ),
    );
    expect(await screen.findByText('Visitar o imóvel')).toBeInTheDocument();
    expect((screen.getByLabelText('Título') as HTMLInputElement).value).toBe('');
  });

  it('ticking the box completes (the row is drawn done at once); unticking reopens', async () => {
    const srv = server([activity()]);
    const api = mount((h) => panel(h), {
      'GET /api/activities': () => page(srv.rows.filter((r) => !r.cancelled_at)),
      'POST /api/activities/a1/complete': () => srv.put(activity({ done_at: '2026-11-02T10:00:00Z', outcome: 'realizada' })),
      'POST /api/activities/a1/reopen': () => srv.put(activity()),
    });
    const box = await screen.findByRole('checkbox', { name: 'Marcar como concluída' });
    await userEvent.click(box);
    expect(await screen.findByText('Realizada')).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledWith('/api/activities/a1/complete', { outcome: 'realizada' });
    await userEvent.click(await screen.findByRole('checkbox', { name: 'Reabrir atividade' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/activities/a1/reopen', {}));
  });

  it('a refused write is shown in pt-BR next to the list, never swallowed', async () => {
    mount((h) => panel(h), {
      'GET /api/activities': page([activity()]),
      'POST /api/activities/a1/complete': () => Promise.reject(new ApiError(409, 'x', { error: { code: 'atividade_encerrada' } })),
    });
    await userEvent.click(await screen.findByRole('checkbox', { name: 'Marcar como concluída' }));
    expect(await screen.findByText('A atividade já foi encerrada (concluída ou cancelada).')).toBeInTheDocument();
    expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false); // rolled back
  });

  it('reassigns through the picker and cancels', async () => {
    const srv = server([activity()]);
    const api = mount((h) => panel(h), {
      'GET /api/activities': () => page(srv.rows),
      'POST /api/activities/a1/reassign': () => srv.put(activity({ assignee_id: 'u2' })),
      'POST /api/activities/a1/cancel': () => srv.put(activity({ assignee_id: 'u2', cancelled_at: '2026-11-02T10:00:00Z' })),
    });
    const row = await screen.findByTestId('activity-row');
    await userEvent.selectOptions(within(row).getByLabelText('Alterar responsável'), 'u2');
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/activities/a1/reassign', { assignee_id: 'u2' }));
    await userEvent.click(within(row).getByRole('button', { name: 'Cancelar atividade' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/activities/a1/cancel', {}));
    expect(await screen.findByText('Cancelada')).toBeInTheDocument();
  });
});

describe('MyTasksPage', () => {
  it('asks /mine, shows rows with a link to what they are about, and the total', async () => {
    const api = mount(
      (h) => <MyTasksPage hooks={h} entityHref={(k, id) => `/${k}/${id}`} />,
      { 'GET /api/activities/mine': { data: [activity()], pagination: { page: 1, page_size: 25, total: 1 } } },
    );
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    const row = await screen.findByTestId('activity-row');
    expect(within(row).getByRole('link', { name: 'Abrir' })).toHaveAttribute('href', `/lead/${ENTITY}`);
    expect(screen.getByText('1 no total')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/api/activities/mine', expect.objectContaining({ status: 'open', page: 1 }));
  });

  it('the tabs change what is asked (overdue / done) and each has its own empty state', async () => {
    const api = mount((h) => <MyTasksPage hooks={h} />, { 'GET /api/activities/mine': page([]) });
    expect(await screen.findByText('Você não tem atividades abertas.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Atrasadas' }));
    expect(await screen.findByText('Nenhuma atividade atrasada.')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/api/activities/mine', expect.objectContaining({ overdue: true, status: 'open' }));
    await userEvent.click(screen.getByRole('button', { name: 'Concluídas' }));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/activities/mine', expect.objectContaining({ status: 'done' })));
  });

  it('pages through a long list and shows an error with retry when the load fails', async () => {
    const api = mount((h) => <MyTasksPage hooks={h} />, {
      'GET /api/activities/mine': { data: [activity()], pagination: { page: 1, page_size: 25, total: 60 } },
    });
    expect(await screen.findByText('Página 1 de 3')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Próxima' }));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/activities/mine', expect.objectContaining({ page: 2 })));
    cleanup();
    mount((h) => <MyTasksPage hooks={h} />, { 'GET /api/activities/mine': () => Promise.reject(new Error('rede caiu')) });
    expect(await screen.findByText(/rede caiu/)).toBeInTheDocument();
  });
});
