/**
 * Data sources for the editorial organs: the HTTP adapter (expected router
 * paths — see README.md) and an in-memory Fake.
 */
import type {
  EditorialAction,
  EditorialDataSource,
  EditorialEvent,
  EditorialItem,
  EditorialItemDetail,
  EditorialQueuePage,
  EditorialQueueParams,
  EditorialState,
  EditorialVersion,
} from './types';
import { EDITORIAL_STATES } from './types';

export interface EditorialApi {
  get: <T = any>(path: string, params?: Record<string, any>) => Promise<T>;
  post: <T = any>(path: string, body?: unknown) => Promise<T>;
}

/** `success_response` envelope: `{success, data, total?}`; tolerate a bare payload. */
function unwrap<T>(res: any): T {
  return res && typeof res === 'object' && 'data' in res && 'success' in res ? res.data : res;
}

/**
 * Real adapter for `editorial_router` (backend `domain/editorial/router.py`).
 * `basePath` is the consumer's mount prefix, e.g. `/api/knowledge/editorial`.
 */
export function createEditorialHttpSource(api: EditorialApi, basePath: string): EditorialDataSource {
  const getItem = async (id: string) =>
    unwrap<EditorialItemDetail>(await api.get(`${basePath}/${id}`));
  return {
    listQueue: async (p) =>
      unwrap<EditorialQueuePage>(
        await api.get(basePath, {
          ...(p.state ? { state: p.state } : {}),
          ...(p.awaiting_me ? { awaiting_me: true } : {}),
          page: p.page,
          page_size: p.page_size,
        }),
      ),
    getItem,
    createVersion: async (id, content) => {
      const res = unwrap<{ version: EditorialVersion }>(
        await api.post(`${basePath}/${id}/versions`, { content }),
      );
      return res.version;
    },
    transition: async (id, action, motivo) =>
      unwrap(await api.post(`${basePath}/${id}/transitions`, { action, motivo: motivo ?? null })),
    // The diff is computed client-side from the two versions (GET /{id} already carries them).
    diff: async (id, fromN, toN) => {
      const { versions } = await getItem(id);
      const find = (n: number) => {
        const v = versions.find((x) => x.n === n);
        if (!v) throw new Error(`Versão ${n} não encontrada.`);
        return v;
      };
      return { from: find(fromN), to: find(toN) };
    },
  };
}

/** In-memory data source — tests, stories, consumer demos. */
export class FakeEditorialDataSource implements EditorialDataSource {
  items: EditorialItem[];
  details: Record<string, EditorialItemDetail>;
  /** Item ids the "current user" can act on next (drives `awaiting_me`). */
  awaitingMe: Set<string>;
  calls: EditorialQueueParams[] = [];

  constructor(init: {
    items?: EditorialItem[];
    details?: Record<string, EditorialItemDetail>;
    awaitingMe?: string[];
  } = {}) {
    this.items = init.items ?? [];
    this.details = init.details ?? {};
    this.awaitingMe = new Set(init.awaitingMe ?? []);
  }

  async listQueue(p: EditorialQueueParams): Promise<EditorialQueuePage> {
    this.calls.push(p);
    const base = this.items.filter((i) => !p.awaiting_me || this.awaitingMe.has(i.id));
    const counts: Partial<Record<EditorialState, number>> = {};
    for (const s of EDITORIAL_STATES) counts[s] = base.filter((i) => i.state === s).length;
    const filtered = base.filter((i) => !p.state || i.state === p.state);
    const start = (p.page - 1) * p.page_size;
    return { items: filtered.slice(start, start + p.page_size), total: filtered.length, counts };
  }

  async getItem(id: string): Promise<EditorialItemDetail> {
    const d = this.details[id];
    if (!d) throw new Error('Item não encontrado.');
    return d;
  }

  async createVersion(id: string, content: Record<string, unknown>): Promise<EditorialVersion> {
    const d = await this.getItem(id);
    const v: EditorialVersion = {
      item_id: id,
      n: d.item.current_version_n + 1,
      content,
      content_sha: `fake-${d.item.current_version_n + 1}`,
      author_id: 'fake-user',
      created_at: new Date().toISOString(),
    };
    d.versions = [...d.versions, v];
    d.item = { ...d.item, current_version_n: v.n, state: 'rascunho' };
    return v;
  }

  async transition(id: string, action: EditorialAction, motivo?: string | null) {
    const d = await this.getItem(id);
    const event: EditorialEvent = {
      id: d.events.length + 1,
      item_id: id,
      version_n: d.item.current_version_n,
      action,
      from_state: d.item.state,
      to_state: d.item.state,
      actor_id: 'fake-user',
      grant: null,
      motivo: motivo ?? null,
      created_at: new Date().toISOString(),
    };
    d.events = [...d.events, event];
    return { item: d.item, event };
  }

  async diff(id: string, fromN: number, toN: number) {
    const d = await this.getItem(id);
    const find = (n: number) => {
      const v = d.versions.find((x) => x.n === n);
      if (!v) throw new Error(`Versão ${n} não encontrada.`);
      return v;
    };
    return { from: find(fromN), to: find(toN) };
  }
}
