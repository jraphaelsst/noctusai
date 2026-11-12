/** Hook factory: two-signal loading, cache writes (the server's answer lands in the cache), refusals, the verbs. */
import { afterEach, describe, expect, it } from 'vitest';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { ApiError } from '../api';
import { assignmentErrorMessage, assignmentKeys, compareAssignmentTeams, createAssignmentHooks } from './hooks';
import type { AssignmentRule, AssignmentSettings, AssignmentTeam, SubjectAssignment } from './types';
import { ANA, BRUNO, T1, T2, env, makeApi, makeClient, member, rule, settings, team, wrapperFor } from './testUtils';

afterEach(cleanup);

const seeded = (client = makeClient()) => {
  client.setQueryData(assignmentKeys.teams, [team(), team({ id: T2, name: 'Zeta', members: [] })]);
  return client;
};

describe('two-signal loading', () => {
  it('showSkeleton on first load only; isRefreshing on a refetch over data', async () => {
    let resolve!: (v: unknown) => void;
    const api = makeApi();
    api.get.mockImplementationOnce(() => new Promise((r) => (resolve = r)));
    const hooks = createAssignmentHooks(api);
    const { result } = renderHook(() => hooks.useTeams(), { wrapper: wrapperFor() });
    expect(result.current.showSkeleton).toBe(true);
    expect(result.current.isRefreshing).toBe(false);
    await act(async () => resolve(env([team()])));
    await waitFor(() => expect(result.current.data).toHaveLength(1));
    expect(result.current.showSkeleton).toBe(false);

    let resolve2!: (v: unknown) => void;
    api.get.mockImplementationOnce(() => new Promise((r) => (resolve2 = r)));
    act(() => void result.current.refetch());
    await waitFor(() => expect(result.current.isRefreshing).toBe(true));
    expect(result.current.showSkeleton).toBe(false);
    expect(result.current.data).toHaveLength(1);
    await act(async () => resolve2(env([team(), team({ id: T2, name: 'Zeta' })])));
    await waitFor(() => expect(result.current.isRefreshing).toBe(false));
  });

  it('a subject with no owner (404) is an answer, any other failure is an error', async () => {
    const api = makeApi();
    api.get.mockRejectedValueOnce(new ApiError(404, 'não encontrado'));
    const hooks = createAssignmentHooks(api);
    const { result } = renderHook(() => hooks.useSubjectAssignment('card', 'c-1'), { wrapper: wrapperFor() });
    await waitFor(() => expect(result.current.data).toBeNull());
    expect(result.current.isError).toBe(false);
    expect(api.get).toHaveBeenCalledWith('/api/assignment/assignments/card/c-1');

    api.get.mockRejectedValueOnce(new ApiError(500, 'boom'));
    const { result: r2 } = renderHook(() => hooks.useSubjectAssignment('card', 'c-2'), { wrapper: wrapperFor() });
    await waitFor(() => expect(r2.current.isError).toBe(true));
  });

  it('a subject query stays disabled without a subject (no skeleton, no call)', () => {
    const api = makeApi();
    const { result } = renderHook(() => createAssignmentHooks(api).useSubjectAssignment(null, null), { wrapper: wrapperFor() });
    expect(result.current.showSkeleton).toBe(false);
    expect(api.get).not.toHaveBeenCalled();
  });
});

describe('team writes put the server answer into the cached list', () => {
  it('create inserts the new team where the server sorts it, before any refetch', async () => {
    const api = makeApi();
    const created = team({ id: 't-new', name: 'Anúncios', members: [] });
    api.post.mockResolvedValue(env(created));
    api.get.mockReturnValue(new Promise(() => undefined)); // the background settle never answers: the cache must already be right
    const client = seeded();
    const { result } = renderHook(() => createAssignmentHooks(api).useTeamMutations(), { wrapper: wrapperFor(client) });
    await act(async () => void (await result.current.create.mutateAsync({ name: 'Anúncios' })));
    expect(api.post).toHaveBeenCalledWith('/api/assignment/teams', { name: 'Anúncios' });
    expect(client.getQueryData<AssignmentTeam[]>(assignmentKeys.teams)!.map((t) => t.name)).toEqual(['Anúncios', 'Vendas', 'Zeta']);
  });

  it('a rename is drawn on the click and rolled back when the server refuses', async () => {
    const api = makeApi();
    let reject!: (e: unknown) => void;
    api.patch.mockImplementation(() => new Promise((_, rej) => (reject = rej)));
    api.get.mockReturnValue(new Promise(() => undefined));
    const client = seeded();
    const { result } = renderHook(() => createAssignmentHooks(api).useTeamMutations(), { wrapper: wrapperFor(client) });
    let done!: Promise<unknown>;
    act(() => {
      done = result.current.update.mutateAsync({ id: T1, name: 'Comercial' }).catch((e: unknown) => e);
    });
    await waitFor(() => expect(client.getQueryData<AssignmentTeam[]>(assignmentKeys.teams)![0].name).toBe('Comercial'));
    await act(async () => {
      reject(new ApiError(409, 'Já existe uma equipe com esse nome.', { error: { code: 'equipe_duplicada' } }));
      await done;
    });
    expect(client.getQueryData<AssignmentTeam[]>(assignmentKeys.teams)![0].name).toBe('Vendas');
  });

  it('removing a team is drawn on the click and refreshes what the server cascades', async () => {
    const api = makeApi();
    api.delete.mockResolvedValue(null); // 204
    api.get.mockReturnValue(new Promise(() => undefined));
    const client = seeded();
    client.setQueryData(assignmentKeys.settings, settings());
    const { result } = renderHook(() => createAssignmentHooks(api).useTeamMutations(), { wrapper: wrapperFor(client) });
    await act(async () => void (await result.current.remove.mutateAsync({ id: T1 })));
    expect(client.getQueryData<AssignmentTeam[]>(assignmentKeys.teams)!.map((t) => t.id)).toEqual([T2]);
    expect(client.getQueryState(assignmentKeys.settings)?.isInvalidated).toBe(true); // a default team may have reset
  });

  it('a member edit is drawn on the click, then replaced by the server team', async () => {
    const api = makeApi();
    const saved = team({ members: [member({ capacity: 5 }), member({ user_id: BRUNO, name: 'Bruno', position: 1 })] });
    api.patch.mockResolvedValue(env(saved));
    api.get.mockReturnValue(new Promise(() => undefined));
    const client = seeded();
    const { result } = renderHook(() => createAssignmentHooks(api).useTeamMutations(), { wrapper: wrapperFor(client) });
    await act(async () => void (await result.current.updateMember.mutateAsync({ teamId: T1, userId: ANA, capacity: 5 })));
    expect(api.patch).toHaveBeenCalledWith(`/api/assignment/teams/${T1}/members/${ANA}`, { capacity: 5 });
    expect(client.getQueryData<AssignmentTeam[]>(assignmentKeys.teams)![0].members[0].capacity).toBe(5);
  });

  it('reordering is drawn immediately with the new positions', async () => {
    const api = makeApi();
    api.put.mockReturnValue(new Promise(() => undefined)); // pending: only the optimistic draw is on screen
    const client = seeded();
    const { result } = renderHook(() => createAssignmentHooks(api).useTeamMutations(), { wrapper: wrapperFor(client) });
    act(() => void result.current.order.mutate({ teamId: T1, order: [BRUNO, ANA] }));
    await waitFor(() => expect(client.getQueryData<AssignmentTeam[]>(assignmentKeys.teams)![0].members.map((m) => [m.user_id, m.position])).toEqual([[BRUNO, 0], [ANA, 1]]));
    expect(api.put).toHaveBeenCalledWith(`/api/assignment/teams/${T1}/order`, { order: [BRUNO, ANA] });
  });

  it('adding a member and removing one write the team and the workload stays derived', async () => {
    const api = makeApi();
    const saved = team({ id: T2, name: 'Zeta', members: [member()] });
    api.post.mockResolvedValue(env(saved));
    api.delete.mockResolvedValue(null);
    api.get.mockReturnValue(new Promise(() => undefined));
    const client = seeded();
    client.setQueryData(assignmentKeys.workload, []);
    const { result } = renderHook(() => createAssignmentHooks(api).useTeamMutations(), { wrapper: wrapperFor(client) });
    await act(async () => void (await result.current.addMember.mutateAsync({ teamId: T2, user_id: ANA })));
    expect(client.getQueryData<AssignmentTeam[]>(assignmentKeys.teams)!.find((t) => t.id === T2)!.members).toHaveLength(1);
    await act(async () => void (await result.current.removeMember.mutateAsync({ teamId: T2, userId: ANA })));
    expect(client.getQueryData<AssignmentTeam[]>(assignmentKeys.teams)!.find((t) => t.id === T2)!.members).toHaveLength(0);
    expect(client.getQueryState(assignmentKeys.workload)?.isInvalidated).toBe(true);
  });
});

describe('settings and rules', () => {
  it('a settings change is drawn at once and then replaced by the server answer', async () => {
    const api = makeApi();
    let resolve!: (v: unknown) => void;
    api.put.mockImplementation(() => new Promise((r) => (resolve = r)));
    api.get.mockReturnValue(new Promise(() => undefined));
    const client = makeClient();
    client.setQueryData(assignmentKeys.settings, settings());
    const { result } = renderHook(() => createAssignmentHooks(api).useSettingsMutation(), { wrapper: wrapperFor(client) });
    act(() => void result.current.mutate({ strategy: 'manual' }));
    await waitFor(() => expect(client.getQueryData<AssignmentSettings>(assignmentKeys.settings)!.strategy).toBe('manual'));
    await act(async () => resolve(env(settings({ strategy: 'manual', keep_last: false }))));
    await waitFor(() => expect(client.getQueryData<AssignmentSettings>(assignmentKeys.settings)!.keep_last).toBe(false));
  });

  it('a rule upsert replaces the row with the same id and keeps the server order; a removal is drawn at once', async () => {
    const api = makeApi();
    api.put.mockResolvedValue(env(rule({ team_id: T2 })));
    api.delete.mockResolvedValue(null);
    api.get.mockReturnValue(new Promise(() => undefined));
    const client = makeClient();
    client.setQueryData(assignmentKeys.rules, [rule(), rule({ id: 'r-2', kind: 'unit', match_value: 'u9' })]);
    const { result } = renderHook(() => createAssignmentHooks(api).useRuleMutations(), { wrapper: wrapperFor(client) });
    await act(async () => void (await result.current.put.mutateAsync({ kind: 'source', match_value: 'meta_ads', team_id: T2 })));
    const rules = client.getQueryData<AssignmentRule[]>(assignmentKeys.rules)!;
    expect(rules.map((r) => [r.id, r.team_id])).toEqual([['r-1', T2], ['r-2', T1]]);
    await act(async () => void (await result.current.remove.mutateAsync({ id: 'r-2' })));
    expect(client.getQueryData<AssignmentRule[]>(assignmentKeys.rules)!.map((r) => r.id)).toEqual(['r-1']);
  });
});

describe('the verbs a host calls', () => {
  const owner = (over: Partial<SubjectAssignment> = {}): SubjectAssignment => ({
    id: 'a-1', org_id: 'o', subject_kind: 'card', subject_id: 'c-1', user_id: ANA, team_id: T1, org_unit_id: null, strategy: 'round_robin',
    criterion: 'round_robin', assigned_at: '', closed_at: null, ...over,
  });

  it('assign writes the new owner into the subject cache and refreshes the derived views', async () => {
    const api = makeApi();
    api.post.mockResolvedValue(env({ assigned: true, user_id: BRUNO, team_id: T1, criterion: 'keep_last', strategy: 'round_robin', changed: true, event: 'reassigned' }));
    api.get.mockReturnValue(new Promise(() => undefined));
    const client = makeClient();
    client.setQueryData(assignmentKeys.subject('card', 'c-1'), owner());
    client.setQueryData(assignmentKeys.workload, []);
    const { result } = renderHook(() => createAssignmentHooks(api).useAssignmentActions(), { wrapper: wrapperFor(client) });
    await act(async () => void (await result.current.assign.mutateAsync({ subject_kind: 'card', subject_id: 'c-1' })));
    expect(client.getQueryData<SubjectAssignment>(assignmentKeys.subject('card', 'c-1'))!.user_id).toBe(BRUNO);
    expect(client.getQueryState(assignmentKeys.workload)?.isInvalidated).toBe(true);
  });

  it('a no-candidate assign leaves the cached owner alone (it is an outcome, not a write)', async () => {
    const api = makeApi();
    api.post.mockResolvedValue(env({ assigned: false, reason: 'no_team', strategy: 'round_robin' }));
    api.get.mockReturnValue(new Promise(() => undefined));
    const client = makeClient();
    client.setQueryData(assignmentKeys.subject('card', 'c-1'), owner());
    const { result } = renderHook(() => createAssignmentHooks(api).useAssignmentActions(), { wrapper: wrapperFor(client) });
    await act(async () => void (await result.current.assign.mutateAsync({ subject_kind: 'card', subject_id: 'c-1' })));
    expect(client.getQueryData<SubjectAssignment>(assignmentKeys.subject('card', 'c-1'))!.user_id).toBe(ANA);
  });

  it('a refused reassign rolls the optimistic owner back', async () => {
    const api = makeApi();
    api.post.mockRejectedValue(new ApiError(403, 'sem permissão', { error: { code: 'sem_permissao' } }));
    api.get.mockReturnValue(new Promise(() => undefined));
    const client = makeClient();
    client.setQueryData(assignmentKeys.subject('card', 'c-1'), owner());
    const { result } = renderHook(() => createAssignmentHooks(api).useAssignmentActions(), { wrapper: wrapperFor(client) });
    await act(async () => {
      await result.current.reassign.mutateAsync({ subject_kind: 'card', subject_id: 'c-1', to_user_id: BRUNO }).catch(() => undefined);
    });
    expect(client.getQueryData<SubjectAssignment>(assignmentKeys.subject('card', 'c-1'))!.user_id).toBe(ANA);
  });

  it('unassign clears the cached owner; close stamps closed_at', async () => {
    const api = makeApi();
    api.post.mockResolvedValue(env({ changed: true, event: 'unassigned' }));
    api.get.mockReturnValue(new Promise(() => undefined));
    const client = makeClient();
    client.setQueryData(assignmentKeys.subject('card', 'c-1'), owner());
    client.setQueryData(assignmentKeys.subject('card', 'c-2'), owner({ subject_id: 'c-2' }));
    const { result } = renderHook(() => createAssignmentHooks(api).useAssignmentActions(), { wrapper: wrapperFor(client) });
    await act(async () => void (await result.current.unassign.mutateAsync({ subject_kind: 'card', subject_id: 'c-1' })));
    expect(client.getQueryData(assignmentKeys.subject('card', 'c-1'))).toBeNull();
    api.post.mockResolvedValue(env({ changed: true, event: 'closed' }));
    await act(async () => void (await result.current.close.mutateAsync({ subject_kind: 'card', subject_id: 'c-2' })));
    expect(client.getQueryData<SubjectAssignment>(assignmentKeys.subject('card', 'c-2'))!.closed_at).not.toBeNull();
  });
});

describe('error copy', () => {
  it('maps the stable codes to pt-BR and falls back to the server message', () => {
    expect(assignmentErrorMessage(new ApiError(409, 'x', { error: { code: 'equipe_duplicada' } }))).toBe('Já existe uma equipe com esse nome.');
    expect(assignmentErrorMessage(new ApiError(500, 'falha do servidor'))).toBe('[500] falha do servidor');
    expect(assignmentErrorMessage(new Error('rede caiu'))).toBe('rede caiu');
  });

  it('team order in the cache is the server order (case-insensitive name)', () => {
    const names = ['zeta', 'Ana', 'bruno'].map((name, i) => team({ id: String(i), name }));
    expect([...names].sort(compareAssignmentTeams).map((t) => t.name)).toEqual(['Ana', 'bruno', 'zeta']);
  });
});
