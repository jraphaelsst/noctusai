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

/** Real adapter. `basePath` defaults to `/api/editorial`. */
export function createEditorialHttpSource(
  api: EditorialApi,
  basePath = '/api/editorial',
): EditorialDataSource {
  return {
    listQueue: (p) =>
      api.get<EditorialQueuePage>(`${basePath}/queue`, {
        ...(p.state ? { state: p.state } : {}),
        ...(p.awaiting_me ? { awaiting_me: true } : {}),
        page: p.page,
        page_size: p.page_size,
      }),
    getItem: (id) => api.get<EditorialItemDetail>(`${basePath}/items/${id}`),
    createVersion: (id, content) =>
      api.post<EditorialVersion>(`${basePath}/items/${id}/versions`, { content }),
    transition: (id, action, motivo) =>
      api.post(`${basePath}/items/${id}/transition`, { action, motivo: motivo ?? null }),
    diff: (id, fromN, toN) =>
      api.get(`${basePath}/items/${id}/diff`, { from: fromN, to: toN }),
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
