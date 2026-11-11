/** Wire shapes of the activities API (`/api/activities`). Mirror `noctusai_lib.domain.activities` — keep the two in step. */

export const ACTIVITIES_KINDS = ['task', 'call', 'meeting', 'visit'] as const;
export type ActivitiesKind = (typeof ACTIVITIES_KINDS)[number];

export const ACTIVITY_OUTCOMES = ['realizada', 'nao_realizada', 'sem_resposta'] as const;
export type ActivityOutcome = (typeof ACTIVITY_OUTCOMES)[number];

export type ActivityStatus = 'open' | 'done' | 'cancelled' | 'all';

export interface ActivityType {
  org_id: string;
  slug: string;
  label: string;
  kind: ActivitiesKind;
  position: number;
  active: boolean;
}

export interface Activity {
  id: string;
  org_id: string;
  entity_kind: string;
  entity_id: string;
  type_slug: string;
  kind: ActivitiesKind;
  title: string;
  notes: string | null;
  due_at: string | null;
  /** A plain user id (the host maps it to a name through `assigneeLabel`). */
  assignee_id: string | null;
  /** The nullable multi-branch convention: carried, never interpreted by the organ. */
  org_unit_id: string | null;
  done_at: string | null;
  done_by: string | null;
  outcome: ActivityOutcome | null;
  cancelled_at: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  /** Derived by the server on read (open and past due). */
  overdue: boolean;
}

export interface ActivityEvent {
  id: string;
  seq: number;
  activity_id: string;
  event: string;
  actor_id: string | null;
  occurred_at: string;
  data: Record<string, unknown>;
}

export interface ActivitiesEnvelope<T> {
  data: T;
}
export interface ActivitiesPage<T> {
  data: T[];
  pagination: { page: number; page_size: number; total: number; total_pages?: number };
}

export interface ActivityListParams {
  entity_kind?: string;
  entity_id?: string;
  assignee_id?: string;
  status?: ActivityStatus;
  type_slug?: string;
  kind?: ActivitiesKind;
  overdue?: boolean;
  due_from?: string;
  due_to?: string;
  page?: number;
  page_size?: number;
}

export interface ActivityInput {
  entity_kind: string;
  entity_id: string;
  type_slug: string;
  title: string;
  notes?: string | null;
  due_at?: string | null;
  assignee_id?: string | null;
  org_unit_id?: string | null;
}

export interface TypeInput {
  slug: string;
  label: string;
  kind: ActivitiesKind;
  position?: number;
}
export interface TypePatch {
  label?: string;
  position?: number;
  active?: boolean;
}

/** Someone an activity can be assigned to (the host supplies them: names belong to the team / identity layer). */
export interface AssigneeOption {
  id: string;
  label: string;
}
