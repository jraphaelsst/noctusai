/**
 * `<TeamsManager/>` — teams and their members: create / rename / delete a team, add / remove a member, rotation order,
 * active, capacity (max open cases) and out-of-office. Reads render for anyone; every control needs `canWrite`.
 */
import * as React from 'react';
import { Badge, Button, EmptyState, Field, FormError, Input, ListSkeleton, RefreshingBar, RetryError, Select } from './controls';
import { assignmentErrorMessage, errorMessage } from './hooks';
import { defaultAssignmentT } from './i18n';
import { dayToIso, formatDay, type AssignmentOrganProps } from './shared';
import type { AssignmentMemberPatch, AssignmentTeam, AssignmentTeamMember, AssignmentWorkloadRow } from './types';

export type TeamsManagerProps = AssignmentOrganProps;

type Run = (p: Promise<unknown>) => Promise<void>;
type TeamMutations = ReturnType<AssignmentOrganProps['hooks']['useTeamMutations']>;

function MemberRow({
  team, member, m, run, t, locale, canWrite, first, last, order,
}: {
  team: AssignmentTeam; member: AssignmentTeamMember; m: TeamMutations; run: Run; t: NonNullable<AssignmentOrganProps['t']>; locale: string; canWrite: boolean;
  first: boolean; last: boolean; order: (userId: string, delta: -1 | 1) => void;
}) {
  const [capacity, setCapacity] = React.useState(member.capacity == null ? '' : String(member.capacity));
  const [from, setFrom] = React.useState('');
  const [until, setUntil] = React.useState('');
  React.useEffect(() => setCapacity(member.capacity == null ? '' : String(member.capacity)), [member.capacity]);
  const pending = m.updateMember.isPending || m.removeMember.isPending;
  const patch = (changes: AssignmentMemberPatch) =>
    run(m.updateMember.mutateAsync({ teamId: team.id, userId: member.user_id, ...changes }));
  const awayUntil = member.unavailable_reason === 'out_of_office' || (member.ooo_until && new Date(member.ooo_until) > new Date()) ? member.ooo_until : null;

  function saveCapacity() {
    const next = capacity.trim() === '' ? null : Number(capacity);
    if (next !== null && (!Number.isInteger(next) || next < 1)) {
      setCapacity(member.capacity == null ? '' : String(member.capacity));
      return;
    }
    if (next !== member.capacity) void patch({ capacity: next });
  }

  return (
    <li className="flex flex-wrap items-center gap-2 py-2 text-sm" data-testid="team-member">
      <strong>{member.name ?? t('member.unnamed')}</strong>
      {!member.in_org ? <Badge variant="muted">{t('member.left_org')}</Badge> : null}
      {!member.active ? <Badge variant="muted">{t('member.inactive')}</Badge> : null}
      {awayUntil ? <Badge variant="muted">{t('member.ooo_badge', { date: formatDay(awayUntil, locale) })}</Badge> : null}
      {member.unavailable_reason === 'at_capacity' ? <Badge variant="muted">{t('member.unavailable.at_capacity')}</Badge> : null}
      <span className="text-xs text-muted-foreground">
        {member.capacity != null ? t('member.open_of', { count: member.open_count, capacity: member.capacity }) : t('member.open', { count: member.open_count })}
      </span>
      {canWrite ? (
        <span className="ml-auto flex flex-wrap items-end gap-2">
          <Field label={t('member.capacity')}>
            <Input
              type="number" min={1} inputMode="numeric" className="w-20" value={capacity} placeholder="∞" title={t('member.capacity_hint')}
              onChange={(e) => setCapacity(e.target.value)} onBlur={saveCapacity} disabled={pending}
            />
          </Field>
          {awayUntil ? (
            <Button size="sm" variant="ghost" disabled={pending} onClick={() => patch({ ooo_from: null, ooo_until: null })}>{t('member.ooo_clear')}</Button>
          ) : (
            <>
              <Field label={t('member.ooo_from')}><Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
              <Field label={t('member.ooo_until')}><Input type="date" value={until} onChange={(e) => setUntil(e.target.value)} /></Field>
              <Button
                size="sm" variant="ghost" disabled={pending || !until}
                onClick={() => patch({ ooo_from: dayToIso(from) ?? new Date().toISOString(), ooo_until: dayToIso(until, true) }).then(() => { setFrom(''); setUntil(''); })}
              >
                {t('member.ooo_set')}
              </Button>
            </>
          )}
          <Button size="sm" variant="ghost" disabled={pending} onClick={() => patch({ active: !member.active })}>
            {member.active ? t('member.deactivate') : t('member.activate')}
          </Button>
          <Button size="sm" variant="ghost" disabled={pending || first} aria-label={t('member.move_up')} title={t('member.move_up')} onClick={() => order(member.user_id, -1)}>↑</Button>
          <Button size="sm" variant="ghost" disabled={pending || last} aria-label={t('member.move_down')} title={t('member.move_down')} onClick={() => order(member.user_id, 1)}>↓</Button>
          <Button size="sm" variant="ghost" disabled={pending} onClick={() => run(m.removeMember.mutateAsync({ teamId: team.id, userId: member.user_id }))}>{t('common.remove')}</Button>
        </span>
      ) : null}
    </li>
  );
}

function TeamCard({
  team, people, m, run, t, locale, canWrite,
}: {
  team: AssignmentTeam; people: AssignmentWorkloadRow[]; m: TeamMutations; run: Run; t: NonNullable<AssignmentOrganProps['t']>; locale: string; canWrite: boolean;
}) {
  const [renaming, setRenaming] = React.useState(false);
  const [name, setName] = React.useState(team.name);
  const [confirming, setConfirming] = React.useState(false);
  const [nameErr, setNameErr] = React.useState<string | null>(null);
  const [pick, setPick] = React.useState('');
  const seated = new Set(team.members.map((x) => x.user_id));
  const candidates = people.filter((p) => !seated.has(p.user_id));

  function reorder(userId: string, delta: -1 | 1) {
    const ids = team.members.map((x) => x.user_id);
    const i = ids.indexOf(userId);
    const j = i + delta;
    if (i < 0 || j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    void run(m.order.mutateAsync({ teamId: team.id, order: ids }));
  }

  return (
    <section className="space-y-2 rounded-md border p-3" data-testid="team-card" aria-label={team.name}>
      <header className="flex flex-wrap items-center gap-2">
        {renaming ? (
          <form
            className="flex items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (!name.trim() || name.trim().length > 60) return void setNameErr(t('teams.invalid_name'));
              setNameErr(null);
              void run(m.update.mutateAsync({ id: team.id, name: name.trim() }).then(() => setRenaming(false)));
            }}
          >
            <Field label={t('teams.name')} error={nameErr}><Input value={name} maxLength={60} onChange={(e) => setName(e.target.value)} /></Field>
            <Button type="submit" size="sm" variant="primary" disabled={m.update.isPending}>{m.update.isPending ? t('common.saving') : t('teams.rename')}</Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => { setRenaming(false); setName(team.name); }}>{t('common.cancel')}</Button>
          </form>
        ) : (
          <h3 className="text-base font-semibold">{team.name}</h3>
        )}
        <Badge variant={team.auto ? undefined : 'muted'}>{team.auto ? t('teams.auto_badge') : t('teams.manual_badge')}</Badge>
        {canWrite && !renaming ? (
          <span className="ml-auto flex flex-wrap gap-1">
            <Button size="sm" variant="ghost" disabled={m.update.isPending} onClick={() => run(m.update.mutateAsync({ id: team.id, auto: !team.auto }))}>
              {team.auto ? t('teams.manual_badge') : t('teams.auto_badge')}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setRenaming(true)}>{t('teams.rename')}</Button>
            {confirming ? (
              <>
                <Button size="sm" variant="outline" disabled={m.remove.isPending} onClick={() => run(m.remove.mutateAsync({ id: team.id }))}>{t('common.confirm_delete')}</Button>
                <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>{t('common.cancel')}</Button>
              </>
            ) : (
              <Button size="sm" variant="ghost" onClick={() => setConfirming(true)}>{t('teams.delete')}</Button>
            )}
          </span>
        ) : null}
      </header>

      {team.members.length === 0 ? (
        <EmptyState message={t('teams.no_members')} />
      ) : (
        <ul className="divide-y" aria-label={t('teams.members')}>
          {team.members.map((member, i) => (
            <MemberRow
              key={member.user_id} team={team} member={member} m={m} run={run} t={t} locale={locale} canWrite={canWrite}
              first={i === 0} last={i === team.members.length - 1} order={reorder}
            />
          ))}
        </ul>
      )}

      {canWrite ? (
        candidates.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t('teams.no_candidates')}</p>
        ) : (
          <form
            className="flex items-end gap-2"
            aria-label={t('teams.add_member')}
            onSubmit={(e) => {
              e.preventDefault();
              if (pick) void run(m.addMember.mutateAsync({ teamId: team.id, user_id: pick }).then(() => setPick('')));
            }}
          >
            <Field label={t('teams.add_member')}>
              <Select value={pick} onChange={(e) => setPick(e.target.value)} data-testid="member-picker">
                <option value="">{t('teams.pick_member')}</option>
                {candidates.map((p) => (<option key={p.user_id} value={p.user_id}>{p.name ?? t('member.unnamed')}</option>))}
              </Select>
            </Field>
            <Button type="submit" variant="primary" disabled={!pick || m.addMember.isPending}>{m.addMember.isPending ? t('common.saving') : t('teams.add_member')}</Button>
          </form>
        )
      ) : null}
    </section>
  );
}

export function TeamsManager({ hooks, t = defaultAssignmentT, locale = 'pt-BR', canWrite = false }: TeamsManagerProps) {
  const teams = hooks.useTeams();
  const workload = hooks.useWorkload();
  const m = hooks.useTeamMutations();
  const [name, setName] = React.useState('');
  const [auto, setAuto] = React.useState(true);
  const [err, setErr] = React.useState<string | null>(null);

  if (teams.showSkeleton) return <ListSkeleton rows={3} />;
  if (teams.isError && !teams.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(teams.error)}`} onRetry={() => teams.refetch()} retryLabel={t('common.retry')} />;
  }
  const rows = teams.data ?? [];

  const run: Run = async (p) => {
    setErr(null);
    try {
      await p;
    } catch (e) {
      setErr(assignmentErrorMessage(e, t));
    }
  };

  function create(ev: React.FormEvent) {
    ev.preventDefault();
    const clean = name.trim();
    if (!clean || clean.length > 60) return void setErr(t('teams.invalid_name'));
    void run(m.create.mutateAsync({ name: clean, auto }).then(() => { setName(''); setAuto(true); }));
  }

  return (
    <section className="space-y-3" aria-busy={teams.isRefreshing} aria-label={t('teams.title')}>
      <RefreshingBar active={teams.isRefreshing} label={t('common.refreshing')} />
      <FormError message={err} />
      {rows.length === 0 ? (
        <EmptyState message={t('teams.empty')} />
      ) : (
        rows.map((team) => (
          <TeamCard key={team.id} team={team} people={workload.data ?? []} m={m} run={run} t={t} locale={locale} canWrite={canWrite} />
        ))
      )}
      {canWrite ? (
        <form onSubmit={create} className="flex flex-wrap items-end gap-2 rounded-md border p-3" aria-label={t('teams.new')}>
          <Field label={t('teams.name')} required><Input value={name} maxLength={60} onChange={(e) => setName(e.target.value)} /></Field>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
            {t('teams.auto')}
          </label>
          <Button type="submit" variant="primary" disabled={m.create.isPending}>{m.create.isPending ? t('common.saving') : t('teams.new')}</Button>
        </form>
      ) : null}
    </section>
  );
}
