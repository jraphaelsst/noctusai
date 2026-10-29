import { toast } from 'sonner';

import { t } from './i18n';
import type { Lead } from './types';

/**
 * A write that landed but whose stage hook failed (`stage_hook_error`, e.g. the lead→client conversion on entering a
 * closing stage) is never silent: a non-blocking warning toast names the server's reason.
 */
export function warnStageHook(saved: Pick<Lead, 'stage_hook_error'> | null | undefined): void {
  if (saved?.stage_hook_error) toast.warning(t('stage_hook.warning'), { description: saved.stage_hook_error });
}
