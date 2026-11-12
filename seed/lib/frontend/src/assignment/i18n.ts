/** Assignment i18n: the shared organ translator over the pt-BR table; an unknown key renders as the key itself. */
import { createOrganTranslator, type OrganTranslate } from '../organ-kit/i18n';
import { ASSIGNMENT_MESSAGES } from './messages';

export type AssignmentTranslate = OrganTranslate;

export function createAssignmentTranslator(overrides?: Record<string, string>): AssignmentTranslate {
  return createOrganTranslator(ASSIGNMENT_MESSAGES as Record<string, string>, overrides);
}

export const defaultAssignmentT: AssignmentTranslate = createAssignmentTranslator();
