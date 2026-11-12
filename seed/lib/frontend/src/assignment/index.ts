/** Assignment organ — public surface (re-exported from the `@noctusai/lib` barrel). Backend: `noctusai_lib.domain.assignment`. */
export { ASSIGNMENT_STRATEGIES, ASSIGNMENT_EVENT_KINDS, ASSIGNMENT_RULE_KINDS } from './types';
export type {
  AssignmentAssignInput,
  AssignmentAssignResult,
  AssignmentEnvelope,
  AssignmentEvent,
  AssignmentEventKind,
  AssignmentRule,
  AssignmentSettings,
  AssignmentBuiltinStrategy,
  AssignmentEventsParams,
  AssignmentMemberInput,
  AssignmentMemberPatch,
  AssignmentReassignInput,
  AssignmentReleaseInput,
  AssignmentReleaseResult,
  AssignmentRuleInput,
  AssignmentRuleKind,
  AssignmentSettingsPatch,
  SubjectAssignment,
  AssignmentTeam,
  AssignmentTeamInput,
  AssignmentTeamMember,
  AssignmentTeamPatch,
  AssignmentUnavailableReason,
  AssignmentWorkloadRow,
} from './types';
export { assignmentErrorMessage, assignmentKeys, compareAssignmentTeams, createAssignmentHooks } from './hooks';
export type { AssignmentApi, AssignmentHooks } from './hooks';
export { ASSIGNMENT_MESSAGES } from './messages';
export { createAssignmentTranslator, defaultAssignmentT } from './i18n';
export type { AssignmentTranslate } from './i18n';
export type { AssignmentOrganProps } from './shared';
export { TeamsManager } from './TeamsManager';
export type { TeamsManagerProps } from './TeamsManager';
export { AssignmentRulesPage } from './AssignmentRulesPage';
export type { AssignmentRulesPageProps } from './AssignmentRulesPage';
export { ASSIGNMENT_DEFAULT_LABELS, ASSIGNMENT_DEFAULT_PATHS, ASSIGNMENT_PAGE_KEYS, assignmentModuleItems } from './pages';
export type { AssignmentModuleItemsOptions } from './pages';
