/** Wire types of the assignment API (`/api/assignment`) — frozen in `KB § PATTERNS/backend/assignment-organ.md` § 4. */

export const ASSIGNMENT_STRATEGIES = ['round_robin', 'by_team', 'by_source', 'by_unit', 'manual'] as const;
export type AssignmentBuiltinStrategy = (typeof ASSIGNMENT_STRATEGIES)[number];

export const ASSIGNMENT_RULE_KINDS = ['source', 'unit'] as const;
export type AssignmentRuleKind = (typeof ASSIGNMENT_RULE_KINDS)[number];

export const ASSIGNMENT_EVENT_KINDS = ['assigned', 'reassigned', 'unassigned', 'closed', 'no_candidate'] as const;
export type AssignmentEventKind = (typeof ASSIGNMENT_EVENT_KINDS)[number];

export type AssignmentUnavailableReason = 'inactive' | 'out_of_office' | 'at_capacity' | 'left_org';

export interface AssignmentEnvelope<T> {
  data: T;
}

export interface AssignmentSettings {
  /** A builtin or a host-registered custom strategy name. */
  strategy: string;
  default_team_id: string | null;
  keep_last: boolean;
  builtin: string[];
  custom: string[];
}

export interface AssignmentSettingsPatch {
  strategy?: string;
  default_team_id?: string | null;
  keep_last?: boolean;
}

export interface AssignmentTeamMember {
  user_id: string;
  name: string | null;
  /** false = the person left the org while a stale seat remains (never a candidate). */
  in_org: boolean;
  active: boolean;
  position: number;
  capacity: number | null;
  ooo_from: string | null;
  ooo_until: string | null;
  open_count: number;
  unavailable_reason: AssignmentUnavailableReason | null;
}

export interface AssignmentTeam {
  id: string;
  name: string;
  auto: boolean;
  org_unit_id: string | null;
  members: AssignmentTeamMember[];
}

export interface AssignmentTeamInput {
  name: string;
  auto?: boolean;
  org_unit_id?: string | null;
}

export interface AssignmentTeamPatch {
  name?: string;
  auto?: boolean;
  org_unit_id?: string | null;
}

export interface AssignmentMemberInput {
  user_id: string;
  active?: boolean;
  capacity?: number | null;
  ooo_from?: string | null;
  ooo_until?: string | null;
}

/** Explicit `null` clears (capacity → unlimited; a date → no absence). */
export interface AssignmentMemberPatch {
  active?: boolean;
  capacity?: number | null;
  ooo_from?: string | null;
  ooo_until?: string | null;
}

export interface AssignmentRule {
  id: string;
  org_id: string;
  kind: AssignmentRuleKind;
  match_value: string;
  team_id: string;
  created_at: string;
  updated_at: string;
}

export interface AssignmentRuleInput {
  kind: AssignmentRuleKind;
  match_value: string;
  team_id: string;
}

export interface AssignmentWorkloadRow {
  user_id: string;
  name: string | null;
  open_count: number;
  teams: string[];
  available: boolean;
  unavailable_reasons: string[];
}

export interface AssignmentEvent {
  id: string;
  org_id: string;
  subject_kind: string;
  subject_id: string;
  event: AssignmentEventKind;
  from_user_id: string | null;
  to_user_id: string | null;
  team_id: string | null;
  org_unit_id: string | null;
  strategy: string | null;
  criterion: string | null;
  actor_id: string | null;
  note: string | null;
  created_at: string;
}

export interface AssignmentEventsParams {
  subject_kind?: string;
  subject_id?: string;
  limit?: number;
  offset?: number;
}

/** The CURRENT owner of a subject (`GET /assignments/{kind}/{id}`). */
export interface SubjectAssignment {
  id: string;
  org_id: string;
  subject_kind: string;
  subject_id: string;
  user_id: string;
  team_id: string | null;
  org_unit_id: string | null;
  strategy: string;
  criterion: string;
  assigned_at: string;
  closed_at: string | null;
}

export interface AssignmentAssignInput {
  subject_kind: string;
  subject_id: string;
  source?: string | null;
  org_unit_id?: string | null;
  team_id?: string | null;
  note?: string | null;
}

export type AssignmentAssignResult =
  | { assigned: true; user_id: string; team_id: string | null; criterion: string; strategy: string; changed: boolean; event: AssignmentEventKind | null }
  | { assigned: false; reason: string; strategy: string };

export interface AssignmentReassignInput {
  subject_kind: string;
  subject_id: string;
  to_user_id: string;
  team_id?: string | null;
  note?: string | null;
}

export interface AssignmentReleaseInput {
  subject_kind: string;
  subject_id: string;
  note?: string | null;
}

export interface AssignmentReleaseResult {
  changed: boolean;
  event: AssignmentEventKind | null;
}
