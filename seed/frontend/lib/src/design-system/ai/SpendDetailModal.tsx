/**
 * `<SpendDetailModal/>` — minimal admin modal showing the full spend
 * status when the user clicks `<LLMSpendBadge/>` and no
 * `onOpenDetail` override is configured.
 *
 * Renders the status dict + a hint about the budget endpoint. Doesn't
 * mutate budget — that's a separate admin page (out of scope for
 * `llm-spend-badge-mount`; can be a follow-up `admin-llm-spend-page`
 * project if needed).
 *
 * Tailwind-only; no portal — the modal is a fixed overlay. Closes on
 * escape, backdrop click, or the close button.
 */
import { useEffect } from 'react';
import { X } from 'lucide-react';

import type { LLMSpendResponse, SpendStatus } from './useLLMSpend';

export interface SpendDetailModalProps {
  open: boolean;
  onClose: () => void;
  data: LLMSpendResponse;
}

const STATUS_LABEL: Record<SpendStatus, string> = {
  unset: 'Sem orçamento configurado',
  ok: 'Dentro do orçamento',
  warn: 'Aproximando do limite',
  hard_stop: 'Limite atingido — chamadas de IA bloqueadas',
};

function _formatBRL(value: number | null): string {
  if (value == null) return '—';
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(value);
}

function _formatPct(value: number | null): string {
  if (value == null) return '—';
  return `${value.toFixed(1)}%`;
}

export function SpendDetailModal({ open, onClose, data }: SpendDetailModalProps) {
  // Escape closes; cleanup on unmount.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="spend-detail-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg border border-border bg-background p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 id="spend-detail-title" className="text-lg font-semibold text-foreground">
            Consumo de IA — mês corrente
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fechar"
            className="rounded-md p-1 text-muted-foreground hover:bg-muted"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <dl className="space-y-2 text-sm">
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Status</dt>
            <dd className="font-medium text-foreground">{STATUS_LABEL[data.status]}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Gasto</dt>
            <dd className="font-medium text-foreground">{_formatBRL(data.spent_brl)}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Orçamento</dt>
            <dd className="font-medium text-foreground">{_formatBRL(data.budget_brl)}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">% utilizado</dt>
            <dd className="font-medium text-foreground">{_formatPct(data.used_pct)}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Limite leve / hard</dt>
            <dd className="font-medium text-foreground">
              {(data.soft_pct * 100).toFixed(0)}% / {(data.hard_pct * 100).toFixed(0)}%
            </dd>
          </div>
        </dl>
        <p className="mt-4 text-xs text-muted-foreground">
          Para alterar o orçamento mensal, use o endpoint admin{' '}
          <code className="rounded bg-muted px-1 py-0.5 text-[11px]">
            PUT /api/admin/llm-spend/{'{org_id}'}/budget
          </code>{' '}
          ou a página de administração da plataforma.
        </p>
      </div>
    </div>
  );
}

export default SpendDetailModal;
