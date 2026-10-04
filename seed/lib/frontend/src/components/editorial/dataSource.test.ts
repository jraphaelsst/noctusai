import { describe, expect, it, vi } from 'vitest';
import { createEditorialHttpSource } from './dataSource';
import { mkEvent, mkItem, mkVersion } from './fixtures';

const env = (data: unknown) => ({ success: true, data });

describe('createEditorialHttpSource (editorial_router contract)', () => {
  it('listQueue: GET base with filters, unwraps envelope', async () => {
    const page = { items: [mkItem()], total: 1, counts: { rascunho: 1 }, page: 1, page_size: 20 };
    const api = { get: vi.fn().mockResolvedValue(env(page)), post: vi.fn() };
    const ds = createEditorialHttpSource(api, '/api/k/editorial');
    expect(await ds.listQueue({ state: 'rascunho', awaiting_me: true, page: 2, page_size: 20 })).toEqual(page);
    expect(api.get).toHaveBeenCalledWith('/api/k/editorial', {
      state: 'rascunho', awaiting_me: true, page: 2, page_size: 20,
    });
  });

  it('listQueue: omits unset filters', async () => {
    const api = { get: vi.fn().mockResolvedValue({ items: [], total: 0, counts: {} }), post: vi.fn() };
    await createEditorialHttpSource(api, '/e').listQueue({ page: 1, page_size: 5 });
    expect(api.get).toHaveBeenCalledWith('/e', { page: 1, page_size: 5 });
  });

  it('transition posts to /transitions; createVersion returns the minted version', async () => {
    const v = mkVersion(2, { t: 1 });
    const api = {
      get: vi.fn(),
      post: vi
        .fn()
        .mockResolvedValueOnce(env({ item: mkItem(), event: mkEvent(1), version: null }))
        .mockResolvedValueOnce(env({ item: mkItem(), event: mkEvent(2), version: v })),
    };
    const ds = createEditorialHttpSource(api, '/e');
    await ds.transition('i1', 'send_back', 'Falta fonte');
    expect(api.post).toHaveBeenNthCalledWith(1, '/e/i1/transitions', { action: 'send_back', motivo: 'Falta fonte' });
    expect(await ds.createVersion('i1', { t: 1 })).toEqual(v);
    expect(api.post).toHaveBeenNthCalledWith(2, '/e/i1/versions', { content: { t: 1 } });
  });

  it('diff reads both versions from GET /{id}; missing version throws', async () => {
    const detail = { item: mkItem(), versions: [mkVersion(1, {}), mkVersion(2, {})], events: [] };
    const api = { get: vi.fn().mockResolvedValue(env(detail)), post: vi.fn() };
    const ds = createEditorialHttpSource(api, '/e');
    const r = await ds.diff('i1', 1, 2);
    expect([r.from.n, r.to.n]).toEqual([1, 2]);
    expect(api.get).toHaveBeenCalledWith('/e/i1');
    await expect(ds.diff('i1', 1, 9)).rejects.toThrow('Versão 9 não encontrada.');
  });
});
