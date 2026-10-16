/**
 * `<RemindersPage/>` — billing reminders (dunning) for the finance organ: the master switch, the rules editor
 * (template with variable chips), "what goes out today" (the exact preview of the daily job) and the sent log.
 *
 * Reminders are OFF per org until an admin switches them on (the first enable seeds the default rules). `isAdmin` is a UX
 * gate only — the server enforces every write. Server messages (an unknown `{variable}` is a 422 with the offending
 * names) are rendered as-is next to the form. Product-agnostic: the host passes its authenticated api client (or hooks).
 */
import * as React from 'react';
import { Badge } from '../design-system/ui/Badge';
import { Button } from '../design-system/ui/Button';
import { Switch } from '../design-system/ui/switch';
import { ConfirmButton, EmptyState, Field, FormError, Input, ListSkeleton, Notice, PageHeader, Pager, RefreshingBar, RetryError, Select, Textarea, totalPagesOf } from './controls';
import { formatDate } from './format';
import { t } from './i18n';
import { errorMessage } from '../organ-kit/query';
import type { OrganApi } from '../organ-kit/query';
import { createFinanceReminderHooks, type FinanceReminderHooks } from './reminderHooks';
import { REMINDER_LOG_STATUSES, REMINDER_VARIABLES, type ReminderLogStatus, type ReminderRule } from './reminderTypes';

export type RemindersPageProps = {
  isAdmin?: boolean;
  /** Optional wrapper class. */
  className?: string;
} & ({ hooks: FinanceReminderHooks; api?: never } | { api: OrganApi; hooks?: never });

type Tab = 'rules' | 'today' | 'log';
const TABS: readonly Tab[] = ['rules', 'today', 'log'];

/** `-3` → "3 dias antes"; `0` → "No dia do vencimento"; `7` → "7 dias depois". */
export function offsetLabel(days: number): string {
  if (days === 0) return t('reminders.offset_on');
  if (days < 0) return days === -1 ? t('reminders.offset_before_one') : t('reminders.offset_before', { n: -days });
  return days === 1 ? t('reminders.offset_after_one') : t('reminders.offset_after', { n: days });
}

export function RemindersPage({ isAdmin = false, className, hooks, api }: RemindersPageProps) {
  const built = React.useMemo(() => hooks ?? createFinanceReminderHooks(api as OrganApi), [hooks, api]);
  const settings = built.useReminderSettings();
  const save = built.useSaveReminderSettings();
  const [tab, setTab] = React.useState<Tab>('rules');

  if (settings.showSkeleton) return <ListSkeleton />;
  if (settings.isError && !settings.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(settings.error)}`} onRetry={() => settings.refetch()} retryLabel={t('common.retry')} />;
  }
  const enabled = !!settings.data?.enabled;

  return (
    <section className={className ?? 'space-y-4'} aria-busy={settings.isRefreshing}>
      <PageHeader
        title={t('reminders.title')}
        subtitle={t('reminders.subtitle')}
        actions={
          <label className="flex items-center gap-2 text-sm">
            <Switch
              aria-label={t('reminders.enabled')}
              checked={enabled}
              disabled={!isAdmin || save.isPending}
              onCheckedChange={(v) => save.mutate({ enabled: v })}
            />
            <span>{t('reminders.enabled')}</span>
          </label>
        }
      />
      <RefreshingBar active={settings.isRefreshing} label={t('common.refreshing')} />
      <FormError message={save.error ? errorMessage(save.error) : null} />
      {!enabled ? <Notice tone="warning">{t('reminders.off_notice')}</Notice> : <p className="text-xs text-muted-foreground">{t('reminders.enabled_help')}</p>}

      <div role="tablist" aria-label={t('reminders.tabs_label')} className="flex gap-1 border-b">
        {TABS.map((k) => (
          <button
            key={k}
            type="button"
            role="tab"
            id={`reminders-tab-${k}`}
            aria-selected={tab === k}
            aria-controls={`reminders-panel-${k}`}
            onClick={() => setTab(k)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${tab === k ? 'border-primary font-medium' : 'border-transparent text-muted-foreground'}`}
          >
            {t(`reminders.tab_${k}`)}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`reminders-panel-${tab}`} aria-labelledby={`reminders-tab-${tab}`}>
        {tab === 'rules' ? <RulesEditor hooks={built} isAdmin={isAdmin} /> : null}
        {tab === 'today' ? <TodayPreview hooks={built} isAdmin={isAdmin} enabled={enabled} /> : null}
        {tab === 'log' ? <SentLog hooks={built} /> : null}
      </div>
    </section>
  );
}

// ---- rules -----------------------------------------------------------------------------------------------

function RulesEditor({ hooks, isAdmin }: { hooks: FinanceReminderHooks; isAdmin: boolean }) {
  const rules = hooks.useReminderRules();
  const m = hooks.useReminderRuleMutations();
  const [editing, setEditing] = React.useState<ReminderRule | 'new' | null>(null);
  const [offset, setOffset] = React.useState('');
  const [template, setTemplate] = React.useState('');
  const [active, setActive] = React.useState(true);
  const [fieldError, setFieldError] = React.useState<string | null>(null);
  const area = React.useRef<HTMLTextAreaElement>(null);

  function open(rule: ReminderRule | null) {
    setEditing(rule ?? 'new');
    setOffset(rule ? String(rule.offset_days) : '');
    setTemplate(rule?.template ?? '');
    setActive(rule?.enabled ?? true);
    setFieldError(null);
    m.create.reset();
    m.update.reset();
  }

  function insertVariable(name: string) {
    const token = `{${name}}`;
    const el = area.current;
    const start = el?.selectionStart ?? template.length;
    const end = el?.selectionEnd ?? template.length;
    const next = template.slice(0, start) + token + template.slice(end);
    setTemplate(next);
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(start + token.length, start + token.length);
    });
  }

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    const days = Number(offset);
    if (offset.trim() === '' || !Number.isInteger(days)) return setFieldError(t('reminders.offset_invalid'));
    if (!template.trim()) return setFieldError(t('reminders.template_empty'));
    setFieldError(null);
    try {
      if (editing === 'new') await m.create.mutateAsync({ offset_days: days, template: template.trim(), enabled: active });
      else if (editing) await m.update.mutateAsync({ id: editing.id, offset_days: days, template: template.trim(), enabled: active });
      setEditing(null);
    } catch {
      // Rendered below from the mutation error (the server's pt-BR message).
    }
  }

  if (rules.showSkeleton) return <ListSkeleton />;
  if (rules.isError && !rules.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(rules.error)}`} onRetry={() => rules.refetch()} retryLabel={t('common.retry')} />;
  }
  const list = [...(rules.data ?? [])].sort((a, b) => a.offset_days - b.offset_days);
  const mutErr = m.create.error ?? m.update.error ?? m.remove.error ?? m.addDefaults.error;

  return (
    <div className="space-y-3" aria-busy={rules.isRefreshing}>
      <RefreshingBar active={rules.isRefreshing} label={t('common.refreshing')} />
      {isAdmin ? (
        <div className="flex gap-2">
          <Button size="sm" onClick={() => open(null)}>{t('reminders.add_rule')}</Button>
          <Button size="sm" variant="outline" disabled={m.addDefaults.isPending} onClick={() => m.addDefaults.mutate()}>{t('reminders.add_defaults')}</Button>
        </div>
      ) : null}
      {editing === null ? <FormError message={mutErr ? errorMessage(mutErr) : null} /> : null}
      {list.length === 0 && editing === null ? <EmptyState message={t('reminders.rules_empty')} /> : null}
      {list.length > 0 ? (
        <ul className="space-y-2">
          {list.map((r) => (
            <li key={r.id} className={`rounded-md border p-3 ${r.enabled ? '' : 'opacity-60'}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-medium">{offsetLabel(r.offset_days)}</span>
                <span className="flex items-center gap-2">
                  <Switch
                    aria-label={`${t('reminders.rule_enabled')}: ${offsetLabel(r.offset_days)}`}
                    checked={r.enabled}
                    disabled={!isAdmin || m.update.isPending}
                    onCheckedChange={(v) => m.update.mutate({ id: r.id, enabled: v })}
                  />
                  {isAdmin ? (
                    <>
                      <Button size="sm" variant="ghost" onClick={() => open(r)}>{t('common.edit')}</Button>
                      <ConfirmButton label={t('reminders.delete_rule')} confirmLabel={t('reminders.delete_confirm')} pending={m.remove.isPending} onConfirm={() => m.remove.mutateAsync(r.id).catch(() => undefined)} />
                    </>
                  ) : null}
                </span>
              </div>
              <p className="mt-1 whitespace-pre-wrap text-sm text-muted-foreground">{r.template}</p>
            </li>
          ))}
        </ul>
      ) : null}
      {editing !== null && isAdmin ? (
        <form aria-label={t('reminders.rule_form')} onSubmit={submit} className="space-y-3 rounded-md border p-3">
          <h3 className="text-sm font-semibold">{editing === 'new' ? t('reminders.add_rule') : t('reminders.edit_rule')}</h3>
          <Field label={t('reminders.offset_label')} required error={fieldError === t('reminders.offset_invalid') ? fieldError : null}>
            <Input type="number" step={1} value={offset} onChange={(e) => setOffset(e.target.value)} />
          </Field>
          <p className="text-xs text-muted-foreground">{t('reminders.offset_help')}</p>
          <Field label={t('reminders.template_label')} required error={fieldError === t('reminders.template_empty') ? fieldError : null}>
            <Textarea ref={area} rows={5} value={template} onChange={(e) => setTemplate(e.target.value)} />
          </Field>
          <div className="space-y-1" role="group" aria-label={t('reminders.variables')}>
            <span className="text-xs text-muted-foreground">{t('reminders.variables')}</span>
            <div className="flex flex-wrap gap-1">
              {REMINDER_VARIABLES.map((v) => (
                <button key={v} type="button" onClick={() => insertVariable(v)} className="rounded-full border px-2 py-0.5 font-mono text-xs hover:bg-muted">{`{${v}}`}</button>
              ))}
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
            <span>{t('reminders.rule_enabled')}</span>
          </label>
          <FormError message={mutErr ? errorMessage(mutErr) : null} />
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={m.create.isPending || m.update.isPending}>{m.create.isPending || m.update.isPending ? t('common.saving') : t('common.save')}</Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(null)}>{t('common.cancel')}</Button>
          </div>
        </form>
      ) : null}
    </div>
  );
}

// ---- today ------------------------------------------------------------------------------------------------

function TodayPreview({ hooks, isAdmin, enabled }: { hooks: FinanceReminderHooks; isAdmin: boolean; enabled: boolean }) {
  const preview = hooks.useReminderPreview();
  const optOut = hooks.useReceivableOptOut();
  if (preview.showSkeleton) return <ListSkeleton />;
  if (preview.isError && !preview.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(preview.error)}`} onRetry={() => preview.refetch()} retryLabel={t('common.retry')} />;
  }
  const data = preview.data;
  if (!enabled) return <EmptyState message={t('reminders.today_off')} />;
  if (!data || (data.planned.length === 0 && data.skipped.length === 0)) return <EmptyState message={t('reminders.today_empty')} />;
  return (
    <div className="space-y-4" aria-busy={preview.isRefreshing}>
      <RefreshingBar active={preview.isRefreshing} label={t('common.refreshing')} />
      <FormError message={optOut.error ? errorMessage(optOut.error) : null} />
      {data.planned.length > 0 ? (
        <div className="space-y-1">
          <h3 className="text-sm font-semibold">{t('reminders.today_planned')} ({data.planned.length})</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="p-2">{t('reminders.col_receivable')}</th>
                <th className="p-2">{t('reminders.col_rule')}</th>
                <th className="p-2">{t('reminders.col_recipient')}</th>
                <th className="p-2">{t('reminders.col_message')}</th>
                <th className="p-2"><span className="sr-only">{t('common.actions')}</span></th>
              </tr>
            </thead>
            <tbody>
              {data.planned.map((p) => (
                <tr key={`${p.entry_id}:${p.rule_id}`} className="border-b align-top">
                  <td className="p-2">{p.description ?? '—'}<span className="block text-xs text-muted-foreground">{formatDate(p.cycle_date)}</span></td>
                  <td className="p-2">{offsetLabel(p.offset_days)}</td>
                  <td className="p-2 whitespace-nowrap">{p.recipient}</td>
                  <td className="p-2 whitespace-pre-wrap">
                    {p.text}
                    {p.already ? <Badge variant="muted" className="ml-1">{t('reminders.already', { status: t(`reminders.status.${p.already}`) })}</Badge> : null}
                  </td>
                  <td className="p-2 text-right">
                    {isAdmin ? <Button size="sm" variant="ghost" disabled={optOut.isPending} onClick={() => optOut.mutate({ entryId: p.entry_id, optOut: true })}>{t('reminders.opt_out')}</Button> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {data.skipped.length > 0 ? (
        <div className="space-y-1">
          <h3 className="text-sm font-semibold">{t('reminders.today_skipped')} ({data.skipped.length})</h3>
          <ul className="space-y-1 text-sm">
            {data.skipped.map((k) => (
              <li key={`${k.entry_id}:${k.rule_id}`} className="flex items-center justify-between gap-2 border-b py-1">
                <span>{k.description ?? '—'} <span className="text-xs text-muted-foreground">· {t(`reminders.skip.${k.reason}`)}</span></span>
                {isAdmin && k.reason === 'receivable_opt_out' ? (
                  <Button size="sm" variant="ghost" disabled={optOut.isPending} onClick={() => optOut.mutate({ entryId: k.entry_id, optOut: false })}>{t('reminders.opt_in')}</Button>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

// ---- log ---------------------------------------------------------------------------------------------------

function SentLog({ hooks }: { hooks: FinanceReminderHooks }) {
  const [status, setStatus] = React.useState<ReminderLogStatus | ''>('');
  const [page, setPage] = React.useState(1);
  const log = hooks.useReminderLog({ status, page, page_size: 20 });
  if (log.showSkeleton) return <ListSkeleton />;
  if (log.isError && !log.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(log.error)}`} onRetry={() => log.refetch()} retryLabel={t('common.retry')} />;
  }
  const rows = log.data?.data ?? [];
  return (
    <div className="space-y-3" aria-busy={log.isRefreshing}>
      <div className="max-w-xs">
        <Field label={t('reminders.log_filter')}>
          <Select value={status} onChange={(e) => { setStatus(e.target.value as ReminderLogStatus | ''); setPage(1); }}>
            <option value="">{t('common.all')}</option>
            {REMINDER_LOG_STATUSES.map((s) => <option key={s} value={s}>{t(`reminders.status.${s}`)}</option>)}
          </Select>
        </Field>
      </div>
      <RefreshingBar active={log.isRefreshing} label={t('common.refreshing')} />
      {rows.length === 0 ? <EmptyState message={t('reminders.log_empty')} /> : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th className="p-2">{t('reminders.col_due')}</th>
              <th className="p-2">{t('reminders.col_rule')}</th>
              <th className="p-2">{t('reminders.col_recipient')}</th>
              <th className="p-2">{t('reminders.col_message')}</th>
              <th className="p-2">{t('reminders.col_status')}</th>
              <th className="p-2">{t('reminders.col_attempts')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b align-top">
                <td className="p-2 whitespace-nowrap">{formatDate(r.cycle_date)}</td>
                <td className="p-2">{offsetLabel(r.offset_days)}</td>
                <td className="p-2 whitespace-nowrap">{r.recipient}</td>
                <td className="p-2 whitespace-pre-wrap">{r.message}{r.last_error ? <span className="block text-xs text-destructive">{r.last_error}</span> : null}</td>
                <td className="p-2">
                  <Badge variant={r.status === 'sent' ? 'default' : r.status === 'failed' ? 'destructive' : 'outline'}>{t(`reminders.status.${r.status}`)}</Badge>
                  {r.sent_at ? <span className="block text-xs text-muted-foreground">{formatDate(r.sent_at)}</span> : null}
                </td>
                <td className="p-2">{r.attempts}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <Pager page={page} totalPages={totalPagesOf(log.data?.pagination)} onPage={setPage} />
    </div>
  );
}
