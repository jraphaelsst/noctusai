/**
 * Team — the canonical product Equipe page over the seed `/api/team` router.
 *
 * Usage:
 *   import { TeamPage } from "@noctusai/lib";
 */
export { createTeamHooks, TEAM_QUERY_KEYS } from './createTeamHooks';
export type {
  TeamApi,
  TeamHooks,
  TeamMember,
  TeamInvitation,
  TeamPolicyContract,
  TeamInviteResponse,
  TeamInviteBody,
} from './createTeamHooks';

export { TeamPage } from './TeamPage';
export type { TeamPageProps, TeamPageUser } from './TeamPage';
