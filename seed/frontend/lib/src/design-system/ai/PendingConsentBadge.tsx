/**
 * `<PendingConsentBadge/>` — small "N consentimento(s) pendente(s)"
 * badge shown in `LayoutEnrichment.aiBadge` when the user has AI features
 * they haven't decided on yet.
 *
 * Null-renders when `pending === 0` so the layout slot stays empty when
 * there's nothing to nudge about. Clicking links to `/settings/ai`
 * (auto-mounted by the seed framework — see
 * `seed/frontend/framework/src/app.tsx`).
 *
 * Mounted by default via the framework layout factory — products do
 * NOT mount this themselves. Products that want different `aiBadge`
 * content pass an explicit override; products that want NO badge pass
 * `aiBadge: null` to opt out (the layout factory respects `null` as
 * explicit-empty vs. `undefined` as use-default).
 */
import { Link } from 'react-router-dom';
import { AlertCircle } from 'lucide-react';

import { useConsents } from './useConsents';

export interface PendingConsentBadgeProps {
  /** Optional className appended to the wrapper. */
  className?: string;
}

export function PendingConsentBadge({ className = '' }: PendingConsentBadgeProps) {
  const { data, isLoading, isError } = useConsents();

  // Silent on initial load + error — the badge is an ambient nudge, not a
  // critical surface. A failed catalog fetch does NOT block the layout.
  if (isLoading || isError) return null;
  const pending = data?.pending ?? 0;
  if (pending === 0) return null;

  return (
    <Link
      to="/settings/ai"
      className={`inline-flex items-center gap-1.5 rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-700 hover:bg-amber-500/20 dark:text-amber-400 ${className}`}
      title="Você tem consentimentos de IA pendentes — clique para revisar"
    >
      <AlertCircle className="h-3.5 w-3.5" aria-hidden="true" />
      <span>
        {pending} {pending === 1 ? 'consentimento pendente' : 'consentimentos pendentes'}
      </span>
    </Link>
  );
}

export default PendingConsentBadge;
