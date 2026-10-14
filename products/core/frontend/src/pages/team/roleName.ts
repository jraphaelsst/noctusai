import { ORG_ROLE_LABELS } from '@noctusai/lib';

import type { TeamRole } from '../../hooks/useTeam';

/** A role slug's display name: the org's role catalog first, then the seed labels, then the slug. */
export function roleName(slug: string, roles: TeamRole[]): string {
  const role = roles.find((r) => r.slug === slug);
  if (role) return role.name;
  return ORG_ROLE_LABELS[slug as keyof typeof ORG_ROLE_LABELS] || slug;
}
