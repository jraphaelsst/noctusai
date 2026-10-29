/**
 * `<LeadDetailModal/>` -- one lead: view, edit, delete (with confirm) and "abrir conversa".
 *
 * Chrome from the seed `EntityDetailDialog`. The lead is read from the hooks by id, seeded by the `lead` the card
 * already holds (no skeleton flash on open); a refetch never replaces fields with a skeleton. Needs `ConfirmProvider`.
 */
import { Pencil, MessageCircle, Trash2 } from 'lucide-react';
import * as React from 'react';

import { EntityDetailDialog, type DetailAction } from '../components/detail/EntityDetailDialog';
import { useConfirm } from '../components/confirm/ConfirmProvider';
import { stageTagClasses } from '../components/pipeline/stageTokens';
import { Badge } from '../design-system/ui/Badge';
import { displayPhone, firstContactLabel, originLabel, stageLabel, stageOf, stageTagLabel } from './format';
import { errorMessage, type LeadsHooks } from './hooks';
import { t } from './i18n';
import { LeadFormDialog } from './LeadFormDialog';
import type { Lead } from './types';

export interface LeadDetailModalProps {
  hooks: LeadsHooks;
  /** The lead to show (a card / row the host already holds). `null` = closed. */
  lead: Lead | null;
  onClose: () => void;
  /** Host navigation to the conversation (shown only for a lead born from a WhatsApp chat). */
  onOpenConversation?: (lead: Lead) => void;
  /**
   * Host seam: extra footer actions for this lead (e.g. a product's "Ver paciente" on a closed lead). Rendered
   * between the organ's own actions and "Editar"; the host decides when each applies.
   */
  extraActions?: (lead: Lead) => DetailAction[];
}

export function LeadDetailModal({ hooks, lead: seed, onClose, onOpenConversation, extraActions }: LeadDetailModalProps) {
  const confirm = useConfirm();
  const { data: config } = hooks.useLeadsConfig();
  const fetched = hooks.useLead(seed?.id);
  const del = hooks.useDeleteLead();
  const [editing, setEditing] = React.useState(false);
  const [deleteError, setDeleteError] = React.useState<string | null>(null);

  const lead = fetched.data ?? seed;
  // Gone under us (deleted elsewhere): said, not rendered as an empty modal.
  const notFound = !!seed && fetched.isError && !fetched.data && /404|n[ãa]o encontrad/i.test(errorMessage(fetched.error));

  const remove = async () => {
    if (!lead) return;
    const ok = await confirm({
      title: t('detail.delete_title'),
      description: t('detail.delete_body'),
      confirmLabel: t('detail.delete_confirm'),
      tone: 'danger',
    });
    if (!ok) return;
    setDeleteError(null);
    del.mutate(lead.id, {
      onSuccess: onClose,
      onError: (err) => setDeleteError(`${t('detail.delete_error')} ${errorMessage(err)}`),
    });
  };

  const actions: DetailAction[] = lead
    ? [
        { label: t('detail.delete'), variant: 'destructive', align: 'start', icon: <Trash2 className="mr-1 h-4 w-4" />, onClick: remove, disabled: del.isPending, testId: 'lead-detail-delete' },
        ...(onOpenConversation && lead.whatsapp_chat_id
          ? [{ label: t('detail.open_chat'), variant: 'outline' as const, icon: <MessageCircle className="mr-1 h-4 w-4" />, onClick: () => onOpenConversation(lead), testId: 'lead-detail-open-chat' }]
          : []),
        ...(extraActions?.(lead) ?? []),
        { label: t('detail.edit'), variant: 'primary', icon: <Pencil className="mr-1 h-4 w-4" />, onClick: () => setEditing(true), testId: 'lead-detail-edit' },
      ]
    : [];

  return (
    <>
      <EntityDetailDialog
        open={!!seed && !editing}
        onClose={onClose}
        title={lead?.name ?? ''}
        subtitle={lead ? firstContactLabel(lead) && `${t('detail.first_contact')}: ${firstContactLabel(lead)}` : undefined}
        badges={
          lead
            ? [
                {
                  label: stageTagLabel(stageOf(config, lead.stage), lead.stage),
                  variant: 'outline',
                  className: stageTagClasses(stageOf(config, lead.stage)?.color),
                  testId: 'lead-detail-stage-tag',
                },
                { label: originLabel(config, lead.origin), variant: 'outline' },
              ]
            : []
        }
        note={deleteError ?? undefined}
        sections={
          lead
            ? [
                {
                  fields: [
                    { label: t('detail.phone'), value: displayPhone(lead.phone) },
                    { label: t('detail.email'), value: lead.email },
                    { label: t('detail.stage'), value: stageLabel(config, lead.stage) },
                    { label: t('detail.last_message'), value: lead.last_message_preview, wide: true },
                    { label: t('detail.notes'), value: lead.notes, wide: true },
                    {
                      label: t('detail.tags'),
                      value: (
                        <span className="flex flex-wrap gap-1" data-testid="lead-detail-tags">
                          {lead.tags.map((tag) => (
                            <Badge key={tag} variant="muted" className="font-normal">
                              {tag}
                            </Badge>
                          ))}
                        </span>
                      ),
                      wide: true,
                      hidden: lead.tags.length === 0,
                    },
                  ],
                },
              ]
            : []
        }
        notFound={notFound}
        error={notFound ? undefined : fetched.isError && !lead ? t('detail.error') : undefined}
        actions={actions}
        testId="lead-detail-modal"
      />
      <LeadFormDialog hooks={hooks} open={!!seed && editing} lead={lead ?? null} onClose={() => setEditing(false)} />
    </>
  );
}
