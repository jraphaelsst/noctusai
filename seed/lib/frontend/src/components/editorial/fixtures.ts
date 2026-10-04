import type { EditorialEvent, EditorialItem, EditorialVersion } from './types';

export const mkItem = (over: Partial<EditorialItem> = {}): EditorialItem => ({
  id: 'i1',
  org_id: 'o1',
  kind: 'atividade',
  ref: 'atividade-1',
  state: 'rascunho',
  published_version_n: null,
  current_version_n: 1,
  created_at: '2026-10-01T10:00:00Z',
  updated_at: '2026-10-02T10:00:00Z',
  ...over,
});

export const mkVersion = (n: number, content: Record<string, unknown>): EditorialVersion => ({
  item_id: 'i1',
  n,
  content,
  content_sha: `sha${n}`,
  author_id: 'u1',
  created_at: '2026-10-01T10:00:00Z',
});

export const mkEvent = (id: number, over: Partial<EditorialEvent> = {}): EditorialEvent => ({
  id,
  item_id: 'i1',
  version_n: 1,
  action: 'submit',
  from_state: 'rascunho',
  to_state: 'revisao_editorial',
  actor_id: 'u1',
  grant: 'editorial:editar',
  motivo: null,
  created_at: `2026-10-0${id}T10:00:00Z`,
  ...over,
});
