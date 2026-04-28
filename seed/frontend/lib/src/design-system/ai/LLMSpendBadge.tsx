/**
 * `<LLMSpendBadge/>` — admin-only chip surfacing the org's LLM spend
 * status in `LayoutEnrichment.aiBadge`. Default-mounted by the seed
 * framework via the `<AIBadgeStack/>` default.
 *
 * **Render behavior by spend status:**
 *   - `unset`     → null-render (no budget configured; nothing to surface).
 *   - `ok`        → null-render (under soft threshold; ambient signal off).
 *   - `warn`      → yellow chip "IA NN% (R$x / R$y)" — admin sees the
 *                   approach to hard-stop before it fires.
 *   - `hard_stop` → red chip "Limite IA atingido" — calls become 429s.
 *
 * **Admin-only visibility.** Reads `useAuthStore` (via `@noctusai/seed/infra`)
 * to extract `org_id` + admin role from the user's metadata. Non-admins
 * see nothing. The hook itself is `enabled: false` for non-admins so
 * we don't even fetch.
 *
 * **Click target.** `onClick` fires `onOpenDetail(orgId)` if provided
 * (lets products route to their own admin spend page) — otherwise falls
 * back to a `<SpendDetailModal/>` which renders the full status dict
 * inline. Default-on UX: clicking shows context without leaving the
 * current page.
 */
import { useState } from 'react';
import { useAuthStore } from '@noctusai/seed/infra';
import { resolveSSORoles } from '@noctusai/lib';

import { useLLMSpend, type SpendStatus } from './useLLMSpend';
import { SpendDetailModal } from './SpendDetailModal';

export interface LLMSpendBadgeProps {
  /**
   * Optional override: products with their own `/admin/llm-spend` page can
   * route the click there. When omitted, the badge opens the inline modal.
   */
  onOpenDetail?: (orgId: string) => void;
  /** Optional className appended to the wrapper. */
  className?: string;
}

function _formatBRL(value: number | null | undefined): string {
  if (value == null) return '—';
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(value);
}

export function LLMSpendBadge({ onOpenDetail, className = '' }: LLMSpendBadgeProps) {
  const auth = useAuthStore();
  const user = (auth as { user?: { user_metadata?: Record<string, unknown> } | null })?.user ?? null;
  const metadata = user?.user_metadata ?? null;
  const { isProductAdmin } = resolveSSORoles(metadata as Record<string, unknown> | null);
  const orgId = (metadata?.org_id as string | undefined) ?? null;

  const { data } = useLLMSpend(orgId, isProductAdmin);
  const [modalOpen, setModalOpen] = useState(false);

  // Non-admin / unset / ok / no-data → silent.
  if (!isProductAdmin || !orgId || !data) return null;
  if (data.status === 'ok' || data.status === 'unset') return null;

  const isHard = data.status === 'hard_stop';
  const tone = isHard
    ? 'border-destructive/40 bg-destructive/10 text-destructive'
    : 'border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400';

  const label = isHard
    ? `Limite IA atingido (${_formatBRL(data.spent_brl)} / ${_formatBRL(data.budget_brl)})`
    : `IA ${data.used_pct?.toFixed(0) ?? '?'}% (${_formatBRL(data.spent_brl)} / ${_formatBRL(data.budget_brl)})`;

  const handleClick = () => {
    if (onOpenDetail) {
      onOpenDetail(orgId);
    } else {
      setModalOpen(true);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={handleClick}
        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium hover:opacity-80 transition-opacity ${tone} ${className}`}
        title="Detalhes do consumo de IA"
      >
        <span>{label}</span>
      </button>
      <SpendDetailModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        data={data}
      />
    </>
  );
}

export default LLMSpendBadge;

// Re-export the status type for convenience.
export type { SpendStatus };
