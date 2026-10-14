import type { RemoveMemberResult } from '../../hooks/useTeam';

/**
 * The pt-BR success message for a removal, saying exactly what happened to the person's account
 * (`DELETE /api/team/{user_id}` → `data`, multi-org S5b):
 * - a personal org was created (sole-org member, D4);
 * - the profile moved to another org they belong to (named when the viewer knows it);
 * - nothing moved (this org was not their profile org).
 * `orgName` resolves an org id to a name the viewer can see; `undefined` when unknown.
 */
export function removeMemberMessage(
  memberNome: string,
  orgNome: string,
  result: RemoveMemberResult | undefined,
  orgName: (orgId: string) => string | undefined,
): string {
  const head = `${memberNome} foi removido(a) de ${orgNome}.`;
  if (!result) return head;
  if (result.personal_org_id) {
    return `${head} Como esta era a única organização da pessoa, a conta foi mantida em uma organização pessoal própria, com o histórico preservado.`;
  }
  if (result.profile_moved_to) {
    const target = orgName(result.profile_moved_to);
    return target
      ? `${head} A conta passa a usar ${target} como organização principal.`
      : `${head} A conta passa a usar outra organização de que a pessoa participa.`;
  }
  return `${head} A pessoa continua nas outras organizações de que participa.`;
}
