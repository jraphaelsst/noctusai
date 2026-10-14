/**
 * Team admin error copy — every refusal code of the multi-org S4b contract
 * (`project-history/roadmaps/multi-org-membership-2026-10.md` § "S4b API contract") mapped to a
 * pt-BR sentence the admin can act on. The backend sends `{detail, code}`; the code wins, the
 * server's own detail is the fallback for anything unmapped (never a bare "HTTP 403").
 */
import { ApiError } from '@noctusai/lib';

/** `POST /api/team/move` + `PUT .../product-access/{slug}` + the RPC-backed team writes. */
export const TEAM_ERROR_MESSAGES: Record<string, string> = {
  // move (D3)
  invalid_role: 'Papel inválido para a organização de destino.',
  invalid_mode: 'Escolha se a pessoa será transferida ou adicionada.',
  same_org: 'A organização de destino precisa ser diferente da organização atual.',
  forbidden: 'Você precisa ser proprietário ou administrador nas duas organizações para fazer isso.',
  role_above_actor: 'Você não pode conceder um papel acima do seu na organização de destino.',
  // owner decisions P1/P3/P5 (2026-10-14)
  owner_grant_forbidden: 'Somente a equipe NoctusAI pode conceder o papel de proprietário.',
  cannot_block_staff: 'A equipe NoctusAI não pode ser bloqueada de nenhum produto.',
  membership_suspended:
    'A participação desta pessoa na organização de destino está suspensa. Reative-a antes de movê-la.',
  not_a_member: 'Esta pessoa não é mais membro ativo desta organização. Atualize a lista.',
  org_not_found: 'Organização não encontrada.',
  last_owner:
    'Não é possível transferir o último proprietário: a organização precisa manter ao menos um. '
    + 'Use "Adicionar" ou defina outro proprietário antes.',
  already_member: 'Esta pessoa já é membro da organização de destino.',
  // product access (D5)
  product_not_found: 'Produto não encontrado.',
  not_licensed: 'A organização não tem licença ativa deste produto.',
  // remove (D4) — transient race inside the removal transaction
  personal_org_required: 'A situação do membro mudou durante a remoção. Tente novamente.',
  personal_org_invalid: 'Não foi possível preparar a organização pessoal do membro. Tente novamente.',
};

const STATUS_MESSAGES: Record<number, string> = {
  401: 'Sua sessão expirou. Entre novamente.',
  422: 'Dados inválidos. Revise os campos e tente novamente.',
};

/** The pt-BR message for a failed team call (`fallback` when nothing better is known). */
export function teamErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    const code = err.code;
    if (code && TEAM_ERROR_MESSAGES[code]) return TEAM_ERROR_MESSAGES[code];
    if (err.status !== null && STATUS_MESSAGES[err.status]) return STATUS_MESSAGES[err.status];
    const msg = err.message.replace(/^\[\d+\]\s*/, '').trim();
    return msg || fallback;
  }
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}
