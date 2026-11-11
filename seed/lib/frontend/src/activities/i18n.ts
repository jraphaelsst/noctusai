/** Activities i18n: pt-BR table; unknown key -> the key itself (visible, never blank). */
import { createOrganTranslator, type OrganTranslate } from '../organ-kit/i18n';
import { ACTIVITIES_MESSAGES } from './messages';

export type ActivitiesTranslate = OrganTranslate;

export function createActivitiesTranslator(overrides?: Record<string, string>): ActivitiesTranslate {
  return createOrganTranslator(ACTIVITIES_MESSAGES as Record<string, string>, overrides);
}

export const defaultActivitiesT: ActivitiesTranslate = createActivitiesTranslator();
