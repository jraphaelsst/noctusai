/**
 * `<LeadDetailModal/>` — the product's ONE lead detail view.
 *
 * Mounted by three surfaces (the Leads table, the Funil board, the
 * Processos board). Chrome comes from the seed organ
 * (`EntityDetailDialog`), the field list from `leadDetailSections` /
 * `campanhaDetailSections`. This file owns only the bit that is genuinely
 * social-wiring's: WHICH record to show, and how to get it.
 *
 * THREE WAYS TO NAME A LEAD, ONE MODAL
 * ------------------------------------
 * The surfaces do not hold the same thing:
 *
 *   `lead`     — the Leads table already has the whole row. Nothing to
 *                fetch; the modal opens instantly.
 *   `leadId`   — a Funil/Processos card carries an 8-column PROJECTION of
 *                the lead. It fetches the full record on open, which is why
 *                the organ has an `isLoading` state — rendering the missing
 *                columns as blank would assert "these are empty" about data
 *                that has not arrived.
 *   `campanha` — a campaign-origin card. There IS no `leads` row and no
 *                endpoint to fetch; the card's projection IS the record.
 *
 * `useLead(null)` is disabled, so the hook is always called (rules of
 * hooks) and only fires when a `leadId` was actually given.
 *
 * ACTIONS ARE THE CALLER'S
 * ------------------------
 * `onEdit`/`onDelete` come from the Leads page, which owns the form and the
 * confirm dialog. The boards pass `actions` of their own (archiving a
 * processo). Neither is baked in here: the same record has different
 * verbs available depending on where you opened it from.
 */
import { EntityDetailDialog } from '@noctusai/lib/components';
import type { DetailAction } from '@noctusai/lib/components';
import { Pencil, Trash2 } from 'lucide-react';

import { useLead } from '@/hooks/useLeads';
import { useLeadSources } from '@/hooks/useLeadsSources';
import {
  campanhaDetailSections,
  explainNeedsReview,
  leadDetailSections,
} from '@/pages/leads/leadDetailSections';
import type { Lead } from '@/pages/leads/types';
import type { AtendimentoCampanha } from '@/types/pipeline';

export interface LeadDetailModalProps {
  open: boolean;
  onClose: () => void;
  /** The full record, when the surface already holds it (the Leads table). */
  lead?: Lead | null;
  /** Fetch the record by id (a board card, lead origin). */
  leadId?: string | null;
  /** Render straight from the card's projection (a board card, campaign origin). */
  campanha?: AtendimentoCampanha | null;
  /** Prepended to the footer — e.g. "Arquivar" on the Processos board. */
  actions?: DetailAction[];
  onEdit?: (lead: Lead) => void;
  onDelete?: (lead: Lead) => void;
}

export function LeadDetailModal({
  open,
  onClose,
  lead,
  leadId,
  campanha,
  actions = [],
  onEdit,
  onDelete,
}: LeadDetailModalProps) {
  // Only fetch when the caller gave an id AND held no record — passing both
  // would spend a round trip re-fetching what we already have.
  const shouldFetch = open && !lead && !!leadId;
  const fetched = useLead(shouldFetch ? (leadId as string) : null);
  const { data: sources } = useLeadSources();

  const resolved = lead ?? fetched.data ?? null;

  if (campanha) {
    return (
      <EntityDetailDialog
        open={open}
        onClose={onClose}
        title={campanha.full_name || campanha.email || campanha.phone || 'Lead de campanha'}
        subtitle={campanha.campaign_name ?? undefined}
        badges={[{ label: 'Campanha', variant: 'muted' }]}
        sections={campanhaDetailSections(campanha)}
        actions={actions}
        testId="lead-detail-modal"
      />
    );
  }

  return (
    <EntityDetailDialog
      open={open}
      onClose={onClose}
      title={resolved?.cliente_nome || 'Lead sem nome'}
      badges={
        resolved?.needs_review ? [{ label: 'Revisar', variant: 'destructive' as const }] : []
      }
      note={resolved?.needs_review ? explainNeedsReview(resolved, sources) : undefined}
      sections={resolved ? leadDetailSections(resolved) : []}
      // `fetched.isPending` alone — NOT `isPending || isFetching`. The
      // organ (`EntityDetailDialog`, seed/lib/frontend/src/components/detail/
      // EntityDetailDialog.tsx) takes exactly one `isLoading` boolean and
      // swaps `<SkeletonGrid/>` in over the field grid whenever it's true,
      // with no data-presence check of its own — so passing `isFetching`
      // here replaced a fully-rendered lead with a skeleton on every
      // background refetch, even though `resolved` still held the record.
      // `fetched.isPending` already means "no data has ever landed for this
      // leadId" (this hook sets no `placeholderData`), so it goes false
      // after the first fetch and stays false through every later refetch
      // for the same id. (KB § PATTERNS/frontend/lying-loading-state.md)
      isLoading={shouldFetch && fetched.isPending}
      error={
        fetched.isError
          ? `Erro ao carregar o lead: ${(fetched.error as Error)?.message ?? 'tente novamente.'}`
          : undefined
      }
      // Fetch finished, no record: the lead was deleted under us, or the card
      // points at an id that no longer exists. Distinct from "still loading",
      // and the user deserves to be told which.
      //
      // `!shouldFetch` is part of the condition, not an oversight. A disabled
      // TanStack v5 query reports `isPending: true` forever, so without it a
      // card carrying NEITHER origin (no lead_id, no campanha — the join
      // failed to load) would fall through every branch and render a modal
      // with a title and nothing else: no fields, no spinner, no error. An
      // empty modal that explains nothing is the silent-failure shape.
      notFound={
        !resolved &&
        !fetched.isError &&
        (!shouldFetch || (!fetched.isPending && !fetched.isFetching))
      }
      actions={[
        ...actions,
        ...(resolved && onDelete
          ? [
              {
                label: 'Excluir',
                variant: 'destructive' as const,
                align: 'start' as const,
                icon: <Trash2 className="mr-1 h-4 w-4" />,
                onClick: () => onDelete(resolved),
                testId: 'lead-detail-delete',
              },
            ]
          : []),
        ...(resolved && onEdit
          ? [
              {
                label: 'Editar',
                variant: 'primary' as const,
                icon: <Pencil className="mr-1 h-4 w-4" />,
                onClick: () => onEdit(resolved),
                testId: 'lead-detail-edit',
              },
            ]
          : []),
      ]}
      testId="lead-detail-modal"
    />
  );
}
