/**
 * Cache-write contract of the seed organ hook factories — every main create / update / delete puts
 * what it knows into the cache. Each case asserts the cache WHILE the request is still in flight (a
 * deferred promise) or right after the answer with every refetch still pending: the screen must not
 * wait for write + refetch (KB § PATTERNS/frontend/mutation-cache-writes.md).
 *
 * The api is an injected double (the factories' DI seam); no cached read is mounted, so settle only
 * marks entries stale — what these tests read is exactly what the write placed.
 */
import * as React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';

import { createPartiesHooks, partiesKeys } from './parties/hooks';
import { createContractsHooks, contractsKeys } from './contracts/hooks';
import { createFinanceHooks, financeKeys } from './finance/hooks';
import { createFinanceReminderHooks, reminderKeys } from './finance/reminderHooks';
import { createCardHubHooks } from './components/card-hub/createCardHubHooks';
import { createTeamHooks, TEAM_QUERY_KEYS } from './components/team/createTeamHooks';
import { createApiKeysHooks } from './components/api-keys/createApiKeysHooks';
import { createPipelineHooks } from './components/pipeline/createPipelineHooks';
import { createWhatsAppConnectionsHooks } from './whatsapp';
import { createNotificationHooks } from './notifications';
import { createLLMHooks } from './llm';
import { makeRoutedApi } from './organ-kit/testing';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } }));

afterEach(cleanup);

function deferred<T = unknown>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function harness() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  return { qc, wrapper };
}

const page = (rows: unknown[]) => ({ data: rows, pagination: { page: 1, page_size: 20, total: rows.length } });

describe('parties', () => {
  it('update commits the server row into the list page and the detail; delete leaves the list on click', async () => {
    const { qc, wrapper } = harness();
    const d = deferred();
    const api: any = makeRoutedApi({
      'PATCH /api/parties/p1': () => d.promise,
      'DELETE /api/parties/p2': () => d.promise,
    });
    const hooks = createPartiesHooks(api);
    qc.setQueryData(partiesKeys.list({}), page([{ id: 'p1', name: 'Ana' }, { id: 'p2', name: 'Bia' }]));
    qc.setQueryData(partiesKeys.detail('p1'), { id: 'p1', name: 'Ana' });

    const upd = renderHook(() => hooks.useUpdateParty(), { wrapper });
    act(() => upd.result.current.mutate({ id: 'p1', name: 'Ana Maria' } as any));
    await act(async () => d.resolve({ data: { id: 'p1', name: 'Ana Maria' } }));
    await waitFor(() => expect(upd.result.current.isSuccess).toBe(true));
    expect((qc.getQueryData(partiesKeys.list({})) as any).data[0].name).toBe('Ana Maria');
    expect((qc.getQueryData(partiesKeys.detail('p1')) as any).name).toBe('Ana Maria');

    const d2 = deferred();
    api.route('DELETE /api/parties/p2', () => d2.promise);
    const del = renderHook(() => hooks.useDeleteParty(), { wrapper });
    act(() => del.result.current.mutate('p2'));
    await waitFor(() => expect((qc.getQueryData(partiesKeys.list({})) as any).data).toHaveLength(1)); // in flight
    expect((qc.getQueryData(partiesKeys.list({})) as any).pagination.total).toBe(1);
    await act(async () => d2.reject(new Error('409')));
    await waitFor(() => expect((qc.getQueryData(partiesKeys.list({})) as any).data).toHaveLength(2)); // rolled back
  });

  it('create seeds the new detail from the answer', async () => {
    const { qc, wrapper } = harness();
    const api: any = makeRoutedApi({ 'POST /api/parties': { data: { id: 'p9', name: 'Novo' } } });
    const { result } = renderHook(() => createPartiesHooks(api).useCreateParty(), { wrapper });
    await act(async () => { await result.current.mutateAsync({ name: 'Novo' } as any); });
    expect(qc.getQueryData(partiesKeys.detail('p9'))).toEqual({ id: 'p9', name: 'Novo' });
  });
});

describe('contracts', () => {
  it('a lifecycle action commits the refreshed contract into the detail and the list page; delete is optimistic', async () => {
    const { qc, wrapper } = harness();
    const d = deferred();
    const api: any = makeRoutedApi({ 'POST /api/contracts/c1/activate': () => d.promise, 'DELETE /api/contracts/c2': () => d.promise });
    const hooks = createContractsHooks(api);
    qc.setQueryData(contractsKeys.list({}), page([{ id: 'c1', status: 'draft' }, { id: 'c2', status: 'draft' }]));
    qc.setQueryData(contractsKeys.detail('c1'), { id: 'c1', status: 'draft', title: 'T' });

    const act1 = renderHook(() => hooks.useActivateContract(), { wrapper });
    act(() => act1.result.current.mutate({ id: 'c1' }));
    await act(async () => d.resolve({ data: { id: 'c1', status: 'active', title: 'T' } }));
    await waitFor(() => expect(act1.result.current.isSuccess).toBe(true));
    expect((qc.getQueryData(contractsKeys.detail('c1')) as any).status).toBe('active');
    expect((qc.getQueryData(contractsKeys.list({})) as any).data[0].status).toBe('active');

    const del = renderHook(() => hooks.useDeleteContract(), { wrapper });
    act(() => del.result.current.mutate('c2'));
    await waitFor(() => expect((qc.getQueryData(contractsKeys.list({})) as any).data.map((r: any) => r.id)).toEqual(['c1']));
  });
});

describe('finance', () => {
  it('settle writes the entry into the list and the settlement into the detail; remove leaves on click', async () => {
    const { qc, wrapper } = harness();
    const d = deferred();
    const api: any = makeRoutedApi({ 'POST /api/finance/entries/e1/settlements': () => d.promise, 'DELETE /api/finance/entries/e2': () => d.promise });
    const hooks = createFinanceHooks(api);
    const listKey = [...financeKeys.entries, 'list', {}];
    qc.setQueryData(listKey, page([{ id: 'e1', status: 'open' }, { id: 'e2', status: 'open' }]));
    qc.setQueryData(financeKeys.entry('e1'), { id: 'e1', status: 'open', settlements: [] });

    const { result } = renderHook(() => hooks.useEntryMutations(), { wrapper });
    act(() => result.current.settle.mutate({ id: 'e1', account_id: 'a', amount_cents: 100 } as any));
    await act(async () => d.resolve({ data: { settlement: { id: 's1', entry_id: 'e1' }, entry: { id: 'e1', status: 'paid' }, replayed: false } }));
    await waitFor(() => expect(result.current.settle.isSuccess).toBe(true));
    expect((qc.getQueryData(listKey) as any).data[0].status).toBe('paid');
    expect((qc.getQueryData(financeKeys.entry('e1')) as any)).toMatchObject({ status: 'paid', settlements: [{ id: 's1' }] });

    act(() => result.current.remove.mutate('e2'));
    await waitFor(() => expect((qc.getQueryData(listKey) as any).data.map((r: any) => r.id)).toEqual(['e1']));
  });

  it('category create commits the server row; remove leaves on click', async () => {
    const { qc, wrapper } = harness();
    const d = deferred();
    const api: any = makeRoutedApi({ 'POST /api/finance/categories': () => d.promise, 'DELETE /api/finance/categories/c1': () => d.promise });
    const { result } = renderHook(() => createFinanceHooks(api).useCategoryMutations(), { wrapper });
    qc.setQueryData(financeKeys.categories, [{ id: 'c1', name: 'A' }]);
    act(() => result.current.create.mutate({ name: 'B' } as any));
    await act(async () => d.resolve({ data: { id: 'c2', name: 'B' } }));
    await waitFor(() => expect((qc.getQueryData(financeKeys.categories) as any[]).map((c) => c.id)).toEqual(['c1', 'c2']));
    const d2 = deferred();
    api.route('DELETE /api/finance/categories/c1', () => d2.promise);
    act(() => result.current.remove.mutate('c1'));
    await waitFor(() => expect((qc.getQueryData(financeKeys.categories) as any[]).map((c) => c.id)).toEqual(['c2']));
  });

  it('reminder rules: create commits, remove leaves on click', async () => {
    const { qc, wrapper } = harness();
    const d = deferred();
    const api: any = makeRoutedApi({ 'POST /api/finance/reminders/rules': () => d.promise, 'DELETE /api/finance/reminders/rules/r1': () => d.promise });
    const { result } = renderHook(() => createFinanceReminderHooks(api).useReminderRuleMutations(), { wrapper });
    qc.setQueryData(reminderKeys.rules, [{ id: 'r1' }]);
    act(() => result.current.create.mutate({} as any));
    await act(async () => d.resolve({ data: { id: 'r2' } }));
    await waitFor(() => expect((qc.getQueryData(reminderKeys.rules) as any[]).map((r) => r.id)).toEqual(['r1', 'r2']));
    const d2 = deferred();
    api.route('DELETE /api/finance/reminders/rules/r1', () => d2.promise);
    act(() => { void result.current.remove.mutateAsync('r1'); });
    await waitFor(() => expect((qc.getQueryData(reminderKeys.rules) as any[]).map((r) => r.id)).toEqual(['r2']));
  });
});

describe('card hub', () => {
  const descriptor = { rootKey: ['t', 'hub'], basePath: '/api/cards', entityLabel: 'card' };

  it('a comentario lands in the card badge and the unfiltered timeline after ONE round trip', async () => {
    const { qc, wrapper } = harness();
    const d = deferred();
    const api: any = makeRoutedApi({ 'POST /api/cards/c1/notas': () => d.promise });
    const hooks = createCardHubHooks(descriptor, api);
    qc.setQueryData(hooks.keys.card('c1'), { tags: [], membros: [], descricao: null, datas: {}, badges: { notas: 0, tem_descricao: false } });
    qc.setQueryData(hooks.keys.timeline('c1'), { pages: [{ items: [], total: 0, next_cursor: null }], pageParams: [null] });
    const { result } = renderHook(() => hooks.useNotaMutations('c1'), { wrapper });
    act(() => result.current.create.mutate({ corpo: 'oi' }));
    await act(async () => d.resolve({ id: 'n1', tipo: 'comentario', corpo: 'oi', autor: { id: 'u', nome: 'Ana' }, editado_em: null, deleted_at: null }));
    await waitFor(() => expect(result.current.create.isSuccess).toBe(true));
    expect((qc.getQueryData(hooks.keys.card('c1')) as any).badges.notas).toBe(1);
    expect((qc.getQueryData(hooks.keys.timeline('c1')) as any).pages[0].items[0]).toMatchObject({ id: 'n1', corpo: 'oi', kind: 'nota' });
  });

  it('a descricao fills the card state, not the timeline', async () => {
    const { qc, wrapper } = harness();
    const api: any = makeRoutedApi({ 'POST /api/cards/c1/notas': { id: 'd1', tipo: 'descricao', corpo: 'texto', autor: null, editado_em: null, deleted_at: null } });
    const hooks = createCardHubHooks(descriptor, api);
    qc.setQueryData(hooks.keys.card('c1'), { tags: [], membros: [], descricao: null, datas: {}, badges: { notas: 0, tem_descricao: false } });
    const { result } = renderHook(() => hooks.useNotaMutations('c1'), { wrapper });
    await act(async () => { await result.current.create.mutateAsync({ corpo: 'texto', tipo: 'descricao' }); });
    expect((qc.getQueryData(hooks.keys.card('c1')) as any)).toMatchObject({ descricao: { id: 'd1', corpo: 'texto' }, badges: { tem_descricao: true } });
  });

  it('lembrete create commits the server row; remove leaves on click; extras follow', async () => {
    const { qc, wrapper } = harness();
    const d = deferred();
    const api: any = makeRoutedApi({
      'POST /api/cards/c1/lembretes': () => d.promise,
      'DELETE /api/cards/c1/lembretes/l1': () => d.promise,
      'POST /api/cards/c1/checklist-extras': () => d.promise,
    });
    const hooks = createCardHubHooks(descriptor, api);
    qc.setQueryData(hooks.keys.lembretes('c1'), [{ id: 'l1' }]);
    qc.setQueryData(hooks.keys.checklistExtras('c1'), []);
    const { result } = renderHook(() => ({ l: hooks.useLembreteMutations('c1'), e: hooks.useChecklistExtraMutations('c1') }), { wrapper });
    act(() => result.current.l.criar.mutate({ titulo: 'x', dispara_em: 'y' }));
    await act(async () => d.resolve({ id: 'l2', titulo: 'x' }));
    await waitFor(() => expect((qc.getQueryData(hooks.keys.lembretes('c1')) as any[]).map((r) => r.id)).toEqual(['l1', 'l2']));
    const d2 = deferred();
    api.route('DELETE /api/cards/c1/lembretes/l1', () => d2.promise);
    act(() => result.current.l.remover.mutate('l1'));
    await waitFor(() => expect((qc.getQueryData(hooks.keys.lembretes('c1')) as any[]).map((r) => r.id)).toEqual(['l2']));
    const d3 = deferred();
    api.route('POST /api/cards/c1/checklist-extras', () => d3.promise);
    act(() => result.current.e.criar.mutate({ label: 'L', tipo: 'texto' }));
    await act(async () => d3.resolve({ id: 'x1', label: 'L', tipo: 'texto' }));
    await waitFor(() => expect((qc.getQueryData(hooks.keys.checklistExtras('c1')) as any[]).map((r) => r.id)).toEqual(['x1']));
  });

  it('checklist item add / toggle / text / remove are all drawn in flight', async () => {
    const { qc, wrapper } = harness();
    const d = deferred();
    const api: any = makeRoutedApi({
      'POST /api/cards/c1/checklists/k1/itens': () => d.promise,
      'PATCH /api/cards/c1/checklists/k1/itens/i1': () => d.promise,
      'DELETE /api/cards/c1/checklists/k1/itens/i1': () => d.promise,
    });
    const hooks = createCardHubHooks(descriptor, api);
    const item = { id: 'i1', texto: 'a', concluido: false, concluido_em: null, concluido_por: null, posicao: 0 };
    qc.setQueryData(hooks.keys.checklists('c1'), [{ id: 'k1', titulo: 'T', posicao: 0, origem: 'ad_hoc', etapa_id: null, itens: [item], total_itens: 1, concluidos: 0 }]);
    const { result } = renderHook(() => hooks.useChecklistMutations('c1'), { wrapper });
    const itens = () => (qc.getQueryData(hooks.keys.checklists('c1')) as any[])[0].itens as any[];
    act(() => result.current.addItem.mutate({ checklistId: 'k1', texto: 'b' }));
    await waitFor(() => expect(itens()).toHaveLength(2));
    expect(itens()[1].id.startsWith('optimistic:')).toBe(true);
    act(() => result.current.toggleItem.mutate({ checklistId: 'k1', itemId: 'i1', concluido: true }));
    await waitFor(() => expect(itens()[0].concluido).toBe(true));
    act(() => result.current.updateItemText.mutate({ checklistId: 'k1', itemId: 'i1', texto: 'novo' }));
    await waitFor(() => expect(itens()[0].texto).toBe('novo'));
    act(() => result.current.removeItem.mutate({ checklistId: 'k1', itemId: 'i1' }));
    await waitFor(() => expect(itens().map((i) => i.id).includes('i1')).toBe(false));
  });

  it('tag catalogue: create commits, remove leaves on click', async () => {
    const { qc, wrapper } = harness();
    const d = deferred();
    const api: any = makeRoutedApi({ 'POST /api/cards/tags': () => d.promise, 'DELETE /api/cards/tags/t1': () => d.promise });
    const hooks = createCardHubHooks(descriptor, api);
    qc.setQueryData(hooks.keys.tags, [{ id: 't1', nome: 'a', cor: '#fff' }]);
    const { result } = renderHook(() => hooks.useTagCatalogMutations(), { wrapper });
    act(() => result.current.create.mutate({ nome: 'b', cor: '#000' }));
    await act(async () => d.resolve({ id: 't2', nome: 'b', cor: '#000' }));
    await waitFor(() => expect((qc.getQueryData(hooks.keys.tags) as any[]).map((t) => t.id)).toEqual(['t1', 't2']));
    const d2 = deferred();
    api.route('DELETE /api/cards/tags/t1', () => d2.promise);
    act(() => result.current.remove.mutate('t1'));
    await waitFor(() => expect((qc.getQueryData(hooks.keys.tags) as any[]).map((t) => t.id)).toEqual(['t2']));
  });

  it('documento upload commits the server row; remove leaves on click', async () => {
    const { qc, wrapper } = harness();
    const d = deferred();
    const api: any = makeRoutedApi({ 'UPLOAD /api/cards/c1/documentos': () => d.promise, 'DELETE /api/cards/c1/documentos/d1': () => d.promise });
    api.upload = vi.fn(() => d.promise);
    const hooks = createCardHubHooks(descriptor, api);
    qc.setQueryData(hooks.keys.documentos('c1'), [{ id: 'd1' }]);
    const { result } = renderHook(() => hooks.useDocumentoMutations('c1'), { wrapper });
    act(() => result.current.upload.mutate({ file: new File(['x'], 'x.txt', { type: 'text/plain' }), tipoDocumento: 'rg' }));
    await act(async () => d.resolve({ id: 'd2' }));
    await waitFor(() => expect((qc.getQueryData(hooks.keys.documentos('c1')) as any[]).map((r) => r.id)).toEqual(['d1', 'd2']));
    const d2 = deferred();
    api.route('DELETE /api/cards/c1/documentos/d1', () => d2.promise);
    act(() => result.current.remove.mutate({ documentoId: 'd1', motivo: 'x' }));
    await waitFor(() => expect((qc.getQueryData(hooks.keys.documentos('c1')) as any[]).map((r) => r.id)).toEqual(['d2']));
  });
});

describe('team / api keys', () => {
  it('invite commits the created invitation; cancel leaves the pending list on click', async () => {
    const { qc, wrapper } = harness();
    const d = deferred();
    const api: any = makeRoutedApi({ 'POST /api/team/invite': () => d.promise, 'DELETE /api/team/invitations/i1': () => d.promise });
    const { result } = renderHook(() => createTeamHooks(api).useInviteMember(), { wrapper });
    const cancel = renderHook(() => createTeamHooks(api).useCancelInvitation(), { wrapper });
    qc.setQueryData(TEAM_QUERY_KEYS.invitations, [{ id: 'i1', email: 'a@x', role: 'admin' }]);
    act(() => result.current.mutate({ email: 'b@x', role: 'admin' }));
    await act(async () => d.resolve({ data: { id: 'i2', email: 'b@x', role: 'admin' }, email_enviado: true }));
    await waitFor(() => expect((qc.getQueryData(TEAM_QUERY_KEYS.invitations) as any[]).map((i) => i.id)).toEqual(['i2', 'i1']));
    const d2 = deferred();
    api.route('DELETE /api/team/invitations/i1', () => d2.promise);
    act(() => cancel.result.current.mutate('i1'));
    await waitFor(() => expect((qc.getQueryData(TEAM_QUERY_KEYS.invitations) as any[]).map((i) => i.id)).toEqual(['i2']));
  });

  it('saving an api key writes the re-resolved status into the list', async () => {
    const { qc, wrapper } = harness();
    const api: any = makeRoutedApi({ 'PUT /api/settings/api-keys/K': { key: 'K', label: 'Chave', configured: true, hint: '...b3f9' } });
    const hooks = createApiKeysHooks(api);
    qc.setQueryData(['api-keys', '/api/settings/api-keys'], { items: [{ key: 'K', label: 'Chave', configured: false, hint: null }], total: 1 });
    const { result } = renderHook(() => hooks.useSaveApiKey(), { wrapper });
    await act(async () => { await result.current.mutateAsync({ key: 'K', value: 'secret' }); });
    expect((qc.getQueryData(['api-keys', '/api/settings/api-keys']) as any).items[0]).toMatchObject({ configured: true, hint: '...b3f9' });
  });
});

describe('pipeline stages', () => {
  const descriptor: any = {
    queryKey: 'pipe', boardEndpoint: '/api/b', stagesEndpoint: '/api/stages', moveEndpoint: '/api/cards',
    getCardId: (c: any) => c.id, getCardValue: () => 0, entityLabel: 'card',
  };
  it('create commits the server stage; delete leaves the list on click', async () => {
    const { qc, wrapper } = harness();
    const d = deferred();
    const api: any = makeRoutedApi({ 'POST /api/stages': () => d.promise, 'DELETE /api/stages/s1': () => d.promise });
    const hooks = createPipelineHooks(descriptor, api);
    qc.setQueryData(['pipe-stages'], [{ id: 's1', label: 'A' }]);
    const { result } = renderHook(() => ({ c: hooks.useCreateStage(), x: hooks.useDeleteStage() }), { wrapper });
    act(() => result.current.c.mutate({ label: 'B' }));
    await act(async () => d.resolve({ data: { id: 's2', label: 'B' } }));
    await waitFor(() => expect((qc.getQueryData(['pipe-stages']) as any[]).map((s) => s.id)).toEqual(['s1', 's2']));
    const d2 = deferred();
    api.route('DELETE /api/stages/s1', () => d2.promise);
    act(() => result.current.x.mutate({ id: 's1' }));
    await waitFor(() => expect((qc.getQueryData(['pipe-stages']) as any[]).map((s) => s.id)).toEqual(['s2']));
  });
});

describe('whatsapp / notifications / llm', () => {
  it('connection create commits, remove leaves on click; start writes the session status', async () => {
    const { qc, wrapper } = harness();
    const d = deferred();
    const api: any = makeRoutedApi({
      'POST /api/whatsapp/connections': () => d.promise,
      'DELETE /api/whatsapp/connections/w1': () => d.promise,
      'POST /api/whatsapp/connections/w1/start': () => d.promise,
    });
    const hooks = createWhatsAppConnectionsHooks(api);
    const KEY = ['whatsapp', 'connections', '/api/whatsapp/connections'];
    qc.setQueryData(KEY, [{ id: 'w1', label: 'a' }]);
    const m = renderHook(() => ({ m: hooks.useConnectionMutations(), a: hooks.useConnectionActions() }), { wrapper });
    act(() => m.result.current.m.create.mutate({ label: 'b', api_key: 'k' }));
    await act(async () => d.resolve({ id: 'w2', label: 'b' }));
    await waitFor(() => expect((qc.getQueryData(KEY) as any[]).map((r) => r.id)).toEqual(['w1', 'w2']));
    const d2 = deferred();
    api.route('DELETE /api/whatsapp/connections/w1', () => d2.promise);
    act(() => m.result.current.m.remove.mutate('w1'));
    await waitFor(() => expect((qc.getQueryData(KEY) as any[]).map((r) => r.id)).toEqual(['w2']));
    const d3 = deferred();
    api.route('POST /api/whatsapp/connections/w2/start', () => d3.promise);
    act(() => m.result.current.a.start.mutate('w2'));
    await act(async () => d3.resolve({ connection_id: 'w2', status: 'WORKING', paired: true }));
    await waitFor(() => expect(qc.getQueryData([...KEY, 'w2', 'status'])).toMatchObject({ status: 'WORKING' }));
  });

  it('marking a notification read flips it in every cached page on click; read-all zeroes the badge', async () => {
    const { qc, wrapper } = harness();
    const d = deferred();
    const api: any = makeRoutedApi({ 'PATCH /api/notificacoes/n1/ler': () => d.promise, 'POST /api/notificacoes/ler-todas': () => d.promise });
    const hooks = createNotificationHooks(api, () => ({ user: null }));
    qc.setQueryData(['notificacoes', 1, 20, false], page([{ id: 'n1', is_read: false }, { id: 'n2', is_read: false }]));
    qc.setQueryData(['notificacoes-contagem'], { nao_lidas: 2 });
    const { result } = renderHook(() => ({ one: hooks.useMarcarComoLida(), all: hooks.useMarcarTodasComoLidas() }), { wrapper });
    act(() => result.current.one.mutate('n1'));
    await waitFor(() => expect((qc.getQueryData(['notificacoes', 1, 20, false]) as any).data[0].is_read).toBe(true));
    expect((qc.getQueryData(['notificacoes', 1, 20, false]) as any).data[1].is_read).toBe(false);
    act(() => result.current.all.mutate());
    await waitFor(() => expect((qc.getQueryData(['notificacoes-contagem']) as any).nao_lidas).toBe(0));
    expect((qc.getQueryData(['notificacoes', 1, 20, false]) as any).data.every((n: any) => n.is_read)).toBe(true);
  });

  it('saving LLM preferences draws them on click', async () => {
    const { qc, wrapper } = harness();
    const d = deferred();
    const api: any = makeRoutedApi({ 'PUT /api/llm/preferences': () => d.promise });
    qc.setQueryData(['llm', 'preferences'], { provider: 'openai', chat_model: 'a', embedding_model: null });
    const { result } = renderHook(() => createLLMHooks(api).useUpdateLLMPreferences(), { wrapper });
    act(() => result.current.mutate({ provider: 'anthropic', chat_model: 'b', embedding_model: null }));
    await waitFor(() => expect((qc.getQueryData(['llm', 'preferences']) as any).provider).toBe('anthropic'));
  });
});
