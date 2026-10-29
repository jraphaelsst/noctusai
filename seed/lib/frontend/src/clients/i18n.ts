/** `t(key, vars?)` over the pt-BR table of the clients organ. */
import { createOrganTranslator } from '../organ-kit/i18n';
import { MESSAGES } from './messages';

export const t = createOrganTranslator(MESSAGES);
