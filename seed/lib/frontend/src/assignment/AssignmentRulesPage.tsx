/**
 * `<AssignmentRulesPage/>` — how leads are distributed: the org's strategy (a builtin or the product's custom one), the
 * default team, keep-last, the source / unit → team rules, who carries how much, and the latest distributions.
 * Reads render for anyone; every control needs `canWrite`.
 */
import * as React from 'react';
import { Badge, Button, Card, EmptyState, Field, FormError, Input, ListSkeleton, RefreshingBar, RetryError, Select } from './controls';
import { assignmentErrorMessage, errorMessage } from './hooks';
import { defaultAssignmentT } from './i18n';
import type { AssignmentOrganProps } from './shared';
import { formatDay } from './shared';
import { ASSIGNMENT_STRATEGIES, ASSIGNMENT_RULE_KINDS, type AssignmentEvent, type AssignmentRuleKind, type AssignmentTeam, type AssignmentWorkloadRow } from './types';

export type AssignmentRulesPageProps = AssignmentOrganProps & {
  /** How many recent events to show (default 20). */
  eventsLimit?: number;
};

type T = NonNullable<AssignmentOrganProps['t']>;

function strategyLabel(t: T, name: string): string {
  return (ASSIGNMENT_STRATEGIES as readonly string[]).includes(name) ? t(`strategy.${name}`) : t('strategy.custom', { name });
}

function strategyHint(t: T, name: string): string {
  return (ASSIGNMENT_STRATEGIES as readonly string[]).includes(name) ? t(`strategy.hint.${name}`) : t('strategy.hint.custom');
}

function who(id: string | null, names: Map<string, string>, t: T): string {
  return id ? (names.get(id) ?? t('member.unnamed')) : t('events.nobody');
}

function eventText(e: AssignmentEvent, names: Map<string, string>, t: T): string {
  const reason = e.criterion ? (t(`events.reason.${e.criterion}`) !== `events.reason.${e.criterion}` ? t(`events.reason.${e.criterion}`) : e.criterion) : '';
  return t(`events.${e.event}`, { to: who(e.to_user_id, names, t), from: who(e.from_user_id, names, t), reason });
}

function Strategy({ hooks, t, canWrite, teams }: Pick<AssignmentRulesPageProps, 'hooks' | 'canWrite'> & { t: T; teams: AssignmentTeam[] }) {
  const settings = hooks.useSettings();
  const save = hooks.useSettingsMutation();
  const [err, setErr] = React.useState<string | null>(null);
  if (settings.showSkeleton) return <ListSkeleton rows={2} />;
  if (settings.isError && !settings.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(settings.error)}`} onRetry={() => settings.refetch()} retryLabel={t('common.retry')} />;
  }
  const s = settings.data;
  if (!s) return null;
  const names = [...s.builtin, ...s.custom.filter((c) => !s.builtin.includes(c))];
  const run = async (patch: Parameters<typeof save.mutateAsync>[0]) => {
    setErr(null);
    try {
      await save.mutateAsync(patch);
    } catch (e) {
      setErr(assignmentErrorMessage(e, t));
    }
  };
  return (
    <Card className="space-y-3 p-3" data-testid="assignment-strategy">
      <h2 className="text-base font-semibold">{t('strategy.title')}</h2>
      <Field label={t('strategy.title')}>
        <Select value={s.strategy} disabled={!canWrite || save.isPending} onChange={(e) => run({ strategy: e.target.value })} data-testid="strategy-select">
          {names.map((n) => (<option key={n} value={n}>{strategyLabel(t, n)}</option>))}
        </Select>
      </Field>
      <p className="text-xs text-muted-foreground">{strategyHint(t, s.strategy)}</p>
      <Field label={t('strategy.default_team')}>
        <Select value={s.default_team_id ?? ''} disabled={!canWrite || save.isPending} onChange={(e) => run({ default_team_id: e.target.value || null })} data-testid="default-team-select">
          <option value="">{t('strategy.no_default_team')}</option>
          {teams.map((tm) => (<option key={tm.id} value={tm.id}>{tm.name}</option>))}
        </Select>
      </Field>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={s.keep_last} disabled={!canWrite || save.isPending} onChange={(e) => run({ keep_last: e.target.checked })} />
        {t('strategy.keep_last')}
      </label>
      <FormError message={err} />
    </Card>
  );
}

function Rules({ hooks, t, canWrite, teams }: Pick<AssignmentRulesPageProps, 'hooks' | 'canWrite'> & { t: T; teams: AssignmentTeam[] }) {
  const rules = hooks.useRules();
  const m = hooks.useRuleMutations();
  const [kind, setKind] = React.useState<AssignmentRuleKind>('source');
  const [value, setValue] = React.useState('');
  const [teamId, setTeamId] = React.useState('');
  const [err, setErr] = React.useState<string | null>(null);
  if (rules.showSkeleton) return <ListSkeleton rows={2} />;
  if (rules.isError && !rules.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(rules.error)}`} onRetry={() => rules.refetch()} retryLabel={t('common.retry')} />;
  }
  const rows = rules.data ?? [];
  const teamName = new Map(teams.map((tm) => [tm.id, tm.name]));
  const run = async (p: Promise<unknown>) => {
    setErr(null);
    try {
      await p;
    } catch (e) {
      setErr(assignmentErrorMessage(e, t));
    }
  };
  function add(ev: React.FormEvent) {
    ev.preventDefault();
    if (!value.trim() || !teamId) return void setErr(t('rules.invalid'));
    void run(m.put.mutateAsync({ kind, match_value: value.trim(), team_id: teamId }).then(() => setValue('')));
  }
  return (
    <Card className="space-y-3 p-3" data-testid="assignment-rules" aria-busy={rules.isRefreshing}>
      <h2 className="text-base font-semibold">{t('rules.title')}</h2>
      <RefreshingBar active={rules.isRefreshing} label={t('common.refreshing')} />
      {rows.length === 0 ? (
        <EmptyState message={t('rules.empty')} />
      ) : (
        <ul className="divide-y rounded-md border">
          {rows.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center gap-2 p-2 text-sm" data-testid="assignment-rule">
              <Badge variant="muted">{t(`rules.kind.${r.kind}`)}</Badge>
              <strong>{r.match_value}</strong>
              <span aria-hidden>→</span>
              <span>{teamName.get(r.team_id) ?? t('member.unnamed')}</span>
              {canWrite ? (
                <Button size="sm" variant="ghost" className="ml-auto" disabled={m.remove.isPending} onClick={() => run(m.remove.mutateAsync({ id: r.id }))}>{t('common.remove')}</Button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      <FormError message={err} />
      {canWrite ? (
        teams.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t('rules.needs_teams')}</p>
        ) : (
          <form onSubmit={add} className="grid gap-2 sm:grid-cols-4" aria-label={t('rules.add')}>
            <Field label={t('rules.kind')}>
              <Select value={kind} onChange={(e) => setKind(e.target.value as AssignmentRuleKind)}>
                {ASSIGNMENT_RULE_KINDS.map((k) => (<option key={k} value={k}>{t(`rules.kind.${k}`)}</option>))}
              </Select>
            </Field>
            <Field label={t('rules.value')} required>
              <Input value={value} maxLength={120} placeholder={t(`rules.value_hint.${kind}`)} onChange={(e) => setValue(e.target.value)} />
            </Field>
            <Field label={t('rules.team')} required>
              <Select value={teamId} onChange={(e) => setTeamId(e.target.value)} data-testid="rule-team">
                <option value="">{t('rules.pick_team')}</option>
                {teams.map((tm) => (<option key={tm.id} value={tm.id}>{tm.name}</option>))}
              </Select>
            </Field>
            <div className="flex items-end">
              <Button type="submit" variant="primary" disabled={m.put.isPending}>{m.put.isPending ? t('common.saving') : t('rules.add')}</Button>
            </div>
          </form>
        )
      ) : null}
    </Card>
  );
}

function Workload({ rows, t }: { rows: AssignmentWorkloadRow[]; t: T }) {
  return rows.length === 0 ? (
    <EmptyState message={t('workload.empty')} />
  ) : (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-xs text-muted-foreground">
          <th className="py-1">{t('workload.person')}</th>
          <th className="py-1">{t('workload.open')}</th>
          <th className="py-1">{t('workload.status')}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.user_id} className="border-t" data-testid="workload-row">
            <td className="py-1">{r.name ?? t('member.unnamed')}</td>
            <td className="py-1">{r.open_count}</td>
            <td className="py-1">
              {r.available ? (
                <Badge>{t('workload.available')}</Badge>
              ) : (
                <Badge variant="muted">
                  {r.unavailable_reasons.length ? r.unavailable_reasons.map((x) => t(`member.unavailable.${x}`)).join(', ') : t('workload.unavailable')}
                </Badge>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function AssignmentRulesPage({ hooks, t = defaultAssignmentT, locale = 'pt-BR', canWrite = false, eventsLimit = 20 }: AssignmentRulesPageProps) {
  const teams = hooks.useTeams();
  const workload = hooks.useWorkload();
  const events = hooks.useEvents({ limit: eventsLimit });

  if (teams.showSkeleton) return <ListSkeleton rows={4} />;
  if (teams.isError && !teams.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(teams.error)}`} onRetry={() => teams.refetch()} retryLabel={t('common.retry')} />;
  }
  const teamRows = teams.data ?? [];
  const names = new Map((workload.data ?? []).map((w) => [w.user_id, w.name ?? t('member.unnamed')]));

  return (
    <div className="space-y-4" aria-busy={teams.isRefreshing}>
      <RefreshingBar active={teams.isRefreshing} label={t('common.refreshing')} />
      <Strategy hooks={hooks} t={t} canWrite={canWrite} teams={teamRows} />
      <Rules hooks={hooks} t={t} canWrite={canWrite} teams={teamRows} />
      <Card className="space-y-2 p-3" data-testid="assignment-workload" aria-busy={workload.isRefreshing}>
        <h2 className="text-base font-semibold">{t('workload.title')}</h2>
        {workload.showSkeleton ? (
          <ListSkeleton rows={3} />
        ) : workload.isError && !workload.data ? (
          <RetryError message={`${t('common.error_loading')}: ${errorMessage(workload.error)}`} onRetry={() => workload.refetch()} retryLabel={t('common.retry')} />
        ) : (
          <Workload rows={workload.data ?? []} t={t} />
        )}
      </Card>
      <Card className="space-y-2 p-3" data-testid="assignment-events" aria-busy={events.isRefreshing}>
        <h2 className="text-base font-semibold">{t('events.title')}</h2>
        {events.showSkeleton ? (
          <ListSkeleton rows={3} />
        ) : events.isError && !events.data ? (
          <RetryError message={`${t('common.error_loading')}: ${errorMessage(events.error)}`} onRetry={() => events.refetch()} retryLabel={t('common.retry')} />
        ) : (events.data ?? []).length === 0 ? (
          <EmptyState message={t('events.empty')} />
        ) : (
          <ul className="divide-y text-sm">
            {(events.data ?? []).map((e) => (
              <li key={e.id} className="flex flex-wrap items-center gap-2 py-1" data-testid="assignment-event">
                <span>{eventText(e, names, t)}</span>
                {e.criterion && e.event !== 'no_candidate' ? <span className="text-xs text-muted-foreground">{t('events.criterion', { criterion: e.criterion })}</span> : null}
                <time className="ml-auto text-xs text-muted-foreground" dateTime={e.created_at}>{formatDay(e.created_at, locale)}</time>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
