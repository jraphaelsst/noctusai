/**
 * `<SessionDetailDialog/>` -- one session opened: when / status / charge, the quick status switch, "Remarcar", the
 * ADMINISTRATIVE note ("observações": rescheduled, arrived late -- seen by whoever manages the agenda), the CLINICAL
 * note ("anotações": the therapist's, shown ONLY to the therapist), the payment of this session and its history.
 *
 * 🔴 The clinical note is sensitive health data (LGPD art. 11). The server gates it (403 for any other role) and keeps
 * it out of every list; this dialog fetches it on its own, shows NOTHING of it when the server refuses (no placeholder,
 * no error), and drops it from the cache as soon as the dialog closes (`useClinicalNote` has `gcTime: 0`).
 */
import { Pencil, Wallet } from 'lucide-react';
import * as React from 'react';
import { toast } from 'sonner';

import { stageTagClasses } from '../components/pipeline/stageTokens';
import { Button } from '../design-system/ui/Button';
import { Dialog, DialogBody, DialogFooter, DialogHeader } from '../design-system/ui/Dialog';
import { cn } from '../utils';
import { formatCents } from '../organ-kit/money';
import { PaymentForm } from './ClientFinanceTab';
import { EmptyState, Field, FormError, Input, ListSkeleton, RefreshingBar, RetryError, Select, Textarea } from './controls';
import { CHARGE_STATUS, formatWhen, optionOf, todayIn, tzOf, zonedIso, zonedParts } from './format';
import { errorMessage, type ClientsHooks } from './hooks';
import { t } from './i18n';
import { clientsErrorText, nounVars, ToneBadge } from './parts';
import { SessionFormDialog } from './SessionFormDialog';
import type { ClientEvent, Session } from './types';

export interface SessionDetailDialogProps {
  hooks: ClientsHooks;
  open: boolean;
  onClose: () => void;
  /** `null` while closed. */
  session: Session | null;
  /** UX gate only (the server enforces admin on payments). */
  isAdmin?: boolean;
  /** Shown when the host can navigate to the client (agenda). */
  onOpenClient?: (clientId: string) => void;
}

/** One history line in pt-BR; an unknown kind shows its slug (never blank). */
export function eventText(e: ClientEvent, statusLabel: (slug: string) => string): string {
  const vars: Record<string, string> = {
    from: statusLabel(e.from ?? ''),
    to: statusLabel(e.to ?? ''),
    method: String(e.data.method ?? e.to ?? ''),
    amount: typeof e.data.amount_cents === 'number' ? formatCents(e.data.amount_cents) : '',
  };
  const text = t(`event.${e.kind}`, vars);
  return text === `event.${e.kind}` ? e.kind : text;
}

function PaymentDialog({ hooks, session, onClose }: { hooks: ClientsHooks; session: Session; onClose: () => void }) {
  const client = hooks.useClient(session.client_id);
  const finance = hooks.useClientFinance(session.client_id);
  if (client.showSkeleton || finance.showSkeleton) return <ListSkeleton rows={3} />;
  if (!client.data || !finance.data) {
    return <RetryError message={`${t('finance.error')} ${errorMessage(finance.error ?? client.error)}`} onRetry={() => { void client.refetch(); void finance.refetch(); }} retryLabel={t('common.retry')} />;
  }
  return <PaymentForm hooks={hooks} client={client.data} finance={finance.data} initialEntryIds={session.entry_id ? [session.entry_id] : undefined} onClose={onClose} />;
}

function Body({ hooks, session, onClose, isAdmin, onEdit }: { hooks: ClientsHooks; session: Session; onClose: () => void; isAdmin: boolean; onEdit: () => void }) {
  const { data: config } = hooks.useClientsConfig();
  const tz = tzOf(config);
  const vars = nounVars(config);
  const update = hooks.useUpdateSession();
  const reschedule = hooks.useRescheduleSession();
  const saveNote = hooks.useSaveClinicalNote();
  const note = hooks.useClinicalNote(session.id, config?.clinical_notes === true);
  const events = hooks.useSessionEvents(session.id);
  const at = zonedParts(session.starts_at, tz);
  const status = optionOf(config?.session_statuses, session.status);
  const charge = session.charge_status ? CHARGE_STATUS[session.charge_status] : null;
  const [adminNotes, setAdminNotes] = React.useState(session.notes ?? '');
  const [clinicalDraft, setClinicalDraft] = React.useState<string | null>(null);
  const [moving, setMoving] = React.useState(false);
  const [newDate, setNewDate] = React.useState(at?.date ?? todayIn(tz));
  const [newTime, setNewTime] = React.useState(at?.time ?? '');
  const [error, setError] = React.useState<string | null>(null);
  const [clinicalError, setClinicalError] = React.useState<string | null>(null);
  const [paying, setPaying] = React.useState(false);
  const statusLabel = (slug: string) => optionOf(config?.session_statuses, slug).label;

  const changeStatus = (next: string) => {
    setError(null);
    update.mutate({ id: session.id, client_id: session.client_id, status: next }, { onError: (err) => setError(clientsErrorText(err, 'detail_dialog.status_error', vars)) });
  };
  const saveAdminNotes = () => {
    setError(null);
    update.mutate(
      { id: session.id, client_id: session.client_id, notes: adminNotes.trim() || null },
      { onSuccess: () => toast.success(t('detail_dialog.admin_notes_saved')), onError: (err) => setError(clientsErrorText(err, 'form.error', vars)) },
    );
  };
  const move = () => {
    const starts_at = zonedIso(newDate, newTime, tz);
    if (!starts_at) return setError(t('session_form.when_required'));
    setError(null);
    reschedule.mutate(
      { id: session.id, client_id: session.client_id, starts_at },
      { onSuccess: onClose, onError: (err) => setError(clientsErrorText(err, 'detail_dialog.reschedule_error', vars)) },
    );
  };
  const saveClinical = () => {
    const body = (clinicalDraft ?? note.data?.body ?? '').trim();
    if (!body) return setClinicalError(t('detail_dialog.clinical_empty'));
    setClinicalError(null);
    saveNote.mutate(
      { sessionId: session.id, body },
      { onSuccess: () => { setClinicalDraft(null); toast.success(t('detail_dialog.clinical_saved')); }, onError: (err) => setClinicalError(clientsErrorText(err, 'form.error', vars)) },
    );
  };

  const owes = session.charge_status === 'pendente' && config?.finance_enabled !== false;

  return (
    <div data-testid="session-detail">
      <DialogHeader>
        <h2 className="text-lg font-semibold">{t('detail_dialog.title')}</h2>
        <p className="text-sm text-muted-foreground">
          {session.client_name} · {formatWhen(session.starts_at, tz)} · {t('sessions.minutes', { n: session.duration_min })}
        </p>
      </DialogHeader>
      <DialogBody className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <Field label={t('detail_dialog.status')}>
            <Select
              value={session.status}
              onChange={(e) => changeStatus(e.target.value)}
              disabled={update.isPending}
              className={cn('font-semibold', stageTagClasses(status.color))}
              data-testid="detail-status"
            >
              {(config?.session_statuses ?? [status]).map((o) => (
                <option key={o.slug} value={o.slug}>
                  {o.label}
                </option>
              ))}
            </Select>
          </Field>
          {charge && (
            <ToneBadge color={charge.color} testId="detail-charge">
              {charge.label}
              {session.amount_cents != null ? ` · ${formatCents(session.amount_cents)}` : ''}
            </ToneBadge>
          )}
          <Button type="button" variant="outline" size="sm" onClick={() => setMoving((v) => !v)} data-testid="detail-reschedule-toggle">
            {t('detail_dialog.reschedule')}
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={onEdit} data-testid="detail-edit">
            <Pencil className="mr-1 h-3.5 w-3.5" />
            {t('detail_dialog.edit')}
          </Button>
        </div>
        {moving && (
          <div className="grid grid-cols-[1fr_1fr_auto] items-end gap-2 rounded-md border p-3" data-testid="detail-reschedule">
            <Field label={t('session_form.date')}>
              <Input type="date" value={newDate} onChange={(e) => setNewDate(e.target.value)} />
            </Field>
            <Field label={t('session_form.time')}>
              <Input type="time" value={newTime} onChange={(e) => setNewTime(e.target.value)} />
            </Field>
            <Button type="button" onClick={move} disabled={reschedule.isPending} data-testid="detail-reschedule-confirm">
              {reschedule.isPending ? t('common.saving') : t('detail_dialog.reschedule_confirm')}
            </Button>
          </div>
        )}
        <FormError message={error} />

        <section className="space-y-1" data-testid="detail-admin-notes">
          <Field label={t('detail_dialog.admin_notes')}>
            <Textarea value={adminNotes} onChange={(e) => setAdminNotes(e.target.value)} rows={2} maxLength={5000} />
          </Field>
          <p className="text-xs text-muted-foreground">{t('detail_dialog.admin_notes_hint')}</p>
          <Button type="button" size="sm" variant="outline" onClick={saveAdminNotes} disabled={update.isPending || (adminNotes.trim() || null) === (session.notes ?? null)} data-testid="detail-admin-notes-save">
            {t('detail_dialog.admin_notes_save')}
          </Button>
        </section>

        {config?.clinical_notes && !note.forbidden && (
          <section className="space-y-1 rounded-md border border-dashed p-3" data-testid="detail-clinical">
            <h3 className="text-sm font-semibold">{t('detail_dialog.clinical')}</h3>
            <p className="text-xs text-muted-foreground">{t('detail_dialog.clinical_hint')}</p>
            {note.showSkeleton ? (
              <ListSkeleton rows={2} />
            ) : note.isError && !note.data ? (
              <RetryError message={`${t('detail_dialog.clinical_error')} ${errorMessage(note.error)}`} onRetry={() => void note.refetch()} retryLabel={t('common.retry')} />
            ) : (
              <>
                <Textarea
                  value={clinicalDraft ?? note.data?.body ?? ''}
                  onChange={(e) => setClinicalDraft(e.target.value)}
                  rows={6}
                  maxLength={20000}
                  placeholder={t('detail_dialog.clinical_placeholder')}
                  aria-label={t('detail_dialog.clinical')}
                  data-testid="detail-clinical-text"
                />
                <FormError message={clinicalError} />
                <Button type="button" size="sm" onClick={saveClinical} disabled={saveNote.isPending || clinicalDraft === null} data-testid="detail-clinical-save">
                  {saveNote.isPending ? t('common.saving') : t('detail_dialog.clinical_save')}
                </Button>
              </>
            )}
          </section>
        )}

        {config?.finance_enabled !== false && (
          <section className="space-y-1" data-testid="detail-payment">
            <h3 className="text-sm font-semibold">{t('detail_dialog.payment')}</h3>
            {session.charge_status === null || session.charge_status === 'cancelado' || session.charge_status === 'isento' ? (
              <p className="text-xs text-muted-foreground">
                {session.charge_status === null ? t('detail_dialog.payment_none') : charge?.label}
              </p>
            ) : (
              <p className="text-sm">
                {t('detail_dialog.payment_amount')}: {formatCents(session.amount_cents ?? 0)} · {t('detail_dialog.payment_settled')}: {formatCents(session.settled_cents)}
              </p>
            )}
            {owes && isAdmin && (
              <Button type="button" size="sm" onClick={() => setPaying(true)} data-testid="detail-pay">
                <Wallet className="mr-1 h-4 w-4" />
                {t('finance.pay')}
              </Button>
            )}
            {owes && !isAdmin && <p className="text-xs text-muted-foreground">{t('finance.pay_admin_only')}</p>}
          </section>
        )}

        <section className="space-y-1" data-testid="detail-history">
          <h3 className="text-sm font-semibold">{t('detail_dialog.history')}</h3>
          <RefreshingBar active={events.isRefreshing} label={t('common.refreshing')} />
          {events.showSkeleton ? (
            <ListSkeleton rows={2} />
          ) : events.isError && !events.data ? (
            <RetryError message={`${t('detail_dialog.history_error')} ${errorMessage(events.error)}`} onRetry={() => void events.refetch()} retryLabel={t('common.retry')} />
          ) : (events.data ?? []).length === 0 ? (
            <EmptyState message={t('detail_dialog.history_empty')} />
          ) : (
            <ul className="space-y-0.5 text-xs text-muted-foreground">
              {(events.data ?? []).map((e) => (
                <li key={e.id} data-testid={`event-${e.kind}`}>
                  <span className="tabular-nums">{formatWhen(e.occurred_at, tz)}</span> · {eventText(e, statusLabel)}
                </li>
              ))}
            </ul>
          )}
        </section>
      </DialogBody>
      <DialogFooter className="gap-2">
        <Button type="button" variant="ghost" onClick={onClose}>
          {t('detail_dialog.close')}
        </Button>
      </DialogFooter>
      {paying && (
        <Dialog open onClose={() => setPaying(false)} title={t('payment.title')}>
          <PaymentDialog hooks={hooks} session={session} onClose={() => setPaying(false)} />
        </Dialog>
      )}
    </div>
  );
}

export function SessionDetailDialog({ hooks, open, onClose, session, isAdmin = false, onOpenClient }: SessionDetailDialogProps) {
  const [editing, setEditing] = React.useState(false);
  React.useEffect(() => {
    if (!open) setEditing(false);
  }, [open]);
  return (
    <>
      <Dialog open={open && !!session && !editing} onClose={onClose} title={t('detail_dialog.title')}>
        {session && <Body key={session.id} hooks={hooks} session={session} onClose={onClose} isAdmin={isAdmin} onEdit={() => setEditing(true)} />}
      </Dialog>
      <SessionFormDialog
        hooks={hooks}
        open={open && editing}
        onClose={() => setEditing(false)}
        clientId={session?.client_id ?? ''}
        session={session}
        onOpenClient={
          onOpenClient
            ? (id) => {
                setEditing(false);
                onClose();
                onOpenClient(id);
              }
            : undefined
        }
      />
    </>
  );
}
