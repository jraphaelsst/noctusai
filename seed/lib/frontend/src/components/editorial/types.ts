/**
 * Editorial workflow — FE contract types. They mirror the backend domain
 * (`noctusai_lib/domain/editorial/{workflow,store}.py`): JSON field names are
 * the dataclass field names (snake_case); states/actions are the enum values.
 */

export type EditorialState =
  | 'rascunho'
  | 'revisao_editorial'
  | 'revisao_seguranca'
  | 'publicado'
  | 'arquivado';

export type EditorialAction =
  | 'create'
  | 'edit'
  | 'submit'
  | 'approve_editorial'
  | 'approve_security'
  | 'publish'
  | 'send_back'
  | 'archive';

export const EDITORIAL_STATES: readonly EditorialState[] = [
  'rascunho',
  'revisao_editorial',
  'revisao_seguranca',
  'publicado',
  'arquivado',
];

export interface EditorialItem {
  id: string;
  org_id: string;
  kind: string;
  ref: string;
  state: EditorialState;
  published_version_n: number | null;
  current_version_n: number;
  created_at: string;
  updated_at: string;
  /** Optional display title the router may attach (falls back to `ref`). */
  title?: string | null;
}

export interface EditorialVersion {
  item_id: string;
  n: number;
  content: Record<string, unknown>;
  content_sha: string;
  author_id: string;
  created_at: string;
}

export interface EditorialEvent {
  id: number;
  item_id: string;
  version_n: number;
  action: EditorialAction | string;
  from_state: EditorialState | null;
  to_state: EditorialState;
  actor_id: string;
  grant: string | null;
  motivo: string | null;
  created_at: string;
}

export interface EditorialQueueParams {
  /** Restrict to one state; omitted = every state. */
  state?: EditorialState | null;
  /** Only items whose NEXT step the current user can take (server-derived). */
  awaiting_me?: boolean;
  page: number;
  page_size: number;
}

export interface EditorialQueuePage {
  items: EditorialItem[];
  /** Total items matching the filter (for paging). */
  total: number;
  /** Count per state under the same `awaiting_me` filter, ignoring `state`. */
  counts: Partial<Record<EditorialState, number>>;
}

export interface EditorialItemDetail {
  item: EditorialItem;
  versions: EditorialVersion[];
  events: EditorialEvent[];
}

/**
 * The typed seam the organs consume. `createEditorialHttpSource(api)` is the
 * real adapter; `FakeEditorialDataSource` the in-memory one (tests / demos).
 */
export interface EditorialDataSource {
  listQueue(params: EditorialQueueParams): Promise<EditorialQueuePage>;
  getItem(itemId: string): Promise<EditorialItemDetail>;
  createVersion(itemId: string, content: Record<string, unknown>): Promise<EditorialVersion>;
  transition(
    itemId: string,
    action: EditorialAction,
    motivo?: string | null,
  ): Promise<{ item: EditorialItem; event: EditorialEvent }>;
  diff(itemId: string, fromN: number, toN: number): Promise<{ from: EditorialVersion; to: EditorialVersion }>;
}
