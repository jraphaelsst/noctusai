/**
 * `<PartiesTable/>` — searchable, filterable, paged list of parties with role chips, a create / edit
 * dialog (`<PartyEditor/>`) and CSV export / import.
 *
 * Two-signal loading: a skeleton on the FIRST load only; a refetch over data shows a small indicator
 * and never unmounts the table (no lying empty state). `doc` arrives masked from the server for
 * non-admin readers and is rendered as given. `canWrite` is UX only — the server enforces admin-only writes.
 */
import * as React from 'react';
import { Badge } from '../design-system/ui/Badge';
import { Button } from '../design-system/ui/Button';
import { EmptyState, Input, ListSkeleton, RefreshingBar, RetryError, Select } from './controls';
import { formatDoc } from './format';
import { errorMessage, type PartiesHooks } from './hooks';
import { t } from './i18n';
import { PartiesCsvActions } from './PartiesCsvActions';
import { PartyEditor } from './PartyEditor';
import { RoleChips } from './RoleChips';
import { PARTY_KINDS, PARTY_ROLES, type PartiesActiveFilter, type PartiesListParams, type PartyKind, type PartyRole } from './types';

export interface PartiesTableProps {
  hooks: PartiesHooks;
  /** Admin write access (UX only). Default `false`. */
  canWrite?: boolean;
  /** Initial role filter, e.g. `supplier` for a "Fornecedores" page. */
  initialRole?: PartyRole | '';
  pageSize?: number;
  /** Row click override; default opens the built-in `<PartyEditor/>`. */
  onSelect?: (id: string) => void;
}

export function PartiesTable({ hooks, canWrite = false, initialRole = '', pageSize = 20, onSelect }: PartiesTableProps) {
  const [q, setQ] = React.useState('');
  const [debounced, setDebounced] = React.useState('');
  const [kind, setKind] = React.useState<PartyKind | ''>('');
  const [role, setRole] = React.useState<PartyRole | ''>(initialRole);
  const [active, setActive] = React.useState<PartiesActiveFilter>('active');
  const [page, setPage] = React.useState(1);
  const [editing, setEditing] = React.useState<string | 'new' | null>(null);

  React.useEffect(() => {
    const h = setTimeout(() => {
      setDebounced(q.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(h);
  }, [q]);

  const filters: PartiesListParams = { q: debounced, kind, role, active };
  const list = hooks.useParties({ ...filters, page, page_size: pageSize });

  const header = (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="text-base font-semibold">{t('parties.title')}</h2>
      {canWrite ? <Button size="sm" onClick={() => setEditing('new')}>{t('parties.new')}</Button> : null}
    </div>
  );

  const controls = (
    <div className="flex flex-wrap items-end gap-2">
      <div className="min-w-[14rem] flex-1">
        <Input type="search" aria-label={t('parties.search')} placeholder={t('parties.search')} value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <Select aria-label={t('parties.filter_kind')} value={kind} onChange={(e) => { setKind(e.target.value as PartyKind | ''); setPage(1); }}>
        <option value="">{t('parties.all_kinds')}</option>
        {PARTY_KINDS.map((k) => <option key={k} value={k}>{t(`kind.${k}`)}</option>)}
      </Select>
      <Select aria-label={t('parties.filter_role')} value={role} onChange={(e) => { setRole(e.target.value as PartyRole | ''); setPage(1); }}>
        <option value="">{t('parties.all_roles')}</option>
        {PARTY_ROLES.map((r) => <option key={r} value={r}>{t(`role.${r}`)}</option>)}
      </Select>
      <Select aria-label={t('parties.filter_active')} value={active} onChange={(e) => { setActive(e.target.value as PartiesActiveFilter); setPage(1); }}>
        <option value="active">{t('parties.only_active')}</option>
        <option value="archived">{t('parties.only_archived')}</option>
        <option value="all">{t('parties.all')}</option>
      </Select>
    </div>
  );

  let content: React.ReactNode;
  if (list.showSkeleton) {
    content = <ListSkeleton rows={6} />;
  } else if (list.isError && !list.data) {
    content = <RetryError message={`${t('common.error_loading')}: ${errorMessage(list.error)}`} onRetry={() => list.refetch()} retryLabel={t('common.retry')} />;
  } else {
    const rows = list.data?.data ?? [];
    const pg = list.data?.pagination;
    const totalPages = pg ? (pg.total_pages ?? Math.max(1, Math.ceil(pg.total / pg.page_size))) : 1;
    const filtered = !!(debounced || kind || role || active !== 'active');
    content = (
      <>
        <RefreshingBar active={list.isRefreshing} label={t('common.refreshing')} />
        {rows.length === 0 ? (
          <EmptyState message={filtered ? t('parties.empty_search') : t('parties.empty')} />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="p-2">{t('parties.col_name')}</th>
                <th className="p-2">{t('parties.col_doc')}</th>
                <th className="p-2">{t('parties.col_roles')}</th>
                <th className="p-2">{t('parties.col_contact')}</th>
                <th className="p-2">{t('parties.col_status')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr
                  key={p.id}
                  tabIndex={0}
                  className="cursor-pointer border-b hover:bg-accent focus:bg-accent"
                  onClick={() => (onSelect ? onSelect(p.id) : setEditing(p.id))}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') (onSelect ? onSelect(p.id) : setEditing(p.id));
                  }}
                >
                  <td className="p-2">
                    <div className="font-medium">{p.legal_name}</div>
                    {p.trade_name ? <div className="text-xs text-muted-foreground">{p.trade_name}</div> : null}
                  </td>
                  <td className="p-2 tabular-nums">{p.doc ? formatDoc(p.kind, p.doc) : '—'}</td>
                  <td className="p-2"><RoleChips roles={p.roles} /></td>
                  <td className="p-2">
                    <div>{p.email ?? '—'}</div>
                    {p.phones[0] ? <div className="text-xs text-muted-foreground">{p.phones[0]}</div> : null}
                  </td>
                  <td className="p-2">
                    <Badge variant={p.is_active ? 'outline' : 'muted'}>{p.is_active ? t('parties.active') : t('parties.archived')}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {totalPages > 1 ? (
          <div className="flex items-center justify-end gap-2 text-sm">
            <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((n) => n - 1)}>{t('common.previous')}</Button>
            <span>{page} / {totalPages}</span>
            <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => setPage((n) => n + 1)}>{t('common.next')}</Button>
          </div>
        ) : null}
      </>
    );
  }

  return (
    <section className="space-y-3" aria-busy={list.isRefreshing}>
      {header}
      {controls}
      <PartiesCsvActions hooks={hooks} filters={filters} canWrite={canWrite} />
      {content}
      {editing !== null ? (
        <PartyEditor
          hooks={hooks}
          open
          partyId={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          canWrite={canWrite}
          defaultRoles={editing === 'new' && role ? [role] : undefined}
        />
      ) : null}
    </section>
  );
}
