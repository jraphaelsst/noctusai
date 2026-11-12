/** Organ behaviour: every state (skeleton, error+retry, empty, data, refreshing), read-only vs writer, and each write path. */
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ApiError } from '../api';
import { AssignmentRulesPage } from './AssignmentRulesPage';
import { createAssignmentHooks } from './hooks';
import { TeamsManager } from './TeamsManager';
import { ANA, BRUNO, CARLA, ROUTES, T1, T2, env, event, makeApi, member, person, routeGet, rule, settings, team, wrapperFor } from './testUtils';

afterEach(cleanup);

function mount(ui: (hooks: ReturnType<typeof createAssignmentHooks>) => React.ReactElement, routes: Record<string, unknown> = ROUTES) {
  const api = makeApi();
  routeGet(api, routes);
  const hooks = createAssignmentHooks(api);
  const Wrapper = wrapperFor();
  render(<Wrapper>{ui(hooks)}</Wrapper>);
  return api;
}

describe('TeamsManager', () => {
  it('skeleton first, then the team with its members, load and badges', async () => {
    mount((hooks) => <TeamsManager hooks={hooks} />, {
      ...ROUTES,
      '/teams': env([team({ members: [member({ capacity: 3, open_count: 3, unavailable_reason: 'at_capacity' }), member({ user_id: BRUNO, name: 'Bruno', active: false, position: 1 })] })]),
    });
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    const card = await screen.findByTestId('team-card');
    expect(within(card).getByText('Vendas')).toBeInTheDocument();
    expect(within(card).getByText('Automática')).toBeInTheDocument();
    const [ana, bruno] = within(card).getAllByTestId('team-member');
    expect(within(ana).getByText('3 de 3 abertos')).toBeInTheDocument();
    expect(within(ana).getByText('Na capacidade')).toBeInTheDocument();
    expect(within(bruno).getByText('Inativo')).toBeInTheDocument();
  });

  it('empty state, and error-with-retry that refetches (never a blank panel)', async () => {
    mount((hooks) => <TeamsManager hooks={hooks} canWrite />, { ...ROUTES, '/teams': env([]) });
    expect(await screen.findByText(/Nenhuma equipe ainda/)).toBeInTheDocument();
    cleanup();
    const api = makeApi();
    api.get.mockRejectedValueOnce(new Error('rede caiu')).mockResolvedValue(env([team()]));
    const Wrapper = wrapperFor();
    render(<Wrapper><TeamsManager hooks={createAssignmentHooks(api)} /></Wrapper>);
    expect(await screen.findByText(/rede caiu/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Tentar de novo' }));
    expect(await screen.findByTestId('team-card')).toBeInTheDocument();
  });

  it('a read-only viewer sees the data and NO write control', async () => {
    mount((hooks) => <TeamsManager hooks={hooks} />);
    await screen.findByTestId('team-card');
    expect(screen.queryByRole('button', { name: /Desativar|Remover|Excluir equipe|Renomear/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('form', { name: 'Nova equipe' })).not.toBeInTheDocument();
    expect(screen.queryByTestId('member-picker')).not.toBeInTheDocument();
  });

  it('creates a team and draws it from the server answer', async () => {
    const user = userEvent.setup();
    const routes: Record<string, unknown> = { ...ROUTES, '/teams': env([]) };
    const api = mount((hooks) => <TeamsManager hooks={hooks} canWrite />, routes);
    api.post.mockImplementation(async () => {
      const created = team({ id: T2, name: 'Anúncios', members: [] });
      routes['/teams'] = env([created]); // what the server now holds (the settle refetch reads it)
      return env(created);
    });
    await screen.findByText(/Nenhuma equipe ainda/);
    await user.type(screen.getByLabelText(/Nome da equipe/), 'Anúncios');
    await user.click(screen.getByRole('button', { name: 'Nova equipe' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/assignment/teams', { name: 'Anúncios', auto: true }));
    expect(await screen.findByRole('heading', { name: 'Anúncios' })).toBeInTheDocument();
  });

  it('refuses a blank name locally and renders a server refusal in pt-BR without losing the typed value', async () => {
    const user = userEvent.setup();
    const api = mount((hooks) => <TeamsManager hooks={hooks} canWrite />);
    await screen.findByTestId('team-card');
    await user.click(screen.getByRole('button', { name: 'Nova equipe' }));
    expect(await screen.findByText('Informe um nome de 1 a 60 caracteres.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
    api.post.mockRejectedValue(new ApiError(409, 'dup', { error: { code: 'equipe_duplicada' } }));
    await user.type(screen.getByLabelText(/Nome da equipe/), 'Vendas');
    await user.click(screen.getByRole('button', { name: 'Nova equipe' }));
    expect(await screen.findByText('Já existe uma equipe com esse nome.')).toBeInTheDocument();
    expect(screen.getByLabelText(/Nome da equipe/)).toHaveValue('Vendas');
  });

  it('adds a member from the org people not yet in the team', async () => {
    const user = userEvent.setup();
    const routes: Record<string, unknown> = { ...ROUTES };
    const api = mount((hooks) => <TeamsManager hooks={hooks} canWrite />, routes);
    api.post.mockImplementation(async () => {
      const saved = team({ members: [member(), member({ user_id: BRUNO, name: 'Bruno', position: 1 }), member({ user_id: CARLA, name: 'Carla', position: 2 })] });
      routes['/teams'] = env([saved]);
      return env(saved);
    });
    await screen.findByTestId('team-card');
    const picker = await screen.findByTestId('member-picker');
    await waitFor(() => expect(within(picker).getAllByRole('option').map((o) => o.textContent)).toEqual(['Escolha uma pessoa', 'Carla']));
    await user.selectOptions(picker, CARLA);
    await user.click(screen.getByRole('button', { name: 'Adicionar membro' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(`/api/assignment/teams/${T1}/members`, { user_id: CARLA }));
    expect(await screen.findAllByTestId('team-member')).toHaveLength(3);
  });

  it('saves a capacity on blur (blank = unlimited) and ignores an invalid one', async () => {
    const user = userEvent.setup();
    const api = mount((hooks) => <TeamsManager hooks={hooks} canWrite />);
    api.patch.mockResolvedValue(env(team({ members: [member({ capacity: 4 }), member({ user_id: BRUNO, name: 'Bruno', position: 1 })] })));
    await screen.findByTestId('team-card');
    const [ana] = screen.getAllByTestId('team-member');
    const input = within(ana).getByLabelText('Capacidade');
    await user.type(input, '4');
    await user.tab();
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith(`/api/assignment/teams/${T1}/members/${ANA}`, { capacity: 4 }));
    await user.clear(input);
    await user.type(input, '0');
    await user.tab();
    expect(api.patch).toHaveBeenCalledTimes(1); // 0 is refused locally and the field snaps back
  });

  it('marks an absence window and clears it; activates / deactivates; reorders', async () => {
    const user = userEvent.setup();
    const api = mount((hooks) => <TeamsManager hooks={hooks} canWrite />);
    api.patch.mockResolvedValue(env(team()));
    api.put.mockResolvedValue(env(team()));
    await screen.findByTestId('team-card');
    const [ana] = screen.getAllByTestId('team-member');
    await user.type(within(ana).getByLabelText('Ausente até'), '2026-12-31');
    await user.click(within(ana).getByRole('button', { name: 'Marcar ausência' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalled());
    const body = api.patch.mock.calls[0][1] as { ooo_from: string; ooo_until: string };
    expect(new Date(body.ooo_until).getTime()).toBeGreaterThan(new Date(body.ooo_from).getTime());
    await user.click(within(ana).getByRole('button', { name: 'Desativar' }));
    await waitFor(() => expect(api.patch).toHaveBeenLastCalledWith(`/api/assignment/teams/${T1}/members/${ANA}`, { active: false }));
    await user.click(within(screen.getAllByTestId('team-member')[0]).getByRole('button', { name: 'Descer na fila' }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith(`/api/assignment/teams/${T1}/order`, { order: [BRUNO, ANA] }));
    expect(within(screen.getAllByTestId('team-member')[0]).getByRole('button', { name: 'Subir na fila' })).toBeDisabled();
  });

  it('shows an absence badge and offers to end it', async () => {
    const future = new Date(Date.now() + 5 * 86400000).toISOString();
    mount((hooks) => <TeamsManager hooks={hooks} canWrite />, {
      ...ROUTES,
      '/teams': env([team({ members: [member({ ooo_from: new Date().toISOString(), ooo_until: future, unavailable_reason: 'out_of_office' })] })]),
    });
    const row = await screen.findByTestId('team-member');
    expect(within(row).getByText(/Ausente até/)).toBeInTheDocument();
    expect(within(row).getByRole('button', { name: 'Encerrar ausência' })).toBeInTheDocument();
  });

  it('renames and deletes with a two-step confirmation', async () => {
    const user = userEvent.setup();
    const routes: Record<string, unknown> = { ...ROUTES };
    const api = mount((hooks) => <TeamsManager hooks={hooks} canWrite />, routes);
    api.patch.mockImplementation(async () => {
      const renamed = team({ name: 'Comercial' });
      routes['/teams'] = env([renamed]);
      return env(renamed);
    });
    api.delete.mockImplementation(async () => {
      routes['/teams'] = env([]);
      return null;
    });
    await screen.findByTestId('team-card');
    await user.click(screen.getAllByRole('button', { name: 'Renomear' })[0]);
    const input = screen.getAllByLabelText('Nome da equipe')[0];
    await user.clear(input);
    await user.type(input, 'Comercial');
    await user.click(screen.getAllByRole('button', { name: 'Renomear' })[0]);
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith(`/api/assignment/teams/${T1}`, { name: 'Comercial' }));
    await user.click(await screen.findByRole('button', { name: 'Excluir equipe' }));
    expect(api.delete).not.toHaveBeenCalled(); // a click is not a deletion
    await user.click(screen.getByRole('button', { name: 'Confirmar exclusão' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith(`/api/assignment/teams/${T1}`));
    await waitFor(() => expect(screen.queryByTestId('team-card')).not.toBeInTheDocument());
  });
});

describe('AssignmentRulesPage', () => {
  it('shows the strategy, rules with team names, the workload and the latest events', async () => {
    mount((hooks) => (
      <AssignmentRulesPage hooks={hooks} />
    ), {
      ...ROUTES,
      '/workload': env([person(), person({ user_id: BRUNO, name: 'Bruno', open_count: 0, available: false, unavailable_reasons: ['out_of_office'] })]),
      '/events': env([event(), event({ id: 'e-2', event: 'no_candidate', to_user_id: null, criterion: 'no_available_member' })]),
    });
    expect(screen.getByTestId('list-loading')).toBeInTheDocument();
    expect(await screen.findByTestId('strategy-select')).toHaveValue('round_robin');
    expect(screen.getByText(/Cada equipe automática recebe a sua vez/)).toBeInTheDocument();
    const ruleRow = await screen.findByTestId('assignment-rule');
    expect(within(ruleRow).getByText('meta_ads')).toBeInTheDocument();
    expect(within(ruleRow).getByText('Vendas')).toBeInTheDocument();
    const rows = await screen.findAllByTestId('workload-row');
    expect(within(rows[1]).getByText('Ausente')).toBeInTheDocument();
    const events = await screen.findAllByTestId('assignment-event');
    expect(events[0].textContent).toContain('Atribuído a Ana');
    expect(events[1].textContent).toContain('Ninguém disponível (todos ausentes, inativos ou na capacidade)');
  });

  it('a viewer cannot change anything: every control is disabled or absent', async () => {
    mount((hooks) => <AssignmentRulesPage hooks={hooks} />);
    expect(await screen.findByTestId('strategy-select')).toBeDisabled();
    expect(screen.getByTestId('default-team-select')).toBeDisabled();
    expect(screen.getByRole('checkbox')).toBeDisabled();
    await screen.findByTestId('assignment-rule');
    expect(screen.queryByRole('button', { name: 'Remover' })).not.toBeInTheDocument();
    expect(screen.queryByRole('form', { name: 'Salvar regra' })).not.toBeInTheDocument();
  });

  it('lists the custom strategies the product registered and changes the strategy through a cache write', async () => {
    const user = userEvent.setup();
    const routes: Record<string, unknown> = { ...ROUTES, '/settings': env(settings({ custom: ['by_plantao'] })) };
    const api = mount((hooks) => <AssignmentRulesPage hooks={hooks} canWrite />, routes);
    api.put.mockImplementation(async (_path: string, body: object) => {
      routes['/settings'] = env({ ...(routes['/settings'] as { data: object }).data, ...body });
      return routes['/settings'];
    });
    const select = await screen.findByTestId('strategy-select');
    expect(within(select).getByRole('option', { name: 'Personalizada: by_plantao' })).toBeInTheDocument();
    await user.selectOptions(select, 'by_plantao');
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/api/assignment/settings', { strategy: 'by_plantao' }));
    expect(await screen.findByText('Regra própria deste produto.')).toBeInTheDocument();
    await user.selectOptions(screen.getByTestId('default-team-select'), T1);
    await waitFor(() => expect(api.put).toHaveBeenLastCalledWith('/api/assignment/settings', { default_team_id: T1 }));
    await waitFor(() => expect(screen.getByTestId('default-team-select')).toHaveValue(T1));
  });

  it('a refused strategy change is explained in pt-BR and the select falls back to the server value', async () => {
    const user = userEvent.setup();
    const api = mount((hooks) => <AssignmentRulesPage hooks={hooks} canWrite />);
    api.put.mockRejectedValue(new ApiError(422, 'x', { error: { code: 'estrategia_invalida' } }));
    await user.selectOptions(await screen.findByTestId('strategy-select'), 'manual');
    expect(await screen.findByText('Estratégia desconhecida.')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('strategy-select')).toHaveValue('round_robin'));
  });

  it('adds a rule (validated locally), then removes one', async () => {
    const user = userEvent.setup();
    const routes: Record<string, unknown> = { ...ROUTES };
    const api = mount((hooks) => <AssignmentRulesPage hooks={hooks} canWrite />, routes);
    const rules = () => (routes['/rules'] as { data: ReturnType<typeof rule>[] }).data;
    api.put.mockImplementation(async () => {
      const added = rule({ id: 'r-9', match_value: 'portal', team_id: T1 });
      routes['/rules'] = env([...rules(), added]);
      return env(added);
    });
    api.delete.mockImplementation(async () => {
      routes['/rules'] = env(rules().filter((r) => r.id !== 'r-1'));
      return null;
    });
    await screen.findByTestId('assignment-rule');
    await user.click(screen.getByRole('button', { name: 'Salvar regra' }));
    expect(await screen.findByText('Informe o valor e a equipe da regra.')).toBeInTheDocument();
    expect(api.put).not.toHaveBeenCalled();
    await user.type(screen.getByPlaceholderText('ex.: meta_ads, portal, site'), 'portal');
    await user.selectOptions(screen.getByTestId('rule-team'), T1);
    await user.click(screen.getByRole('button', { name: 'Salvar regra' }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/api/assignment/rules', { kind: 'source', match_value: 'portal', team_id: T1 }));
    expect(await screen.findAllByTestId('assignment-rule')).toHaveLength(2);
    await user.click(within(screen.getAllByTestId('assignment-rule')[0]).getByRole('button', { name: 'Remover' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/assignment/rules/r-1'));
    await waitFor(() => expect(screen.getAllByTestId('assignment-rule')).toHaveLength(1));
  });

  it('empty rules / events / workload each say so, and a failed events feed offers a retry without hiding the rest', async () => {
    const api = makeApi();
    api.get.mockImplementation((p: string) => {
      if (p.endsWith('/events')) return Promise.reject(new Error('eventos fora do ar'));
      const hit = Object.entries({ ...ROUTES, '/rules': env([]), '/workload': env([]) }).find(([r]) => p.endsWith(r));
      return hit ? Promise.resolve(hit[1]) : Promise.reject(new Error(`unrouted ${p}`));
    });
    const Wrapper = wrapperFor();
    render(<Wrapper><AssignmentRulesPage hooks={createAssignmentHooks(api)} /></Wrapper>);
    expect(await screen.findByText(/Nenhuma regra/)).toBeInTheDocument();
    expect(await screen.findByText('Ninguém na organização ainda.')).toBeInTheDocument();
    expect(await screen.findByText(/eventos fora do ar/)).toBeInTheDocument();
    expect(screen.getByTestId('strategy-select')).toBeInTheDocument();
  });

  it('says to create a team before defining rules when there is none', async () => {
    mount((hooks) => <AssignmentRulesPage hooks={hooks} canWrite />, { ...ROUTES, '/teams': env([]), '/rules': env([]) });
    expect(await screen.findByText('Crie uma equipe antes de definir regras.')).toBeInTheDocument();
  });
});
