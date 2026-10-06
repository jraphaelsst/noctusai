/**
 * Admin > Organizações — superadmin act-as-org entry point (Round 2).
 *
 * Table of orgs (nome, dono, produtos licenciados). Per licensed product an
 * "Entrar" button opens a dialog with an OPTIONAL "Motivo"; confirming POSTs
 * `/api/admin/act-as` and hard-navigates to `redirect_url` (the product, with
 * an SSO token minted for the superadmin). A "Histórico" tab lists sessions.
 * The route sits under `/admin/*`, which `CoreLayout` already gates to the
 * platform admin (`noctus_users.role='admin'`); the backend re-enforces.
 */
import { useState } from 'react';
import { Badge, Button, Dialog, DialogBody, DialogFooter, DialogHeader, EmptyState, ErrorState, Skeleton, Textarea } from '@noctusai/lib/design-system';
import { useActAsHistory, useAdminOrgs, useStartActAs, type LicensedProduct, type OrgRow } from '../../lib/actAs';

const TABS = [
  { id: 'orgs', label: 'Organizações' },
  { id: 'history', label: 'Histórico' },
] as const;
type TabId = (typeof TABS)[number]['id'];

function formatDateTime(value: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString('pt-BR');
}

interface Target { org: OrgRow; product: LicensedProduct }

function EnterDialog({ target, onClose }: { target: Target | null; onClose: () => void }) {
  const [reason, setReason] = useState('');
  const start = useStartActAs();

  function close() {
    if (start.isPending) return;
    setReason('');
    start.reset();
    onClose();
  }

  function confirm() {
    if (!target) return;
    const trimmed = reason.trim();
    start.mutate(
      { org_id: target.org.id, product_slug: target.product.slug, ...(trimmed ? { reason: trimmed } : {}) },
      { onSuccess: (res) => { window.location.assign(res.redirect_url); } },
    );
  }

  return (
    <Dialog open={target !== null} onClose={close} title="Entrar como organização">
      <DialogHeader>
        <h2 className="text-lg font-semibold text-foreground">Entrar como organização</h2>
      </DialogHeader>
      <DialogBody>
        {target && (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Você vai acessar <strong>{target.product.nome}</strong> como <strong>{target.org.nome}</strong>,
              com leitura e escrita. A sessão dura até você clicar em "Sair" dentro do produto.
            </p>
            <label className="block space-y-1">
              <span className="text-xs font-medium text-foreground">Motivo (opcional)</span>
              <Textarea
                aria-label="Motivo"
                rows={3}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Ex.: suporte ao chamado #123"
              />
            </label>
            {start.error && (
              <p role="alert" className="text-sm text-destructive">{start.error.message}</p>
            )}
          </div>
        )}
      </DialogBody>
      <DialogFooter className="gap-2">
        <Button variant="ghost" onClick={close} disabled={start.isPending}>Cancelar</Button>
        <Button variant="primary" onClick={confirm} disabled={start.isPending}>
          {start.isPending ? 'Entrando...' : 'Confirmar e entrar'}
        </Button>
      </DialogFooter>
    </Dialog>
  );
}

function OrgsTab() {
  const { data, isPending, isFetching, error } = useAdminOrgs();
  const [target, setTarget] = useState<Target | null>(null);
  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  if (showSkeleton) {
    return <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</div>;
  }
  if (error && !data) return <ErrorState message={error.message} />;
  if (!data || data.length === 0) return <EmptyState message="Nenhuma organização encontrada" />;

  return (
    <div aria-busy={isRefreshing} className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead className="bg-muted/40 text-left text-xs uppercase text-muted-foreground">
          <tr>
            <th className="px-4 py-2">Organização</th>
            <th className="px-4 py-2">Dono</th>
            <th className="px-4 py-2">Produtos licenciados</th>
          </tr>
        </thead>
        <tbody>
          {data.map((org) => (
            <tr key={org.id} className="border-t border-border align-top">
              <td className="px-4 py-3">
                <div className="font-medium text-foreground">{org.nome}</div>
                <code className="text-xs text-muted-foreground">{org.slug}</code>
              </td>
              <td className="px-4 py-3 text-muted-foreground">{org.owner_email ?? '—'}</td>
              <td className="px-4 py-3">
                {org.licensed_products.length === 0 ? (
                  <span className="text-muted-foreground">Nenhum produto licenciado</span>
                ) : (
                  <ul className="space-y-2">
                    {org.licensed_products.map((p) => (
                      <li key={p.slug} className="flex items-center gap-2">
                        <Badge variant="outline">{p.nome}</Badge>
                        <Button
                          size="sm"
                          variant="outline"
                          aria-label={`Entrar em ${p.nome} como ${org.nome}`}
                          onClick={() => setTarget({ org, product: p })}
                        >
                          Entrar
                        </Button>
                      </li>
                    ))}
                  </ul>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <EnterDialog target={target} onClose={() => setTarget(null)} />
    </div>
  );
}

function HistoryTab() {
  const { data, isPending, isFetching, error } = useActAsHistory(true);
  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  if (showSkeleton) {
    return <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-10" />)}</div>;
  }
  if (error && !data) return <ErrorState message={error.message} />;
  if (!data || data.length === 0) return <EmptyState message="Nenhuma sessão registrada" />;

  return (
    <div aria-busy={isRefreshing} className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead className="bg-muted/40 text-left text-xs uppercase text-muted-foreground">
          <tr>
            <th className="px-4 py-2">Quando</th>
            <th className="px-4 py-2">Evento</th>
            <th className="px-4 py-2">Organização</th>
            <th className="px-4 py-2">Produto</th>
            <th className="px-4 py-2">Motivo</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr key={row.id} className="border-t border-border">
              <td className="px-4 py-2">{formatDateTime(row.at)}</td>
              <td className="px-4 py-2">{row.action === 'act_as.end' ? 'Saída' : 'Entrada'}</td>
              <td className="px-4 py-2">{row.org ?? '—'}</td>
              <td className="px-4 py-2">{row.product ?? '—'}</td>
              <td className="px-4 py-2 text-muted-foreground">{row.reason ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function AdminOrganizacoes() {
  const [tab, setTab] = useState<TabId>('orgs');
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-foreground">Organizações</h1>
        <p className="mt-1 text-muted-foreground">Entre em um produto como uma organização cliente</p>
      </header>
      <nav role="tablist" aria-label="Seções de organizações" className="flex gap-2 border-b border-border pb-2">
        {TABS.map((t) => (
          <Button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            variant={tab === t.id ? 'primary' : 'ghost'}
            size="sm"
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </Button>
        ))}
      </nav>
      <div role="tabpanel">{tab === 'orgs' ? <OrgsTab /> : <HistoryTab />}</div>
    </div>
  );
}

export default AdminOrganizacoes;
